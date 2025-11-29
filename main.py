import discord, aio_pika, asyncio, argparse, aio_pika.abc, json, re, random
from discord.ext import commands
from dotenv import dotenv_values
from aio_pika.exchange import ExchangeType
from setup_view import SessionSetupView, Session
from rocksdict import Rdict

class WindstormBot(commands.Bot):
    def __init__(self, url: str, nation: str):
        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="%",
            intents=intents
        )

        self.url = url
        self.nation = nation
        self.sessions: dict[int, Session] = {}
        self.setup_roles = Rdict("./setup_roles")

    def generate_region_embed(self, region: str):
        generated_by = f"?generated_by=Windstorm__by_Merethin__usedBy_{self.nation}"

        return discord.Embed().add_field(
            name="Region", value=region, inline=False
        ).add_field(
            name="Link", inline=False,
            value=f"[{"%" * 400}](https://www.nationstates.net/region={region}/template-overall=none{generated_by})"
        )

    def generate_report_embed(self, region: str, first_move: str, moves: list[tuple[int, int]]):
        return discord.Embed(
            title=f"Results: {region}",
        ).add_field(
            name="First Trainer Move", value=f"<@{first_move}>", inline=False
        ).add_field(
            name="Rankings", inline=False,
            value="\n".join([f"{index+1}: <@{user}>, {time}s" for index, (user, time) in enumerate(moves)])
        )

    def generate_score_embed(self, scores: list[tuple[int, int]]):
        return discord.Embed(
            title=f"Final Scores",
            description="\n".join([f"{index+1}: <@{user}>, {score} total seconds" for index, (user, score) in enumerate(scores)])
        )

    async def sse_loop(self):
        connection: aio_pika.abc.AbstractConnection = await aio_pika.connect_robust(self.url, loop=asyncio.get_event_loop())

        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange("akari_events", ExchangeType.TOPIC)
            queue = await channel.declare_queue("", exclusive=True, auto_delete=True)
            await queue.bind(exchange=exchange, routing_key="move")

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        event = json.loads(message.body.decode())

                        target = event["destination"]
                        time = event["time"]
                        event_id = event["event"]
                        nation = event["actor"]

                        for guild, session in self.sessions.items():
                            if target == session.current_target and nation in session.users:
                                print(f"[ID: {event_id}, time: {time}]: {nation} moved to {target}")
                                user_id, is_trainer = session.users[nation]
                                session.moves[user_id] = (time, event_id, is_trainer)

    async def setup_hook(self):
        loop = asyncio.get_event_loop()
        loop.set_task_factory(asyncio.eager_task_factory)

        self.sse_task = asyncio.create_task(self.sse_loop())

    NATION_REGEX = re.compile(r"https://www\.nationstates\.net/nation=([a-z0-9_-]+)")
    SETUP_ROLE_COMMAND_REGEX = re.compile(r"!setup_role (?:<@&)?([0-9]+)>?")

    async def on_message(self, message: discord.Message):
        if message.content.startswith("!setup_role"):
            if message.guild.owner_id == message.author.id:
                match = self.SETUP_ROLE_COMMAND_REGEX.match(message.content)
                role_id = int(match.group(1))

                self.setup_roles[message.guild.id] = role_id
                await message.channel.send("Setup role updated.")
            else:
                await message.reply("You are not allowed to do that!")
        if message.content == "!setup_session":
            if message.guild.owner_id == message.author.id or message.author.get_role(self.setup_roles.get(message.guild.id)) is not None:
                await SessionSetupView(self).send(message)
            else:
                await message.reply("You are not allowed to do that!")
        if message.content == "!end_session":
            if message.guild.owner_id == message.author.id or message.author.get_role(self.setup_roles.get(message.guild.id)) is not None:
                if self.sessions.pop(message.guild.id, None) is not None:
                    await message.channel.send("Session ended.")
                else:
                    await message.channel.send("No session in progress!")
            else:
                await message.reply("You are not allowed to do that!")

        session = self.sessions.get(message.guild.id)
        if session is None:
            return
        
        if message.channel.id != session.chasers_channel and message.channel.id != session.trainers_channel:
            return
        
        if message.content.startswith("https://www.nationstates.net/nation="):
            match = self.NATION_REGEX.match(message.content)
            nation = match.group(1)

            is_trainer = message.channel.id == session.trainers_channel
            session.users[nation] = (message.author.id, is_trainer)
            await message.channel.send(f"Nation {nation} linked to {message.author.display_name}")

        if message.content == "!unlink":
            linked_nation = None
            for nation, (user, is_trainer) in session.users.items():
                if user == message.author.id:
                    linked_nation = nation
                    break

            if linked_nation is not None:
                session.users.pop(linked_nation, None)
                await message.channel.send(f"Nation {linked_nation} unlinked from {message.author.display_name}")
            else:
                await message.channel.send(f"{message.author.display_name} has no nations linked.")

        if message.channel.id != session.trainers_channel:
            return

        if message.content == "t":
            region = random.choice(session.targets)
            session.current_target = region
            await message.channel.send(embed=self.generate_region_embed(region))
        if message.content == "!report":
            region = session.current_target

            first_move = None
            first_move_id = None
            first_move_time = None
            chaser_moves = []
            for user, (time, event_id, is_trainer) in session.moves.items():
                if not is_trainer:
                    chaser_moves.append((user, time, event_id))
                    continue

                if first_move_id is None:
                    pass
                elif first_move_id < event_id:
                    continue

                first_move = user
                first_move_id = event_id
                first_move_time = time

            if first_move_id is None:
                await message.channel.send(f"Trainers have not moved yet!")
                return

            if len(chaser_moves) is None:
                await message.channel.send(f"No chasers have moved!")
                return

            chaser_moves.sort(key=lambda a: a[2])
            moves = [(user, time - first_move_time) for (user, time, event_id) in chaser_moves]

            for (user, time) in moves:
                if user not in session.scores:
                    session.scores[user] = 0
                session.scores[user] += time

            session.current_target = None
            session.moves = {}

            await message.guild.get_channel(session.results_channel).send(embed=self.generate_report_embed(
                region, 
                first_move,
                moves
            ))
        if message.content == "!scores":
            scores = list(session.scores.items())
            scores.sort(key=lambda a: a[1])
            if len(scores) == 0:
                await message.channel.send(f"No scores recorded yet!")
                return
            
            await message.guild.get_channel(session.results_channel).send(embed=self.generate_score_embed(scores))

    async def on_ready(self):
        print(f'Windstorm: logged in as {self.user}')

def main() -> None:
    parser = argparse.ArgumentParser(prog="windstorm", description="Chasing training bot")
    parser.add_argument("-n", "--nation-name", required=True)
    args = parser.parse_args()

    settings = dotenv_values(".env")
    bot = WindstormBot(settings["RABBITMQ_URL"], args.nation_name)
    bot.run(settings["TOKEN"])

if __name__ == "__main__":
    main()
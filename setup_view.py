import discord

class Session:
    def __init__(self, results: int, chasers: int, trainers: int):
        self.results_channel = results
        self.chasers_channel = chasers
        self.trainers_channel = trainers
        self.targets: list[str] = []
        self.users: dict[str, tuple[int, bool]] = {}
        self.moves: dict[int, tuple[int, int, bool]] = {}
        self.scores: dict[int, int] = {}
        self.current_target: str | None = None

    def set_targets(self, targets: list[str]):
        self.targets = targets

class TargetSetupForm(discord.ui.Modal):
    targets = discord.ui.TextInput(label="Targets", style=discord.TextStyle.long, required=True)

    def __init__(self, view):
        self.view = view
        super().__init__(title="Set Targets")

    async def on_submit(self, interaction: discord.Interaction):
        targets = [tg.lower().replace(" ", "_") for tg in self.targets.value.splitlines()]
        await interaction.response.defer()
        await self.view.confirm_targets(targets)

class SessionSetupView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.results_channel_dropdown = discord.ui.ChannelSelect(placeholder="Channel to post results in", channel_types=[discord.ChannelType.text], row=0)
        self.chasers_channel_dropdown = discord.ui.ChannelSelect(placeholder="Channel for chasers", channel_types=[discord.ChannelType.text], row=1)
        self.trainers_channel_dropdown = discord.ui.ChannelSelect(placeholder="Channel for trainers", channel_types=[discord.ChannelType.text], row=2)
        self.bot = bot

        self.results_channel_dropdown.callback = self.dropdown_callback
        self.chasers_channel_dropdown.callback = self.dropdown_callback
        self.trainers_channel_dropdown.callback = self.dropdown_callback

        self.add_item(self.results_channel_dropdown)
        self.add_item(self.chasers_channel_dropdown)
        self.add_item(self.trainers_channel_dropdown)

    async def dropdown_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.user:
            return True
        else:
            await interaction.response.send_message("Only the author of the command can perform this action.", ephemeral=True)
            return False

    @discord.ui.button(label="Set Targets", style=discord.ButtonStyle.blurple, row=3)
    async def set_targets(self, interaction: discord.Interaction, button: discord.Button) -> None:
        await interaction.response.send_modal(TargetSetupForm(self))

    async def send(self, message: discord.Message):
        new_message = await message.channel.send(
            "Select the required channels below and then press the 'Set Targets' button to enter a target list.", 
            view=self
        )

        self.message = new_message
        self.user = message.author

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def confirm_targets(self, targets: list[str]):
        try:
            results_channel = self.results_channel_dropdown.values[0]
            chasers_channel = self.chasers_channel_dropdown.values[0]
            trainers_channel = self.trainers_channel_dropdown.values[0]
        
            session = Session(results_channel.id, chasers_channel.id, trainers_channel.id)
            session.set_targets(targets)

            self.bot.sessions[self.message.guild.id] = session

            await self.message.edit(view=None)
            await self.message.channel.send(
                f"New session set up: \n- **Results channel:** {results_channel.mention}\n- **Chasers channel:** {chasers_channel.mention}\n- **Trainers channel:** {trainers_channel.mention}\n- **Targets loaded:** {len(targets)}"
            )
        except IndexError:
            await self.message.channel.send("Please select a valid channel for all three dropdowns!")
            return
        
class SwitcherSetupForm(discord.ui.Modal):
    switchers = discord.ui.TextInput(label="Switchers", style=discord.TextStyle.long, required=True)

    def __init__(self, view):
        self.view = view
        super().__init__(title="Link Switchers")

    async def on_submit(self, interaction: discord.Interaction):
        switchers = [sw.lower().replace(" ", "_") for sw in self.switchers.value.splitlines()]
        await interaction.response.defer()
        await self.view.confirm_switchers(switchers)

class SwitcherSetupView(discord.ui.View):
    def __init__(self, bot, session: Session):
        super().__init__(timeout=300)
        self.bot = bot
        self.session = session

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.user:
            return True
        else:
            await interaction.response.send_message("Only the author of the command can perform this action.", ephemeral=True)
            return False

    @discord.ui.button(label="Link Switchers", style=discord.ButtonStyle.blurple, row=3)
    async def set_switchers(self, interaction: discord.Interaction, button: discord.Button) -> None:
        await interaction.response.send_modal(SwitcherSetupForm(self))

    async def send(self, message: discord.Message):
        new_message = await message.channel.send(
            "Press the button below to enter a list of switchers.\n" \
            "Your previous switchers will not be cleared. Run !unlink for that.", 
            view=self
        )

        self.message = new_message
        self.user = message.author

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def confirm_switchers(self, switchers: list[str]):
        is_trainer = self.message.channel.id == self.session.trainers_channel

        for switcher in switchers:
            self.session.users[switcher] = (self.user.id, is_trainer)

        await self.message.edit(view=None)
        await self.message.channel.send(
            f"Linked **{len(switchers)} nations** to {self.user.display_name}."
        )
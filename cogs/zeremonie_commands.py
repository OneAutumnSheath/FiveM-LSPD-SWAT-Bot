import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.zeremonie_service import ZeremonieService
    from services.log_service import LogService
    
# --- UI Klasse: Modal ---
class ZeremonieModal(discord.ui.Modal, title="Zeremonie Protokoll"):
    content = discord.ui.TextInput(
        label="Gib das Protokoll ein:",
        style=discord.TextStyle.paragraph,
        placeholder="Hier dein mehrzeiliger Protokolltext...",
        required=True,
        max_length=4000,
    )

    def __init__(self, bot: "MyBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        service: ZeremonieService = self.bot.get_cog("ZeremonieService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Zeremonie-Service ist nicht verfügbar.", ephemeral=True)

        await service.create_ceremony_log(interaction, self.content.value)
        await interaction.followup.send("✅ Protokoll wurde erfolgreich gesendet.", ephemeral=True)

# --- Command Cog ---
class ZeremonieCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="zeremonielog", description="Reiche ein Zeremonie-Protokoll ein.")
    @has_permission("zeremonie.log")
    @log_on_completion
    async def zeremonie_log(self, interaction: discord.Interaction):
        """Öffnet das Formular für das Zeremonie-Protokoll."""
        await interaction.response.send_modal(ZeremonieModal(self.bot))

async def setup(bot: "MyBot"):
    await bot.add_cog(ZeremonieCommands(bot))
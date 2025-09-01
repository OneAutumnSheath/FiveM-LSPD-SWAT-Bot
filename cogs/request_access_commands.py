import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING
from utils.decorators import log_on_completion
if TYPE_CHECKING:
    from main import MyBot
    from services.request_access_service import RequestAccessService
    from services.log_service import LogService
    
# --- UI Klasse: Modal ---
class RequestAccessModal(discord.ui.Modal, title="Zugriffsanfrage"):
    email = discord.ui.TextInput(
        label="Deine Google-Workspace E-Mail",
        placeholder="vorname.nachname@us-army.info",
        style=discord.TextStyle.short,
        required=True
    )
    unit = discord.ui.TextInput(
        label="Unit / Abteilung",
        placeholder="z.B. Management, Personaldepartement, etc.",
        style=discord.TextStyle.short,
        required=True
    )
    dokument = discord.ui.TextInput(
        label="Dokument oder Ordner",
        placeholder="Link zum Dokument/Ordner oder 'Komplettzugriff'",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, bot: "MyBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Service holen
        service: RequestAccessService = self.bot.get_cog("RequestAccessService")
        if not service:
            await interaction.followup.send("❌ Interner Fehler: Der Anfrage-Service ist nicht verfügbar.", ephemeral=True)
            return

        # Daten sammeln
        request_data = {
            "email": self.email.value,
            "unit": self.unit.value,
            "dokument": self.dokument.value
        }

        # Logik an den Service übergeben
        success = await service.create_access_request(interaction, request_data)

        if success:
            await interaction.followup.send("✅ Deine Zugriffsanfrage wurde erfolgreich übermittelt!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Es ist ein Fehler beim Senden deiner Anfrage aufgetreten. Bitte kontaktiere einen Admin.", ephemeral=True)

# --- Command Cog ---
class RequestAccessCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="request-access", description="Öffnet das Formular für Zugriffsanfragen.")
    @log_on_completion
    async def request_access_command(self, interaction: discord.Interaction):
        """Öffnet das Formular für Zugriffsanfragen."""
        modal = RequestAccessModal(self.bot)
        await interaction.response.send_modal(modal)

async def setup(bot: "MyBot"):
    await bot.add_cog(RequestAccessCommands(bot))
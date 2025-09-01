import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

# Importiere die neuen Decorators
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.aufstellung_service import AufstellungService
    from services.log_service import LogService
    
class AufstellungCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="aufstellung", description="Erstellt eine Aufstellung und kündigt sie an.")
    @app_commands.describe(
        user="Das Mitglied, das die Aufstellung durchführt.",
        wann="Datum der Aufstellung (z.B. 'heute', 'morgen', '22.07.2025').",
        uhrzeit="Uhrzeit der Aufstellung (z.B. '20:00').",
        position="Die Position/Rolle des ausführenden Mitglieds."
    )
    @has_permission("aufstellung.create") # Prüft die Berechtigung
    @log_on_completion                  # Loggt bei Erfolg automatisch
    async def aufstellung(self, interaction: discord.Interaction, user: discord.Member, wann: str, uhrzeit: str, position: discord.Role):
        await interaction.response.defer(ephemeral=True)

        # Service holen
        service: AufstellungService = self.bot.get_cog("AufstellungService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Aufstellung-Service ist nicht verfügbar.", ephemeral=True)

        # Logik an den Service delegieren
        success, message = await service.create_aufstellung(user, wann, uhrzeit, position)

        if success:
            # Die manuelle Log-Zeile ist hier nicht mehr nötig
            await interaction.followup.send(f"✅ {message}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)


async def setup(bot: "MyBot"):
    await bot.add_cog(AufstellungCommands(bot))
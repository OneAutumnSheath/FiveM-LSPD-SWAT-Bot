import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING

# Importiere eure Decorators
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.raub_service import RaubService

class RaubCommands(commands.Cog):
    # Die Command Group, die alle Unterbefehle sammelt
    raub = app_commands.Group(name="raub", description="Befehle zur Dokumentation von Raubüberfällen.")

    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "RaubCommands"

    @raub.command(name="eintragen", description="Dokumentiert einen Raub und zählt die Einsätze.")
    @app_commands.describe(
        einsatzleitung="Verantwortliche Person für die Einsatzleitung (EL)",
        verhandlungsfuehrung="Verantwortliche Person für die Verhandlungsführung (VF)",
        beweisbild="Screenshot oder Beweisbild des Raubes"
    )
    # Annahme: Jeder darf eintragen, daher kein @has_permission
    @log_on_completion
    async def raub_eintragen(self, interaction: discord.Interaction, einsatzleitung: discord.User, verhandlungsfuehrung: discord.User, beweisbild: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        service: RaubService = self.bot.get_cog("RaubService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Raub-Service ist nicht verfügbar.", ephemeral=True)

        # Logik an den Service delegieren
        success, message = await service.create_raub_dokumentation(
            interaction.user, einsatzleitung, verhandlungsfuehrung, beweisbild
        )

        if success:
            await interaction.followup.send(f"✅ {message}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)


    @raub.command(name="statistik", description="Zeigt die Statistik für Einsätze an.")
    @has_permission("raub.statistik") # Euer Permission-System wird hier verwendet
    @log_on_completion
    async def raub_statistik(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False) # Statistik kann öffentlich sein

        service: RaubService = self.bot.get_cog("RaubService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Raub-Service ist nicht verfügbar.", ephemeral=True)

        # Embed vom Service holen und senden
        stats_embed = await service.get_stats_embed()
        await interaction.followup.send(embed=stats_embed)


    @raub.command(name="reset", description="Setzt die gesamte Einsatz-Statistik zurück.")
    @has_permission("raub.reset") # Euer Permission-System wird hier verwendet
    @log_on_completion
    async def raub_reset(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        service: RaubService = self.bot.get_cog("RaubService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Raub-Service ist nicht verfügbar.", ephemeral=True)

        # Reset-Logik im Service aufrufen
        success, message = service.reset_stats()

        if success:
            await interaction.followup.send(f"✅ {message}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)


async def setup(bot: "MyBot"):
    await bot.add_cog(RaubCommands(bot))

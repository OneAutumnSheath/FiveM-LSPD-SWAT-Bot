import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_antrag_service import UprankAntragService
    from services.log_service import LogService
    
class UprankAntragCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="uprank-antrag", description="Erstellt manuell einen Uprank-Antrag aus einer Nachricht.")
    @app_commands.describe(channel="Der Channel der Original-Nachricht", message_id="Die ID der Original-Nachricht")
    @has_permission("uprank.antrag.manual")
    @log_on_completion
    async def uprank_antrag(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
        await interaction.response.defer(ephemeral=True)

        service: UprankAntragService = self.bot.get_cog("UprankAntragService")
        if not service:
            return await interaction.followup.send("❌ Fehler: UprankAntrag-Service nicht gefunden.", ephemeral=True)

        if channel.id not in service.channel_map:
            return await interaction.followup.send("❌ Dieser Channel ist nicht als Quell-Channel definiert.", ephemeral=True)

        try:
            message = await channel.fetch_message(int(message_id))
        except (ValueError, discord.NotFound):
            return await interaction.followup.send("❌ Nachricht nicht gefunden. Bitte überprüfe die Message-ID.", ephemeral=True)
        
        # Rufe die zentrale Logik-Methode im Service auf
        await service.create_uprank_request(message)
        
        await interaction.followup.send("✅ Uprank-Antrag wurde erfolgreich erstellt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankAntragCommands(bot))
import discord
from discord import app_commands, Interaction
from discord.ext import commands
from typing import TYPE_CHECKING, Optional
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.week_separation_service import WeekSeparationService

class WeekSeparationCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="wochentrennung", description="Sendet eine Wochentrennung-Nachricht.")
    @app_commands.describe(
        channel="Optional: Sende die Trennung nur in diesen Kanal, anstatt in alle."
    )
    @has_permission("wochentrennung.send")
    @log_on_completion
    async def send_week_separation(self, interaction: Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer(ephemeral=True)

        service: WeekSeparationService = self.bot.get_cog("WeekSeparationService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Der Wochentrennungs-Service ist nicht verfügbar.", ephemeral=True)

        # Übergebe den optionalen Kanal an den Service
        sent_channels = await service.send_separation_message(target_channel=channel)

        if sent_channels:
            channel_mentions = [c.mention for c in sent_channels]
            confirmation_message = f"✅ Die Wochentrennung wurde in die folgenden Kanäle gesendet: {', '.join(channel_mentions)}"
            await interaction.followup.send(confirmation_message, ephemeral=True)
        else:
            await interaction.followup.send("❌ Fehler: Es konnte in keinen der angegebenen Kanäle gesendet werden.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(WeekSeparationCommands(bot))
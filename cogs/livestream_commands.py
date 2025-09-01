# bot/cogs/livestream_commands.py

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from typing import TYPE_CHECKING

# HIER WURDE DER NEUE IMPORT HINZUGEFÜGT
from utils.decorators import has_permission

if TYPE_CHECKING:
    from main import MyBot
    from services.livestream_service import LiveStreamService

class LiveStreamCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="test_streams", description="Manueller Check für alle gespeicherten Streamer.")
    @has_permission("livestream.test") # HIER WURDE DER DECORATOR GEÄNDERT
    async def test_streams(self, interaction: Interaction):
        await interaction.response.send_message("🔁 Streams werden manuell überprüft...", ephemeral=True)
        service: "LiveStreamService" = self.bot.get_cog("LiveStreamService")
        if service:
            await service.trigger_check()
            await interaction.followup.send("✅ Manuelle Überprüfung abgeschlossen!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Fehler: LiveStream-Service nicht gefunden.", ephemeral=True)

    streamer_group = app_commands.Group(name="streamer", description="Verwaltet die Streamer-Benachrichtigungen.")

    @streamer_group.command(name="add", description="Fügt einen Streamer hinzu, der überwacht wird.")
    @app_commands.describe(
        platform="Die Plattform des Streamers",
        channel_id="Der Name (Twitch) oder die ID (YouTube) des Kanals",
        user="Der Discord-Nutzer, der dem Stream zugeordnet ist"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="YouTube", value="youtube")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def add_streamer(self, interaction: Interaction, platform: str, channel_id: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        service: "LiveStreamService" = self.bot.get_cog("LiveStreamService")
        if service:
            await service.add_streamer(platform, channel_id, user.id)
            await interaction.followup.send(f"✅ **{user.display_name}** wird jetzt für den {platform.capitalize()}-Kanal **{channel_id}** überwacht.")
        else:
            await interaction.followup.send("❌ Fehler: LiveStream-Service nicht gefunden.", ephemeral=True)

    @streamer_group.command(name="remove", description="Entfernt einen Streamer aus der Überwachung.")
    @app_commands.describe(
        platform="Die Plattform des Streamers",
        channel_id="Der Name (Twitch) oder die ID (YouTube) des Kanals"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="YouTube", value="youtube")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_streamer(self, interaction: Interaction, platform: str, channel_id: str):
        await interaction.response.defer(ephemeral=True)
        service: "LiveStreamService" = self.bot.get_cog("LiveStreamService")
        if service:
            await service.remove_streamer(platform, channel_id)
            await interaction.followup.send(f"🗑️ Der {platform.capitalize()}-Streamer **{channel_id}** wird nicht mehr überwacht.")
        else:
            await interaction.followup.send("❌ Fehler: LiveStream-Service nicht gefunden.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(LiveStreamCommands(bot))
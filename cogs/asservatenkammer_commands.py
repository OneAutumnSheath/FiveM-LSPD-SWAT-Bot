# bot/cogs/asservatenkammer_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import yaml
import asyncio
from typing import TYPE_CHECKING, Dict, Any

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.asservatenkammer_service import AsservatenkammerService

class AsservatenkammerModal(discord.ui.Modal, title="Beschlagnahmung einreichen"):
    konfisziert_am = discord.ui.TextInput(label="Konfisziert am", placeholder="TT.MM.JJJJ (leer = heute)", required=False)
    taeter = discord.ui.TextInput(label="Täter", placeholder="leer = Unbekannt", required=False)
    beschlagnahmt = discord.ui.TextInput(label="Beschlagnahmt", placeholder="Was wurde beschlagnahmt?", required=True, style=discord.TextStyle.paragraph)
    ausgefuehrt_fuer = discord.ui.TextInput(label="Ausgeführt für (Name)", placeholder="Leer = für dich selbst", required=False)

    def __init__(self, commands_cog: "AsservatenkammerCommands"):
        super().__init__()
        self.commands_cog = commands_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: AsservatenkammerService = interaction.client.get_cog("AsservatenkammerService")
        if not service: return await interaction.followup.send("Fehler: Service nicht gefunden.", ephemeral=True)

        try:
            konf_raw = self.konfisziert_am.value.strip()
            konf_date = datetime.strptime(konf_raw, "%d.%m.%Y").strftime("%d.%m.%Y") if konf_raw else datetime.now().strftime("%d.%m.%Y")
        except ValueError:
            return await interaction.followup.send("❌ Ungültiges Datumsformat! Bitte TT.MM.JJJJ verwenden.", ephemeral=True)

        data = {
            "konf_date": konf_date,
            "taeter": self.taeter.value.strip() or "Unbekannt",
            "beschlagnahmt": self.beschlagnahmt.value.strip(),
            "wenn_fuer": self.ausgefuehrt_fuer.value.strip()
        }

        result = await service.create_beschlagnahmung(interaction, data)
        if result.get("success"):
            await interaction.followup.send("✅ Deine Beschlagnahmung wurde eingereicht.", ephemeral=True)
            await self.commands_cog._setup_panel_for_guild(interaction.guild.id)
        else:
            error_msg = result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

class AuslagerungLeitungModal(discord.ui.Modal, title="Auslagerung einreichen"):
    ausgelagert_am = discord.ui.TextInput(label="Ausgelagert am", placeholder="TT.MM.JJJJ (leer = heute)", required=False)
    taeter = discord.ui.TextInput(label="Täter", placeholder="leer = Unbekannt", required=False)
    beschlagnahmt = discord.ui.TextInput(label="Beschlagnahmt", placeholder="Was wurde beschlagnahmt?", required=True, style=discord.TextStyle.paragraph)
    ausgefuehrt_fuer = discord.ui.TextInput(label="Ausgeführt für (Name)", placeholder="Leer = für dich selbst", required=False)
    grund = discord.ui.TextInput(label="Grund", placeholder="Warum wurde ausgelagert?", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, commands_cog: "AsservatenkammerCommands"):
        super().__init__()
        self.commands_cog = commands_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: AsservatenkammerService = interaction.client.get_cog("AsservatenkammerService")
        if not service: return await interaction.followup.send("Fehler: Service nicht gefunden.", ephemeral=True)

        try:
            datum_raw = self.ausgelagert_am.value.strip()
            datum = datetime.strptime(datum_raw, "%d.%m.%Y").strftime("%d.%m.%Y") if datum_raw else datetime.now().strftime("%d.%m.%Y")
        except ValueError:
            return await interaction.followup.send("❌ Ungültiges Datumsformat! Bitte TT.MM.JJJJ verwenden.", ephemeral=True)
        
        data = {
            "datum": datum,
            "taeter": self.taeter.value.strip() or "Unbekannt",
            "beschlagnahmt": self.beschlagnahmt.value.strip(),
            "wenn_fuer": self.ausgefuehrt_fuer.value.strip(),
            "grund": self.grund.value.strip()
        }

        result = await service.create_auslagerung(interaction, data)
        if result.get("success"):
            await interaction.followup.send("✅ Deine Auslagerung wurde eingereicht.", ephemeral=True)
            await self.commands_cog._setup_panel_for_guild(interaction.guild.id)
        else:
            error_msg = result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

class AsservatenkammerButtonView(discord.ui.View):
    def __init__(self, commands_cog: "AsservatenkammerCommands"):
        super().__init__(timeout=None)
        self.commands_cog = commands_cog

    @discord.ui.button(label="Beschlagnahmung einreichen", style=discord.ButtonStyle.danger, custom_id="asservatenkammer_modal_v4")
    @has_permission("asservatenkammer.beschlagnahmung")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AsservatenkammerModal(self.commands_cog))

    @discord.ui.button(label="Auslagerung einreichen", style=discord.ButtonStyle.secondary, custom_id="asservatenkammer_auslagerung_v4")
    @has_permission("asservatenkammer.auslagerung")
    async def auslagerung_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuslagerungLeitungModal(self.commands_cog))

class AsservatenkammerCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self._config = self._load_config()
        self._initial_panel_deployment_done = False
        self.bot.add_view(AsservatenkammerButtonView(self))
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/asservatenkammer_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError: 
            return {}

    def _get_server_config(self, guild_id: int) -> Dict[str, Any]:
        """Holt die Konfiguration für einen spezifischen Server."""
        servers = self._config.get('servers', {})
        return servers.get(str(guild_id), {})

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._initial_panel_deployment_done:
            await asyncio.sleep(5)
            await self._setup_all_panels()
            self._initial_panel_deployment_done = True
            print("[INFO] Asservatenkammer-Panels wurden für alle konfigurierten Server gesetzt/aktualisiert.")

    async def _setup_all_panels(self):
        """Setzt die Panels für alle konfigurierten Server."""
        service: AsservatenkammerService = self.bot.get_cog("AsservatenkammerService")
        if not service:
            print("[FEHLER] AsservatenkammerService nicht gefunden.")
            return
            
        configured_guilds = service.get_all_configured_guilds()
        for guild_id in configured_guilds:
            await self._setup_panel_for_guild(guild_id)

    async def _setup_panel_for_guild(self, guild_id: int):
        """Setzt das Panel für eine spezifische Guild."""
        server_config = self._get_server_config(guild_id)
        channel_id = server_config.get('channel_id')
        
        if not channel_id:
            print(f"[WARNUNG] Kein channel_id für Guild {guild_id} konfiguriert.")
            return
            
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"[FEHLER] Asservatenkammer-Channel {channel_id} für Guild {guild_id} nicht gefunden.")
            return

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else str(guild_id)

        try:
            # Alte Nachrichten mit Buttons löschen
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.components:
                    await msg.delete()
        except discord.Forbidden:
            print(f"[FEHLER] Keine Berechtigung zum Löschen von Nachrichten im Asservatenkammer-Channel von {guild_name}.")
        
        # Server-spezifischer Titel
        server_name = server_config.get('name', guild_name)
        
        embed = discord.Embed(
            title=f"📦 {server_name} - Asservatenkammer",
            description="Klicke auf einen der Buttons, um eine **Beschlagnahmung** oder **Auslagerung** einzureichen.",
            color=discord.Color.from_rgb(128, 73, 42)
        )
        
        try:
            await channel.send(embed=embed, view=AsservatenkammerButtonView(self))
            print(f"[INFO] Asservatenkammer-Panel für {guild_name} wurde gesetzt.")
        except discord.Forbidden:
            print(f"[FEHLER] Keine Berechtigung zum Senden von Nachrichten im Asservatenkammer-Channel von {guild_name}.")
    
    @app_commands.command(name="asservatenkammer-reset", description="Setzt das Asservatenkammer-Panel für diesen Server neu (Admin).")
    @has_permission("asservatenkammer.reset")
    @log_on_completion
    async def reset_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            return await interaction.followup.send("❌ Dieser Befehl kann nur in einem Server verwendet werden.", ephemeral=True)
            
        await self._setup_panel_for_guild(interaction.guild.id)
        await interaction.followup.send("✅ Panel wurde für diesen Server neu gesetzt.", ephemeral=True)

    @app_commands.command(name="asservatenkammer-reset-all", description="Setzt alle Asservatenkammer-Panels neu (Super-Admin).")
    @has_permission("asservatenkammer.reset_all")
    @log_on_completion
    async def reset_all_panels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._setup_all_panels()
        await interaction.followup.send("✅ Alle Panels wurden neu gesetzt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(AsservatenkammerCommands(bot))
# bot/cogs/asservatenkammer_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import yaml
import asyncio
from typing import TYPE_CHECKING

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
            await self.commands_cog._setup_panel()
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
            await self.commands_cog._setup_panel()
        else:
            error_msg = result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

class AsservatenkammerButtonView(discord.ui.View):
    def __init__(self, commands_cog: "AsservatenkammerCommands"):
        super().__init__(timeout=None)
        self.commands_cog = commands_cog

    @discord.ui.button(label="Beschlagnahmung einreichen", style=discord.ButtonStyle.danger, custom_id="asservatenkammer_modal_v3")
    @has_permission("asservatenkammer.beschlagnahmung")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AsservatenkammerModal(self.commands_cog))

    @discord.ui.button(label="Auslagerung einreichen", style=discord.ButtonStyle.secondary, custom_id="asservatenkammer_auslagerung_v3")
    @has_permission("asservatenkammer.auslagerung")
    async def auslagerung_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuslagerungLeitungModal(self.commands_cog))

class AsservatenkammerCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self._config = self._load_config()
        self._initial_panel_deployment_done = False
        self.bot.add_view(AsservatenkammerButtonView(self))
    
    def _load_config(self) -> dict:
        try:
            with open('config/asservatenkammer_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError: return {}

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._initial_panel_deployment_done:
            await asyncio.sleep(5)
            await self._setup_panel()
            self._initial_panel_deployment_done = True
            print("[INFO] Asservatenkammer-Panel wurde gesetzt/aktualisiert.")

    async def _setup_panel(self):
        channel_id = self._config.get('channel_id')
        if not channel_id or not (channel := self.bot.get_channel(channel_id)):
            print(f"[FEHLER] Asservatenkammer-Channel in der Config nicht gefunden.")
            return

        try:
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.components:
                    await msg.delete()
        except discord.Forbidden:
            print(f"[FEHLER] Keine Berechtigung zum Löschen von Nachrichten im Asservatenkammer-Channel.")
        
        embed = discord.Embed(
            title="📦 Asservatenkammer",
            description="Klicke auf einen der Buttons, um eine **Beschlagnahmung** oder **Auslagerung** einzureichen.",
            color=discord.Color.from_rgb(128, 73, 42)
        )
        await channel.send(embed=embed, view=AsservatenkammerButtonView(self))
    
    @app_commands.command(name="asservatenkammer-reset", description="Setzt das Asservatenkammer-Panel neu (Admin).")
    @has_permission("asservatenkammer.reset")
    @log_on_completion
    async def reset_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._setup_panel()
        await interaction.followup.send("✅ Panel wurde neu gesetzt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(AsservatenkammerCommands(bot))
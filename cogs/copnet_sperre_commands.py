# bot/cogs/copnet_sperre_commands.py

import discord
from discord import app_commands, Interaction
from discord.ext import commands
import yaml
from typing import TYPE_CHECKING
import asyncio

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.copnet_sperre_service import CopnetSperreService

# --- Konstante für den Panel-Titel ---
PANEL_TITLE = "Copnet-Sperrungen"

class SperreMeldenModal(discord.ui.Modal, title="Copnet-Sperrung melden"):
    target_dn = discord.ui.TextInput(label="Dienstnummer (DN)", placeholder="DN des gesperrten Mitglieds", required=True)
    reason = discord.ui.TextInput(label="Warum?", style=discord.TextStyle.paragraph, placeholder="Grund für die Sperrung", required=True)
    log_link = discord.ui.TextInput(label="Log-Link", placeholder="Link zum relevanten Log-Eintrag", required=True)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: "CopnetSperreService" = interaction.client.get_cog("CopnetSperreService")
        cog_instance: "CopnetSperreCommands" = interaction.client.get_cog("CopnetSperreCommands")

        if not service or not cog_instance:
            return await interaction.followup.send("❌ Interner Fehler: Einer der benötigten Cogs wurde nicht gefunden.", ephemeral=True)

        try:
            with open('config/copnet_sperre_config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                log_channel_id = config.get('log_channel_id')
        except (FileNotFoundError, AttributeError):
            return await interaction.followup.send("❌ Fehler: Log-Kanal in der Config nicht gefunden.", ephemeral=True)
        
        log_channel = interaction.client.get_channel(log_channel_id)
        if not log_channel:
            return await interaction.followup.send(f"❌ Log-Kanal mit ID `{log_channel_id}` nicht gefunden.", ephemeral=True)

        await cog_instance._delete_old_panels(interaction.channel)

        embed = discord.Embed(
            title="Neue Copnet-Sperrung",
            color=discord.Color.red()
        )
        embed.add_field(name="Dienstnummer", value=self.target_dn.value, inline=False)
        embed.add_field(name="Grund", value=self.reason.value, inline=False)
        embed.add_field(name="Log-Link", value=self.log_link.value, inline=False)
        embed.set_footer(text=f"Ausgeführt von: {interaction.user.nick or interaction.user.name}")
        
        sent_message = await log_channel.send(embed=embed, view=AufhebenView())
        
        await service.create_sperre(
            message_id=sent_message.id,
            requester=interaction.user,
            target_dn=self.target_dn.value,
            reason=self.reason.value,
            log_link=self.log_link.value
        )
        
        await cog_instance._send_new_panel(interaction.channel)
        
        await interaction.followup.send(f"✅ Copnet-Sperrung wurde in {log_channel.mention} erfasst.", ephemeral=True)
        

class EinreichenPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Copnet-Sperrung eintragen", style=discord.ButtonStyle.danger, custom_id="copnet_sperre_eintragen_v1")
    @has_permission("copnet.sperre.erstellen")
    async def eintragen(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SperreMeldenModal())
        
class AufhebenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Sperrung aufheben", style=discord.ButtonStyle.secondary, custom_id="copnet_sperre_aufheben_v1")
    @has_permission("copnet.sperre.aufheben")
    async def aufheben(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service: "CopnetSperreService" = interaction.client.get_cog("CopnetSperreService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Service nicht gefunden.", ephemeral=True)
        
        await service.lift_sperre(interaction.message.id)
        
        original_embed = interaction.message.embeds[0]
        original_embed.title = "Sperre aufgehoben"
        original_embed.color = discord.Color.light_grey()
        
        button.disabled = True
        button.label = "Aufgehoben"
        
        await interaction.message.edit(embed=original_embed, view=self)
        await interaction.followup.send("✅ Sperre wurde aufgehoben.", ephemeral=True)

class CopnetSperreCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.bot.add_view(EinreichenPanelView())
        self.bot.add_view(AufhebenView())
        self._initial_panel_deployment_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._initial_panel_deployment_done:
            await asyncio.sleep(5) 
            print("Starte automatisches Deployment des Copnet-Sperre-Panels...")
            await self.deploy_panel_on_startup()
            self._initial_panel_deployment_done = True
            print("Automatisches Deployment des Copnet-Sperre-Panels abgeschlossen.")

    async def deploy_panel_on_startup(self):
        try:
            with open('config/copnet_sperre_config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                channel_id = config.get('panel_channel_id')
        except (FileNotFoundError, AttributeError):
            print("[FEHLER] Copnet-Panel Startup: Konfigurationsdatei oder `panel_channel_id` nicht gefunden.")
            return

        if not channel_id:
            print("[WARNUNG] Copnet-Panel Startup: `panel_channel_id` ist nicht in der Config gesetzt.")
            return
            
        channel = self.bot.get_channel(channel_id)
        if channel:
            await self._deploy_panel(channel)
        else:
            print(f"[FEHLER] Copnet-Panel Startup: Kanal mit ID {channel_id} nicht gefunden.")

    async def _delete_old_panels(self, channel: discord.TextChannel):
        """Löscht alte Panels basierend auf dem Embed-Titel."""
        try:
            async for message in channel.history(limit=20):
                if message.author == self.bot.user and message.embeds and message.embeds[0].title == PANEL_TITLE:
                    await message.delete()
                    # break # beendet die Schleife nach dem ersten Fund
        except Exception as e:
            print(f"Fehler beim Löschen des alten Copnet-Panels: {e}")

    async def _send_new_panel(self, channel: discord.TextChannel):
        """Sendet ein neues Panel."""
        embed = discord.Embed(title=PANEL_TITLE, description="Klicke hier, um eine neue Sperrung zu melden.", color=discord.Color.dark_grey())
        await channel.send(embed=embed, view=EinreichenPanelView())

    async def _deploy_panel(self, channel: discord.TextChannel):
        """Löscht alte Panels und postet ein neues, damit es unten steht."""
        await self._delete_old_panels(channel)
        await self._send_new_panel(channel)

    @app_commands.command(name="copnet-panel", description="Setzt das Panel für Copnet-Sperrungen.")
    @has_permission("copnet.sperre.setup")
    @log_on_completion
    async def setup_panel(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            with open('config/copnet_sperre_config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                channel_id = config.get('panel_channel_id')
        except (FileNotFoundError, AttributeError):
            return await interaction.followup.send("❌ Fehler: `panel_channel_id` in der Config nicht gefunden.", ephemeral=True)
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return await interaction.followup.send(f"❌ Panel-Kanal mit ID `{channel_id}` nicht gefunden.", ephemeral=True)
        
        await self._deploy_panel(channel)
        await interaction.followup.send(f"✅ Panel für Copnet-Sperrungen wurde in {channel.mention} erstellt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(CopnetSperreCommands(bot))
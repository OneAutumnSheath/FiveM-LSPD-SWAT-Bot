# bot/cogs/uprank_antrag_commands.py

import discord
from discord import app_commands, Interaction
from discord.ext import commands
import yaml
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any, List
import asyncio

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_antrag_service import UprankAntragService

class HistoryPaginationView(discord.ui.View):
    def __init__(self, interaction: Interaction, title: str, results: List[Dict[str, Any]]):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.title = title
        self.results = results
        self.current_page = 0
        self.items_per_page = 5
        self.total_pages = math.ceil(len(self.results) / self.items_per_page) if self.results else 1
    async def show_page(self, page_number: int):
        self.current_page = page_number
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page
        embed = discord.Embed(title=self.title, color=discord.Color.blurple())
        if not self.results:
            embed.description = "Keine Einträge gefunden."
        else:
            status_map = {"pending": "⏳ Ausstehend", "approved": "✅ Genehmigt", "rejected": "❌ Abgelehnt", "deleted": "🗑️ Gelöscht"}
            for item in self.results[start_index:end_index]:
                timestamp = int(item['created_at'].timestamp())
                status = status_map.get(item['status'], "❓ Unbekannt")
                requester_id = item['requester_id']
                target_id = item['target_user_id']
                field_name = f"{status} | <t:{timestamp}:d>"
                field_value = (f"**Antrag für:** <@{target_id}> (DN: {item['target_dn']})\n"
                               f"**Eingereicht von:** <@{requester_id}>\n"
                               f"**Grund:** {item['reason'][:150]}")
                embed.add_field(name=field_name, value=field_value, inline=False)
        embed.set_footer(text=f"Seite {self.current_page + 1} / {self.total_pages}")
        self.update_buttons()
        if self.interaction.response.is_done(): await self.interaction.edit_original_response(embed=embed, view=self)
        else: await self.interaction.response.send_message(embed=embed, view=self, ephemeral=True)
    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages - 1
    @discord.ui.button(label="Zurück", style=discord.ButtonStyle.grey)
    async def previous_page(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.show_page(self.current_page - 1)
    @discord.ui.button(label="Weiter", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.show_page(self.current_page + 1)

class Div1AntragModal(discord.ui.Modal, title="Rangänderungsantrag (Div 1)"):
    target_dn = discord.ui.TextInput(label="Dienstnummer des Soldaten", placeholder="z.B. 123", required=True)
    new_rank_key = discord.ui.TextInput(label="Neuer Rank-Key", placeholder="Ganze Zahl, z.B. 5 für Sergeant", required=True)
    unit_name = discord.ui.TextInput(label="Einheit des Soldaten", placeholder="z.B. Infantry", required=True)
    begruendung = discord.ui.TextInput(label="Begründung", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    def __init__(self, commands_cog: "UprankAntragCommands"):
        super().__init__()
        self.commands_cog = commands_cog
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        service: "UprankAntragService" = interaction.client.get_cog("UprankAntragService")
        try: rank_key_int = int(self.new_rank_key.value)
        except ValueError:
            await interaction.followup.send("❌ **Fehler:** Der Rank-Key muss eine ganze Zahl sein.", ephemeral=True)
            return
        result = await service.create_uprank_request(interaction=interaction, commands_cog=self.commands_cog, target_dn=self.target_dn.value, new_rank_key=rank_key_int, reason=self.begruendung.value, unit_name=self.unit_name.value)
        message = result.get("message") if result.get("success") else result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
        await interaction.followup.send(f'{"✅" if result.get("success") else "❌"} {message}', ephemeral=True)

class UnitAntragModal(discord.ui.Modal, title="Rangänderungsantrag für Einheit"):
    target_dn = discord.ui.TextInput(label="Dienstnummer des Soldaten", placeholder="z.B. 45", required=True)
    new_rank_key = discord.ui.TextInput(label="Neuer Rank-Key", placeholder="Ganze Zahl, z.B. 5 für Sergeant", required=True)
    begruendung = discord.ui.TextInput(label="Begründung", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    def __init__(self, unit_name: str, commands_cog: "UprankAntragCommands"):
        super().__init__()
        self.unit_name = unit_name
        self.commands_cog = commands_cog
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        service: "UprankAntragService" = interaction.client.get_cog("UprankAntragService")
        try: rank_key_int = int(self.new_rank_key.value)
        except ValueError:
            await interaction.followup.send("❌ **Fehler:** Der Rank-Key muss eine ganze Zahl sein.", ephemeral=True)
            return
        result = await service.create_uprank_request(interaction=interaction, commands_cog=self.commands_cog, target_dn=self.target_dn.value, new_rank_key=rank_key_int, reason=self.begruendung.value, unit_name=self.unit_name)
        message = result.get("message") if result.get("success") else result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
        await interaction.followup.send(f'{"✅" if result.get("success") else "❌"} {message}', ephemeral=True)

class UprankAntragPanelView(discord.ui.View):
    def __init__(self, commands_cog: "UprankAntragCommands", channel_id: int):
        super().__init__(timeout=None)
        self.commands_cog = commands_cog
        try:
            with open('config/uprank_antrag_config.yaml', 'r', encoding='utf-8') as f: self.config = yaml.safe_load(f)
        except FileNotFoundError: self.config = {}
        div1_channel_id = self.config.get('division_1_channel_id')
        unit_channels = self.config.get('unit_map', {}).keys()
        if channel_id == div1_channel_id: self.add_item(self.Div1Button(self.commands_cog))
        elif channel_id in unit_channels:
            unit_name = self.config['unit_map'][channel_id]
            self.add_item(self.UnitButton(self.commands_cog, unit_name))

    class Div1Button(discord.ui.Button):
        def __init__(self, commands_cog: "UprankAntragCommands"):
            super().__init__(label="Rangänderung beantragen", style=discord.ButtonStyle.primary, custom_id="rank_change_div1_v6")
            self.commands_cog = commands_cog
        @has_permission("uprank.antrag.div1")
        async def callback(self, interaction: Interaction):
            await interaction.response.send_modal(Div1AntragModal(commands_cog=self.commands_cog))

    class UnitButton(discord.ui.Button):
        def __init__(self, commands_cog: "UprankAntragCommands", unit_name: str):
            super().__init__(label="Rangänderung beantragen", style=discord.ButtonStyle.secondary, custom_id=f"rank_change_unit_v6_{unit_name.replace(' ', '_')}")
            self.commands_cog = commands_cog
            self.unit_name = unit_name
        @has_permission("uprank.antrag.unit")
        async def callback(self, interaction: Interaction):
            await interaction.response.send_modal(UnitAntragModal(unit_name=self.unit_name, commands_cog=self.commands_cog))

class UprankAntragCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self._initial_panel_deployment_done = False
    @commands.Cog.listener()
    async def on_ready(self):
        if not self._initial_panel_deployment_done:
            await asyncio.sleep(5)
            print("Starte automatisches Deployment der Rangänderungs-Panels...")
            await self.deploy_all_panels_on_startup()
            self._initial_panel_deployment_done = True
            print("Automatisches Deployment der Rangänderungs-Panels abgeschlossen.")
    async def deploy_all_panels_on_startup(self):
        try:
            with open('config/uprank_antrag_config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f)
        except FileNotFoundError:
            print("[FEHLER] Rangänderungs-Panel Startup: Konfigurationsdatei nicht gefunden.")
            return
        channel_ids = list(config.get('unit_map', {}).keys())
        if div1_id := config.get('division_1_channel_id'):
            if div1_id not in channel_ids: channel_ids.append(div1_id)
        if not channel_ids:
            print("[WARNUNG] Rangänderungs-Panel Startup: Keine Kanäle in der Konfiguration gefunden.")
            return
        for channel_id in channel_ids:
            channel = self.bot.get_channel(int(channel_id))
            if channel: await self._deploy_panel_to_channel(channel)
            else: print(f"[FEHLER] Rangänderungs-Panel Startup: Kanal mit ID {channel_id} nicht gefunden.")
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != '🗑️' or not payload.guild_id or not payload.member or payload.member.bot: return
        service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        if not service or 'proposal_channel_id' not in service.config or payload.channel_id != service.config['proposal_channel_id']: return
        permission_service = self.bot.get_cog("PermissionService")
        if not permission_service or not permission_service.has_permission(payload.member, "uprank.antrag.delete"): return
        result = await service.delete_uprank_request(payload.message_id, requester=payload.member)
        try:
            if result.get("success"): await payload.member.send(f"🗑️ Der Rangänderungsantrag (Nachrichten-ID: {payload.message_id}) wurde erfolgreich gelöscht.", delete_after=15)
            else:
                error_message = result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
                await payload.member.send(f"❌ Fehler beim Löschen des Antrags: {error_message}", delete_after=30)
        except discord.Forbidden: pass
    uprank_verlauf_group = app_commands.Group(name="uprank-verlauf", description="Zeigt den Verlauf von Rangänderungsanträgen an.")
    @uprank_verlauf_group.command(name="benutzer", description="Zeigt den Rangänderungsverlauf für einen bestimmten Soldaten an.")
    @has_permission("uprank.verlauf.view")
    async def verlauf_benutzer(self, interaction: Interaction, soldat: discord.Member):
        service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        history = await service.get_uprank_history_for_user(soldat.id)
        title = f"Rangänderungsverlauf für {soldat.display_name}"
        view = HistoryPaginationView(interaction, title, history)
        await view.show_page(0)
    @uprank_verlauf_group.command(name="woche", description="Zeigt alle Anträge aus einer bestimmten Woche an.")
    @has_permission("uprank.verlauf.view")
    async def verlauf_woche(self, interaction: Interaction, datum: str):
        await interaction.response.defer(ephemeral=True)
        service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        try: date_obj = datetime.strptime(datum, "%d.%m.%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            await interaction.edit_original_response(content="❌ Ungültiges Datumsformat. Bitte benutze `TT.MM.JJJJ`.")
            return
        week_identifier = service.get_week_identifier(date_obj)
        history = await service.get_uprank_history_for_week(week_identifier)
        title = f"Rangänderungsanträge aus Kalenderwoche {week_identifier}"
        view = HistoryPaginationView(interaction, title, history)
        await view.show_page(0)
    uprank_panel_group = app_commands.Group(name="uprank-panel", description="Verwaltet die Antrags-Panels.")
    @uprank_panel_group.command(name="erstellen", description="Postet das Panel in einem spezifischen Kanal.")
    @has_permission("uprank.antrag.admin")
    async def uprank_panel_erstellen(self, interaction: Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        await self._deploy_panel_to_channel(channel)
        await interaction.followup.send(f"✅ Das Rangänderungs-Panel wurde erfolgreich in {channel.mention} erstellt.", ephemeral=True)
    @uprank_panel_group.command(name="deploy-all", description="Postet das Panel in ALLEN konfigurierten Unit-Kanälen.")
    @has_permission("uprank.antrag.admin")
    async def uprank_panel_deploy_all(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            with open('config/uprank_antrag_config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f)
        except FileNotFoundError:
            await interaction.followup.send("❌ Konfigurationsdatei nicht gefunden.", ephemeral=True)
            return
        channel_ids = list(config.get('unit_map', {}).keys())
        if div1_id := config.get('division_1_channel_id'):
            if div1_id not in channel_ids: channel_ids.append(div1_id)
        if not channel_ids:
            await interaction.followup.send("❌ Keine Kanäle in der Konfiguration gefunden.", ephemeral=True)
            return
        successful, failed = [], []
        for channel_id in channel_ids:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await self._deploy_panel_to_channel(channel)
                successful.append(channel.mention)
            else: failed.append(str(channel_id))
        report = f"**Panel-Deployment abgeschlossen:**\n\n✅ **Erfolgreich in {len(successful)} Kanälen:**\n"
        if successful: report += ", ".join(successful)
        if failed: report += f"\n\n❌ **Fehlgeschlagen für {len(failed)} Kanal-IDs:**\n" + ", ".join(failed)
        await interaction.followup.send(report, ephemeral=True)
    async def _deploy_panel_to_channel(self, channel: discord.TextChannel):
        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.components:
                try: await msg.delete()
                except discord.HTTPException: pass
        embed = discord.Embed(title="🎖️ Rangänderungsanträge", description="Reiche hier einen Antrag für eine Rangänderung ein, indem du den passenden Button klickst.", color=discord.Color.gold())
        await channel.send(embed=embed, view=UprankAntragPanelView(self, channel_id=channel.id))

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankAntragCommands(bot))
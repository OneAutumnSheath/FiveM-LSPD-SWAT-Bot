# bot/cogs/sanction_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING, Dict, Any # HIER WURDE DER IMPORT ERWEITERT
import yaml

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.sanction_service import SanctionService
    from services.display_service import DisplayService

class SanktionsantragModal(discord.ui.Modal, title="Sanktionsantrag"):
    dn = discord.ui.TextInput(label="Dienstnummer des Beschuldigten", style=discord.TextStyle.short)
    sanktionsmass = discord.ui.TextInput(label="Sanktionsmaß (inkl. Verwarnungen, z.B. '1. Verwarnung')", style=discord.TextStyle.paragraph)
    paragraphen = discord.ui.TextInput(label="Rechtsgrundlage (§)", style=discord.TextStyle.short)
    sachverhalt = discord.ui.TextInput(label="Sachverhalt", style=discord.TextStyle.paragraph)
    zeugen = discord.ui.TextInput(label="Zeugen", style=discord.TextStyle.short, required=False)

    def __init__(self, bot: "MyBot", parent_message: discord.Message):
        super().__init__()
        self.bot = bot
        self.parent_message = parent_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service: return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)
        
        result = await service.create_sanction_proposal(
            interaction, self.dn.value, self.sanktionsmass.value, self.paragraphen.value,
            self.sachverhalt.value, self.zeugen.value or None
        )

        if not result.get("success"):
            return await interaction.followup.send(f"❌ Fehler: {result.get('error')}", ephemeral=True)
        
        try:
            # DisplayService für den Thread-Namen verwenden
            display_service: DisplayService = self.bot.get_cog("DisplayService")
            if display_service:
                display_name = await display_service.get_display(result['member'], is_footer=True)
                thread_name = f"Sanktion: {display_name}"
            else:
                thread_name = f"Sanktion: {result['member'].display_name}"
            
            thread = await self.parent_message.create_thread(name=thread_name)
            view = GenehmigenView(self.bot, result['member'], result['neue_verwarnungen'], result['sanktionsmass'], interaction.user)
            await thread.send(content=interaction.user.mention, embed=result['embed'], view=view)
            await interaction.followup.send(f"✅ Antrag wurde im Thread {thread.mention} zur Genehmigung eingereicht.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Fehler beim Erstellen des Threads: {e}", ephemeral=True)

class GenehmigenView(discord.ui.View):
    def __init__(self, bot: "MyBot", member: discord.Member, verwarnung: int, sanktionsmaß: str, antragsteller: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
        self.verwarnung = verwarnung
        self.sanktionsmaß = sanktionsmaß
        self.antragsteller = antragsteller
        
        try:
            with open('config/sanctions_config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.berechtigte_rollen_ids = set(config.get('berechtigte_rollen_ids', []))
        except FileNotFoundError:
            self.berechtigte_rollen_ids = set()

    async def _check_perms(self, interaction: discord.Interaction) -> bool:
        if not any(role.id in self.berechtigte_rollen_ids for role in interaction.user.roles):
            await interaction.response.send_message("❌ Du hast keine Berechtigung, über diesen Antrag zu entscheiden.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Genehmigen", style=discord.ButtonStyle.success, custom_id="sanktion_approve_v3")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction): return
        await interaction.response.defer(ephemeral=True)
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service: return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)
        
        await service.approve_sanction(self.member, self.verwarnung, self.sanktionsmaß)

        # DisplayService für die Anzeige verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            executor_display_name = await display_service.get_display(interaction.user, is_footer=True)
        else:
            executor_display_name = interaction.user.display_name

        embed = interaction.message.embeds[0]
        embed.title = f"✅ Antrag genehmigt von {executor_display_name}"
        embed.color = discord.Color.green()
        for item in self.children: item.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.followup.send("Antrag wurde genehmigt.", ephemeral=True)
        await self.antragsteller.send(f"Dein Sanktionsantrag für {self.member.mention} wurde von {interaction.user.mention} **genehmigt**.")

    @discord.ui.button(label="❌ Ablehnen", style=discord.ButtonStyle.danger, custom_id="sanktion_reject_v3")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perms(interaction): return

        # DisplayService für die Anzeige verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            executor_display_name = await display_service.get_display(interaction.user, is_footer=True)
        else:
            executor_display_name = interaction.user.display_name

        embed = interaction.message.embeds[0]
        embed.title = f"❌ Antrag abgelehnt von {executor_display_name}"
        embed.color = discord.Color.dark_red()
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        
        await self.antragsteller.send(f"Dein Sanktionsantrag für {self.member.mention} wurde von {interaction.user.mention} **abgelehnt**.")

class AntragStartView(discord.ui.View):
    def __init__(self, bot: "MyBot"):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="📝 Antrag einreichen", style=discord.ButtonStyle.primary, custom_id="start_sanktionsantrag_v3")
    async def start_antrag(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SanktionsantragModal(self.bot, interaction.message))

class SanctionCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/sanctions_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError: return {}

    async def cog_load(self):
        self.bot.add_view(AntragStartView(self.bot))

    @app_commands.command(name="sanktionsantrag-setup", description="Setzt das Panel für den Sanktionsantrag.")
    @has_permission("sanktion.setup")
    @log_on_completion
    async def setup_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel_id = self._config.get('antrag_channel_id')
        if not channel_id or not (channel := self.bot.get_channel(channel_id)):
            return await interaction.followup.send("❌ Antrag-Channel nicht in der Config gefunden.", ephemeral=True)
        
        async for msg in channel.history(limit=10):
            if msg.author == self.bot.user and msg.components: await msg.delete()
        
        embed = discord.Embed(title="Sanktionsantrag", description="Reiche hier deinen Antrag ein, indem du auf den Button klickst.", color=discord.Color.dark_red())
        await channel.send(embed=embed, view=AntragStartView(self.bot))
        await interaction.followup.send("✅ Setup für Sanktionsanträge erfolgreich.", ephemeral=True)

    @app_commands.command(name="sanktion", description="Erstellt eine einfache Sanktion für einen Benutzer.")
    @app_commands.describe(user="Das Mitglied", sanktionsmass="Die Maßnahme", grund="Der Grund")
    @has_permission("sanktion.create")
    @log_on_completion
    async def sanktion(self, interaction: discord.Interaction, user: discord.Member, sanktionsmass: str, grund: str):
        await interaction.response.defer(ephemeral=True)
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service: return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)

        success = await service.create_simple_sanction(user, sanktionsmass, grund, interaction)
        if success: 
            # DisplayService für die Bestätigungsnachricht verwenden
            display_service: DisplayService = self.bot.get_cog("DisplayService")
            if display_service:
                display_name = await display_service.get_display(user)
            else:
                display_name = user.mention
            await interaction.followup.send(f"✅ Sanktion für {display_name} wurde erfolgreich erstellt.", ephemeral=True)
        else: 
            await interaction.followup.send("❌ Sanktion konnte nicht erstellt werden (Channel nicht gefunden?).", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(SanctionCommands(bot))
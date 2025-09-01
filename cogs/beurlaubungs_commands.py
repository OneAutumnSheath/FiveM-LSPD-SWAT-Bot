# bot/cogs/beurlaubung_commands.py

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from typing import TYPE_CHECKING
import yaml

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.beurlaubung_service import BeurlaubungService

class BeurlaubungEintragenModal(discord.ui.Modal, title="Beurlaubung eintragen"):
    dn = discord.ui.TextInput(
        label="Dienstnummer des Mitglieds",
        placeholder="z.B. 123",
        required=True
    )
    end_datum = discord.ui.TextInput(
        label="Beurlaubt bis",
        placeholder="z.B. Ende der Woche, ca. 2 Wochen, 14.09.2025",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: "BeurlaubungService" = interaction.client.get_cog("BeurlaubungService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Beurlaubung-Service nicht gefunden.", ephemeral=True)

        target_user = await service.get_member_by_dn(interaction.guild, self.dn.value)
        if not target_user:
            return await interaction.followup.send(f"❌ Kein Mitglied mit der Dienstnummer `{self.dn.value}` gefunden.", ephemeral=True)

        result = await service.create_beurlaubung(
            requester=interaction.user,
            target_user=target_user,
            end_datum_text=self.end_datum.value
        )
        
        message = result.get("message") if result.get("success") else result.get("error", "Ein unbekannter Fehler.")
        await interaction.followup.send(f'{"✅" if result.get("success") else "❌"} {message}', ephemeral=True)

class BeurlaubungPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Beurlaubung eintragen", style=discord.ButtonStyle.primary, custom_id="beurlaubung_eintragen_v1")
    @has_permission("beurlaubung.eintragen")
    async def eintragen_button(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BeurlaubungEintragenModal())

class BeurlaubungCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.bot.add_view(BeurlaubungPanelView())

    @app_commands.command(name="beurlaubung-panel", description="Setzt das Panel für die Beurlaubungen.")
    @has_permission("beurlaubung.setup")
    @log_on_completion
    async def setup_panel(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            with open('config/beurlaubung_config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                channel_id = config.get('panel_channel_id')
        except (FileNotFoundError, AttributeError):
            return await interaction.followup.send("❌ Fehler: `panel_channel_id` in der `beurlaubung_config.yaml` nicht gefunden.", ephemeral=True)

        if not channel_id or not (channel := self.bot.get_channel(channel_id)):
            return await interaction.followup.send("❌ Panel-Kanal konnte nicht gefunden werden.", ephemeral=True)

        async for msg in channel.history(limit=10):
            if msg.author == self.bot.user and msg.components:
                await msg.delete()

        embed = discord.Embed(
            title="📝 Beurlaubungen",
            description="Klicke auf den Button, um eine Beurlaubung für ein Mitglied einzutragen.",
            color=discord.Color.dark_teal()
        )
        await channel.send(embed=embed, view=BeurlaubungPanelView())
        await interaction.followup.send(f"✅ Beurlaubungs-Panel wurde in {channel.mention} erstellt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(BeurlaubungCommands(bot))
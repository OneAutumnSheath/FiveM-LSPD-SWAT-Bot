# commands/seal_sanction_commands.py

import discord
from discord.ext import commands
from discord import Interaction, ButtonStyle
from discord.ui import View, Button, Modal, TextInput
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MyBot
    from services.seal_sanction_service import SealSanctionService

# ### HIER ANPASSEN ###
# Trage hier die IDs für deinen Server und die Kanäle ein.
GUILD_ID = 1097625621875675188  # Die ID des Servers, auf dem das System läuft
SANCTION_SUBMIT_CHANNEL_ID = 1395432517581934713 # Kanal für interne Anträge mit Button
SANCTION_ANNOUNCE_CHANNELS = [1267535561883648001, 1398998200819384442] # Kanäle für öffentliche Bekanntmachung
ROLE_REMOVE_ALLOWED = [1331306902897823745] # Rollen, die Sanktionen entfernen dürfen (z.B. Management)
# ### ENDE ANPASSEN ###

PANEL_TITLE = "SEALs Sanktions-Panel"

# --- UI Klassen ---
class RemoveSanctionView(View):
    def __init__(self, member_id: int):
        super().__init__(timeout=None)
        self.add_item(Button(label="Sanktion entfernen", style=ButtonStyle.danger, custom_id=f"remove_seal_sanction_{member_id}"))

class SealSanktionsantragModal(Modal):
    def __init__(self, cog: "SealSanctionCommands", deckname_value=""):
        super().__init__(title="Sanktionsantrag einreichen")
        self.cog = cog

        self.deckname = TextInput(label="Deckname", style=discord.TextStyle.short, max_length=100, default=deckname_value)
        self.sanktionsmass = TextInput(label="Sanktionsmaß (z.B. '1. Verwarnung')", style=discord.TextStyle.paragraph, max_length=500)
        self.paragraphen = TextInput(label="Rechtsgrundlage (§)", style=discord.TextStyle.short, max_length=45)
        self.sachverhalt = TextInput(label="Sachverhalt", style=discord.TextStyle.paragraph, max_length=1000)
        self.zeugen = TextInput(label="Zeugen", style=discord.TextStyle.short, required=False, max_length=100)

        for item in [self.deckname, self.sanktionsmass, self.paragraphen, self.sachverhalt, self.zeugen]:
            self.add_item(item)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: SealSanctionService = self.cog.bot.get_cog("SealSanctionService")
        if not service:
            return await interaction.followup.send("Fehler: Der Sanktions-Service ist nicht verfügbar.", ephemeral=True)

        result = await service.submit_sanction(
            interaction, self.deckname.value.strip(), self.sanktionsmass.value,
            self.paragraphen.value, self.sachverhalt.value, self.zeugen.value
        )

        if not result.get("success"):
            return await interaction.followup.send(f"❌ Fehler: {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        member = result["member"]
        embed = discord.Embed(title="📄 Neue SEAL-Sanktion", color=discord.Color.orange())
        embed.add_field(name="Sanktioniertes Mitglied", value=member.mention, inline=False)
        embed.add_field(name="Sanktionsmaß", value=self.sanktionsmass.value, inline=False)
        embed.add_field(name="Rechtsgrundlage (§)", value=self.paragraphen.value, inline=False)
        embed.add_field(name="Sachverhalt", value=self.sachverhalt.value, inline=False)
        if self.zeugen.value:
            embed.add_field(name="Zeugen", value=self.zeugen.value, inline=False)
        embed.set_footer(text=f"Eingereicht von {interaction.user.display_name}")

        for channel_id in SANCTION_ANNOUNCE_CHANNELS:
            if channel := self.cog.bot.get_channel(channel_id):
                await channel.send(embed=embed)
                if result.get("meldung"):
                    await channel.send(result["meldung"])
        
        if submit_channel := interaction.guild.get_channel(SANCTION_SUBMIT_CHANNEL_ID):
            view = RemoveSanctionView(member.id)
            await submit_channel.send(embed=embed, view=view)
            await self.cog.create_or_update_panel(submit_channel)

        await interaction.followup.send("✅ Sanktionsantrag erfolgreich eingereicht.", ephemeral=True)

class SealSanctionCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.bot.add_view(RemoveSanctionView(0))
        self.bot.add_view(self._create_panel_view())

    def _create_panel_view(self) -> View:
        view = View(timeout=None)
        view.add_item(Button(label="Sanktionsantrag einreichen", style=ButtonStyle.primary, custom_id="open_sanktionsmodal"))
        return view

    async def create_or_update_panel(self, channel: discord.TextChannel):
        try:
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.embeds and message.embeds[0].title == PANEL_TITLE:
                    await message.delete()
                    break
        except Exception as e:
            print(f"Fehler beim Löschen des alten SEALs-Sanktions-Panels: {e}")
        
        embed = discord.Embed(title=PANEL_TITLE, description="Klicke auf den Button, um einen Sanktionsantrag einzureichen.", color=discord.Color.blue())
        await channel.send(embed=embed, view=self._create_panel_view())
        print("SEALs Sanktions-Panel wurde erfolgreich erstellt/aktualisiert.")

    @commands.Cog.listener()
    async def on_ready(self):
        # Warten, bis der Bot vollständig bereit ist
        await self.bot.wait_until_ready()
        if channel := self.bot.get_channel(SANCTION_SUBMIT_CHANNEL_ID):
            await self.create_or_update_panel(channel)
        else:
            print(f"[WARN] Seal-Sanktion Submit-Channel mit ID {SANCTION_SUBMIT_CHANNEL_ID} nicht gefunden.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id: return

        service: SealSanctionService = self.bot.get_cog("SealSanctionService")
        if not service:
            # Sende eine Fehlermeldung, falls der Service nicht geladen ist
            error_message = "Fehler: Der Sanktions-Service ist nicht verfügbar."
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)
            return

        if custom_id == "open_sanktionsmodal":
            await interaction.response.send_modal(SealSanktionsantragModal(self))
            return

        if custom_id.startswith("remove_seal_sanction_"):
            is_allowed = await service.has_remove_permission(interaction, ROLE_REMOVE_ALLOWED)
            if not is_allowed:
                return await interaction.response.send_message("❌ Du hast keine Berechtigung für diese Aktion.", ephemeral=True)

            await interaction.response.defer(ephemeral=True)
            try:
                member_id = int(custom_id.split('_')[3])
            except (IndexError, ValueError):
                return await interaction.followup.send("Fehler: Ungültige Button-ID.", ephemeral=True)

            result = await service.remove_sanction(member_id)

            if result.get("success"):
                embed = interaction.message.embeds[0]
                embed.title = "❌ Sanktion entfernt"
                embed.color = discord.Color.dark_grey()
                embed.set_footer(text=f"Entfernt von {interaction.user.display_name}")
                await interaction.message.edit(embed=embed, view=None)

                guild = self.bot.get_guild(GUILD_ID)
                member = guild.get_member(member_id) if guild else None
                mention = member.mention if member else f"User-ID `{member_id}`"
                await interaction.followup.send(f"✅ Sanktion von {mention} wurde entfernt.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Fehler beim Entfernen: {result.get('error', 'Unbekannt')}", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(SealSanctionCommands(bot))
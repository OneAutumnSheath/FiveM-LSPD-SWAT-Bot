import discord
from discord.ext import commands
from discord import app_commands, ButtonStyle
from discord.ui import View, Button, Modal, TextInput
from typing import TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from main import MyBot
    from services.seal_sanction_service import SealSanctionService
    from services.log_service import LogService
    
# --- Konstanten ---
SANCTION_SUBMIT_CHANNEL_ID = 1395432517581934713

# --- UI Klassen ---
class RemoveSanctionView(discord.ui.View):
    def __init__(self, member_id: int):
        super().__init__(timeout=None)
        # Wir brauchen die Rollen-ID nicht mehr im Button, da der Service sie aus der DB holt
        self.add_item(Button(label="Sanktion entfernen", style=ButtonStyle.danger, custom_id=f"remove_seal_sanction_{member_id}"))

class SealSanktionsantragModal(discord.ui.Modal, title="Sanktionsantrag einreichen"):
    deckname = TextInput(label="Deckname", style=discord.TextStyle.short, max_length=100)
    sanktionsmaß = TextInput(label="Sanktionsmaß (frei formuliert)", style=discord.TextStyle.paragraph, max_length=500)
    paragraphen = TextInput(label="Rechtsgrundlage (§)", style=discord.TextStyle.short, max_length=45)
    sachverhalt = TextInput(label="Sachverhalt", style=discord.TextStyle.paragraph, max_length=1000)
    zeugen = TextInput(label="Zeugen", style=discord.TextStyle.short, required=False, max_length=100)

    def __init__(self, bot: "MyBot", commands_cog: "SealSanctionCommands"):
        super().__init__()
        self.bot = bot
        self.commands_cog = commands_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: SealSanctionService = self.bot.get_cog("SealSanctionService")
        if not service: return

        data = {
            "deckname": self.deckname.value.strip(),
            "sanktionsmaß": self.sanktionsmaß.value.strip(),
            "paragraphen": self.paragraphen.value.strip(),
            "sachverhalt": self.sachverhalt.value.strip(),
            "zeugen": self.zeugen.value.strip()
        }
        result = await service.create_sanction(interaction, data)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ Fehler: {result.get('error')}", ephemeral=True)

        if submit_channel := self.bot.get_channel(SANCTION_SUBMIT_CHANNEL_ID):
            member = result['member']
            view = RemoveSanctionView(member.id)
            msg = await submit_channel.send(embed=result['embed'], view=view)
            
            if role := result.get("role_to_save"):
                await service._execute_query(
                    "INSERT INTO seal_sanctions (user_id, role_id, message_id, channel_id, issued_at) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE role_id=VALUES(role_id), message_id=VALUES(message_id), channel_id=VALUES(channel_id), issued_at=VALUES(issued_at)",
                    (member.id, role.id, msg.id, msg.channel.id, datetime.now(timezone.utc))
                )
        
        response_msg = "✅ Antrag erfolgreich verarbeitet."
        if warning := result.get("warning"):
            response_msg += f"\n{warning}"
        await interaction.followup.send(response_msg, ephemeral=True)
        await self.commands_cog.create_or_update_panel()

# --- Command Cog ---
class SealSanctionCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(RemoveSanctionView(0)) # Registriere die View mit einer Dummy-ID
        self.bot.loop.create_task(self.delayed_panel_setup())
        
    async def delayed_panel_setup(self):
        await self.bot.wait_until_ready()
        await self.create_or_update_panel()
        print("[INFO] SEAL-Sanktions-Panel wurde gesetzt/aktualisiert.")

    async def create_or_update_panel(self):
        channel = self.bot.get_channel(SANCTION_SUBMIT_CHANNEL_ID)
        if not channel: return

        try:
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds and msg.embeds[0].title == "SEALs Sanktions-Panel":
                    await msg.delete()
                    break
        except Exception: pass

        embed = discord.Embed(
            title="SEALs Sanktions-Panel",
            description="Klicke auf den Button, um einen Sanktionsantrag für ein Mitglied der SEALs einzureichen.",
            color=discord.Color.blue()
        )
        view = View(timeout=None)
        button = Button(label="Sanktionsantrag einreichen", style=ButtonStyle.primary, custom_id="open_sanktionsmodal_seal")
        view.add_item(button)
        await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        custom_id = interaction.data.get("custom_id", "")

        if custom_id == "open_sanktionsmodal_seal":
            await interaction.response.send_modal(SealSanktionsantragModal(self.bot, self))
            return

        if custom_id.startswith("remove_seal_sanction_"):
            await interaction.response.defer(ephemeral=True)
            service: SealSanctionService = self.bot.get_cog("SealSanctionService")
            if not service: return await interaction.followup.send("Fehler: Service nicht verfügbar.", ephemeral=True)

            is_allowed = await service.has_remove_permission(interaction)
            if not is_allowed:
                return await interaction.followup.send("❌ Du hast keine Berechtigung für diese Aktion.", ephemeral=True)

            try:
                member_id = int(custom_id.split('_')[3])
            except (IndexError, ValueError):
                return await interaction.followup.send("Fehler: Ungültige Button-ID.", ephemeral=True)
            
            sanction_data = await service.remove_sanction(member_id)

            if sanction_data:
                # Alte Nachricht bearbeiten, um Buttons zu entfernen
                try:
                    channel = self.bot.get_channel(sanction_data['channel_id'])
                    msg = await channel.fetch_message(sanction_data['message_id'])
                    embed = msg.embeds[0]
                    embed.title = "❌ Sanktion entfernt"
                    embed.color = discord.Color.dark_grey()
                    await msg.edit(embed=embed, view=None)
                except Exception as e:
                    print(f"Konnte alte Sanktionsnachricht nicht bearbeiten: {e}")
                
                await interaction.followup.send(f"✅ Sanktion von <@{member_id}> wurde serverübergreifend entfernt.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Sanktion konnte nicht gefunden oder entfernt werden.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(SealSanctionCommands(bot))
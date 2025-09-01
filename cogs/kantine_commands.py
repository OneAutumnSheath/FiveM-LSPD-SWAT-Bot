import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot
    from services.kantine_service import KantineService
    from services.log_service import LogService
    
# --- Konstanten ---
CHANNEL_ID = 1353348248823136270

# --- UI Klassen ---

class KantinenModal(discord.ui.Modal, title="Öffnung protokollieren"):
    zusatzpersonal = discord.ui.TextInput(label="Zusatzpersonal (optional)", placeholder="z.B. Müller, Schmidt", required=False, max_length=200)

    def __init__(self, bot: "MyBot", commands_cog: "KantineCommands"):
        super().__init__()
        self.bot = bot
        self.commands_cog = commands_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: KantineService = self.bot.get_cog("KantineService")
        if not service: return await interaction.followup.send("Fehler: Kantinen-Service nicht gefunden.", ephemeral=True)
        
        success = await service.open_canteen(interaction.user, self.zusatzpersonal.value.strip())
        
        if success:
            await interaction.followup.send("✅ Öffnung wurde erfolgreich protokolliert.", ephemeral=True)
            await self.commands_cog.setup_kantinen_panel()
        else:
            await interaction.followup.send("❌ Ein Fehler ist aufgetreten.", ephemeral=True)

class KantineButtonView(discord.ui.View):
    def __init__(self, bot: "MyBot", commands_cog: "KantineCommands"):
        super().__init__(timeout=None)
        self.bot = bot
        self.commands_cog = commands_cog

    @discord.ui.button(label="Öffnen", style=discord.ButtonStyle.success, custom_id="kantine_open_v2")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service: KantineService = self.bot.get_cog("KantineService")
        if service and service.get_status() == "Geöffnet":
            return await interaction.response.send_message("⚠️ Die Kantine ist bereits geöffnet!", ephemeral=True)
        await interaction.response.send_modal(KantinenModal(self.bot, self.commands_cog))

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.danger, custom_id="kantine_close_v2")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service: KantineService = self.bot.get_cog("KantineService")
        if not service: return await interaction.followup.send("Fehler: Kantinen-Service nicht gefunden.", ephemeral=True)

        success = await service.close_canteen(interaction.user)
        if success:
            await interaction.followup.send("✅ Schließung wurde protokolliert.", ephemeral=True)
            await self.commands_cog.setup_kantinen_panel()
        else:
            await interaction.followup.send("⚠️ Die Kantine ist bereits geschlossen!", ephemeral=True)

# --- Command Cog ---
class KantineCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(KantineButtonView(self.bot, self))
        self.bot.loop.create_task(self.delayed_panel_setup())
        
    async def delayed_panel_setup(self):
        await self.bot.wait_until_ready()
        await self.setup_kantinen_panel()

    async def setup_kantinen_panel(self):
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel: return

        service: KantineService = self.bot.get_cog("KantineService")
        if not service: return

        # Alte Nachricht löschen
        try:
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.components:
                    await msg.delete()
        except Exception: pass

        # Neues Panel senden
        status = service.get_status()
        status_emoji = "🟢" if status == "Geöffnet" else "🔴"
        color = discord.Color.green() if status == "Geöffnet" else discord.Color.red()
        embed = discord.Embed(
            title="📋 Kantine – Öffnen / Schließen",
            description=f"Drücke auf einen der Buttons, um die Öffnung oder Schließung der Kantine zu protokollieren.\n\n{status_emoji} **Status:** {status}",
            color=color
        )
        await channel.send(embed=embed, view=KantineButtonView(self.bot, self))

async def setup(bot: "MyBot"):
    await bot.add_cog(KantineCommands(bot))
import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.kassen_service import KassenService
    from services.log_service import LogService
    
# --- Konstanten ---
KASSEN_CHANNEL_ID = 1213569335168081941

class KassenCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Sorgt dafür, dass der Kassenstand beim Start aktuell ist."""
        await self.send_current_kassenstand()

    async def send_current_kassenstand(self):
        """Aktualisiert die persistente Kassenstand-Nachricht."""
        channel = self.bot.get_channel(KASSEN_CHANNEL_ID)
        if not channel: return

        service: KassenService = self.bot.get_cog("KassenService")
        if not service: return

        # Alte Nachricht löschen
        try:
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.embeds and message.embeds[0].title == "📊 Aktueller Kassenstand":
                    await message.delete()
                    break
        except Exception: pass

        # Neuen Kassenstand senden
        kassenstand = await service.get_kassenstand()
        geld = kassenstand.get('geld', 0)
        schwarzgeld = kassenstand.get('schwarzgeld', 0)
        
        embed = discord.Embed(
            title="📊 Aktueller Kassenstand",
            description=f"💰 **Geld:** {geld:,}$\n🖤 **Schwarzgeld:** {schwarzgeld:,}$".replace(",", "."),
            color=discord.Color.blue()
        )
        await channel.send(embed=embed)

    # --- Befehlsgruppe ---
    kasse_group = app_commands.Group(name="kasse", description="Befehle zur Verwaltung der Kasse.")

    @kasse_group.command(name="stand", description="Zeigt den aktuellen Stand der Kasse an.")
    @has_permission("kasse.stand")
    @log_on_completion
    async def kassenstand(self, interaction: discord.Interaction):
        service: KassenService = self.bot.get_cog("KassenService")
        if not service: return await interaction.response.send_message("Fehler: Kassen-Service nicht gefunden.", ephemeral=True)
        
        kassenstand = await service.get_kassenstand()
        geld = kassenstand.get('geld', 0)
        schwarzgeld = kassenstand.get('schwarzgeld', 0)
        
        embed = discord.Embed(
            title="📊 Kassenstand",
            description=f"💰 **Geld:** {geld:,}$\n🖤 **Schwarzgeld:** {schwarzgeld:,}$".replace(",", "."),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @kasse_group.command(name="einzahlen", description="Zahlt Geld in die Kasse ein.")
    @app_commands.describe(geld="Der Betrag an normalem Geld.", schwarzgeld="Der Betrag an Schwarzgeld.")
    @has_permission("kasse.einzahlen")
    @log_on_completion
    async def einzahlen(self, interaction: discord.Interaction, geld: int = 0, schwarzgeld: int = 0):
        if geld <= 0 and schwarzgeld <= 0:
            return await interaction.response.send_message("⚠️ Du musst einen positiven Betrag angeben!", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        service: KassenService = self.bot.get_cog("KassenService")
        if not service: return await interaction.followup.send("Fehler: Kassen-Service nicht gefunden.", ephemeral=True)
        
        await service.update_kassenstand(geld, schwarzgeld)
        
        embed = discord.Embed(
            title="💵 Einzahlung",
            description=f"👤 **Von:** {interaction.user.mention}\n💰 **Geld:** +{geld:,}$\n🖤 **Schwarzgeld:** +{schwarzgeld:,}$".replace(",", "."),
            color=discord.Color.green()
        )
        await service.log_transaction(embed)
        await self.send_current_kassenstand()
        await interaction.followup.send("Einzahlung erfolgreich verbucht.", ephemeral=True)

    @kasse_group.command(name="auszahlen", description="Zahlt Geld aus der Kasse aus.")
    @app_commands.describe(an_wen="Der Empfänger.", grund="Der Grund.", geld="Der Betrag an Geld.", schwarzgeld="Der Betrag an Schwarzgeld.")
    @has_permission("kasse.auszahlen")
    @log_on_completion
    async def auszahlen(self, interaction: discord.Interaction, an_wen: discord.Member, grund: str, geld: int = 0, schwarzgeld: int = 0):
        if geld <= 0 and schwarzgeld <= 0:
            return await interaction.response.send_message("⚠️ Du musst einen positiven Betrag angeben!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        service: KassenService = self.bot.get_cog("KassenService")
        if not service: return await interaction.followup.send("Fehler: Kassen-Service nicht gefunden.", ephemeral=True)
        
        kassenstand = await service.get_kassenstand()
        if geld > kassenstand.get('geld', 0) or schwarzgeld > kassenstand.get('schwarzgeld', 0):
            return await interaction.followup.send("❌ Nicht genug Geld in der entsprechenden Kasse vorhanden!", ephemeral=True)
            
        await service.update_kassenstand(-geld, -schwarzgeld)
        
        embed = discord.Embed(
            title="💸 Auszahlung",
            description=f"👤 **Von:** {interaction.user.mention}\n➡️ **An:** {an_wen.mention}\n💰 **Geld:** -{geld:,}$\n🖤 **Schwarzgeld:** -{schwarzgeld:,}$\n📌 **Grund:** {grund}".replace(",", "."),
            color=discord.Color.red()
        )
        await service.log_transaction(embed)
        await self.send_current_kassenstand()
        await interaction.followup.send("Auszahlung erfolgreich verbucht.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(KassenCommands(bot))
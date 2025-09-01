import discord
from discord import Interaction
from discord.ext import commands
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
REQUEST_CHANNEL_ID = 1351076424500383795
PING_ROLE_ID = 1097648080020574260

class RequestAccessService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "RequestAccessService"

    async def create_access_request(self, interaction: Interaction, data: Dict[str, Any]) -> bool:
        """
        Erstellt ein Embed für eine Zugriffsanfrage und postet es.
        Gibt True bei Erfolg, False bei Fehler zurück.
        """
        channel = self.bot.get_channel(REQUEST_CHANNEL_ID)
        if not channel:
            print(f"[FEHLER] Anfrage-Kanal {REQUEST_CHANNEL_ID} nicht gefunden.")
            return False

        role = interaction.guild.get_role(PING_ROLE_ID)
        
        embed = discord.Embed(
            title="Neue Zugriffsanfrage",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Email", value=data["email"], inline=False)
        embed.add_field(name="Unit / Abteilung", value=data["unit"], inline=False)
        embed.add_field(name="Benötigter Zugriff", value=data["dokument"], inline=False)
        
        ausfuehrender_name = interaction.user.nick or interaction.user.name
        embed.set_footer(text=f"Eingereicht von {ausfuehrender_name}")

        try:
            content = role.mention if role else ""
            await channel.send(content=content, embed=embed)
            return True
        except discord.Forbidden:
            print(f"[FEHLER] Keine Berechtigung, in den Anfrage-Kanal {REQUEST_CHANNEL_ID} zu schreiben.")
            return False
        except Exception as e:
            print(f"[FEHLER] Unerwarteter Fehler beim Senden der Zugriffsanfrage: {e}")
            return False

async def setup(bot: "MyBot"):
    await bot.add_cog(RequestAccessService(bot))
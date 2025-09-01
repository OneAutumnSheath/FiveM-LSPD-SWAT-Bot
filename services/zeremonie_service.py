import discord
from discord.ext import commands
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
CHANNEL_IDS = [1105129400921493504, 1330265648302919701]

class ZeremonieService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "ZeremonieService"

    async def create_ceremony_log(self, interaction: discord.Interaction, content: str):
        """
        Erstellt und sendet das Zeremonie-Protokoll in alle konfigurierten Kanäle.
        """
        datum = datetime.now().strftime("%d.%m.%Y")
        embed = discord.Embed(
            title=f"📜 Zeremonie Protokoll vom {datum}",
            description=content,
            color=discord.Color.orange()
        )
        
        display_name = interaction.user.nick or interaction.user.name
        embed.set_footer(text=f"U.S. ARMY Management | ausgeführt von {display_name}")

        for channel_id in CHANNEL_IDS:
            if channel := self.bot.get_channel(channel_id):
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    print(f"[ZeremonieService] Fehler: Keine Berechtigung zum Senden in Channel {channel_id}")

async def setup(bot: "MyBot"):
    await bot.add_cog(ZeremonieService(bot))
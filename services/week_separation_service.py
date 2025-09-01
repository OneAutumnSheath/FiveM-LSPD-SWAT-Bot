import discord
from discord.ext import commands
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
WEEK_SEPARATION_CHANNELS = [
    1306741410455752805, 1306739470929756274, 1306739715826782340,
    1306741836567679036, 1306740165242392619, 1306740612556525650,
    1306741664127258644, 1306741178321997846, 1335699215405420544,
    1105129400921493504, 1353348248823136270
]

class WeekSeparationService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "WeekSeparationService"

    async def send_separation_message(self, target_channel: Optional[discord.TextChannel] = None) -> List[discord.TextChannel]:
        """
        Sendet die Wochentrennungs-Nachricht.
        Wenn target_channel angegeben ist, nur dorthin, ansonsten an die Preset-Liste.
        """
        message = "# ---------------------------------------------Wochentrennung---------------------------------------------"
        sent_channels = []
        channels_to_send_in = []

        if target_channel:
            channels_to_send_in.append(target_channel)
        else:
            for channel_id in WEEK_SEPARATION_CHANNELS:
                if channel := self.bot.get_channel(channel_id):
                    channels_to_send_in.append(channel)
        
        for channel in channels_to_send_in:
            try:
                await channel.send(message)
                sent_channels.append(channel)
            except discord.Forbidden:
                print(f"[FEHLER] WeekSeparation: Keine Berechtigung zum Senden in Channel {channel.id}.")
            except Exception as e:
                print(f"[FEHLER] WeekSeparation: Fehler beim Senden in {channel.id}: {e}")
        
        return sent_channels

async def setup(bot: "MyBot"):
    await bot.add_cog(WeekSeparationService(bot))
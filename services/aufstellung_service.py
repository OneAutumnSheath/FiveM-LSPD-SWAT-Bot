import discord
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
AUFSTELLUNG_CHANNEL_ID = 935022121468440626
PING_ROLE_ID = 1213569073573793822

class AufstellungService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "AufstellungService"

    async def create_aufstellung(self, user: discord.Member, wann: str, uhrzeit: str, position: discord.Role) -> tuple[bool, str]:
        """
        Erstellt die Aufstellungs-Nachricht und sendet sie.
        Gibt ein Tupel zurück: (Erfolg, Nachricht/Fehlermeldung)
        """
        channel = self.bot.get_channel(AUFSTELLUNG_CHANNEL_ID)
        if not channel:
            error_msg = "Der Aufstellungs-Kanal konnte nicht gefunden werden."
            print(f"[FEHLER] {error_msg}")
            return (False, error_msg)

        message_content = (
            f"<@&{PING_ROLE_ID}>\n\n"
            f"Hiermit wird eine Aufstellung angekündigt.\n\n"
            f"**Wann?**: {wann} um {uhrzeit} Uhr\n\n"
            f"Hochachtungsvoll,\n"
            f"{user.mention}\n"
            f"{position.mention}"
        )

        try:
            await channel.send(message_content)
            return (True, f"Aufstellung erfolgreich in {channel.mention} angekündigt.")
        except discord.Forbidden:
            error_msg = "Fehler: Ich habe keine Berechtigung, in den Aufstellungs-Kanal zu schreiben."
            print(f"[FEHLER] {error_msg}")
            return (False, error_msg)
        except Exception as e:
            error_msg = f"Ein unerwarteter Fehler ist aufgetreten: {e}"
            print(f"[FEHLER] {error_msg}")
            return (False, error_msg)

async def setup(bot: "MyBot"):
    await bot.add_cog(AufstellungService(bot))
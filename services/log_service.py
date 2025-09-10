import discord
from discord.ext import commands
from discord import Interaction
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
BOT_LOG_CHANNEL = 952307485295931402 # Deine Log-Kanal-ID

class LogService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "LogService"

    async def log_command(self, interaction: Interaction):
        """
        Die Kernfunktion, die einen ausgeführten Slash-Befehl protokolliert.
        """
        log_channel = self.bot.get_channel(BOT_LOG_CHANNEL)
        if not log_channel:
            print(f"[LogService] FEHLER: Log-Kanal {BOT_LOG_CHANNEL} nicht gefunden.")
            return

        command_name = interaction.command.qualified_name if interaction.command else "Unbekannt"
        user = interaction.user
        
        # --- START DER KORREKTUR FÜR VERSCHACHTELTE BEFEHLE ---
        
        def find_and_format_options(options: list) -> str:
            """Sucht rekursiv nach Argumenten und formatiert sie."""
            lines = []
            for arg in options:
                # Wenn es ein Unterbefehl ist, steige tiefer in die Optionen ein
                if arg.get('type') in [1, 2]: # 1 = Subcommand, 2 = Subcommand Group
                    lines.extend(find_and_format_options(arg.get('options', [])))
                # Ansonsten ist es ein normales Argument mit einem Wert
                else:
                    name = arg['name']
                    value = arg.get('value', 'N/A')
                    
                    if isinstance(value, str) and value.isdigit():
                        if 'user' in name or 'mitglied' in name: value = f"<@{value}>"
                        elif 'channel' in name: value = f"<#{value}>"
                        elif 'role' in name or 'rolle' in name: value = f"<@&{value}>"
                    
                    lines.append(f"**{name}**: `{value}`")
            return lines

        arguments_text = ""
        options = interaction.data.get('options', [])
        formatted_args = find_and_format_options(options)

        if formatted_args:
            arguments_text = "\n".join(formatted_args)
        else:
            arguments_text = "*Keine Argumente*"

        # --- ENDE DER KORREKTUR ---

        embed = discord.Embed(
            title="Befehlsausführung geloggt",
            description=f"**Befehl:** `/{command_name}`\n**Ausgeführt von:** {user.mention} (`{user}`)",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Argumente", value=arguments_text, inline=False)
        embed.set_footer(text=f"Benutzer-ID: {user.id}")

        try:
            await log_channel.send(embed=embed)
        except discord.DiscordException as e:
            print(f"[LogService] FEHLER beim Senden der Log-Nachricht: {e}")

async def setup(bot: "MyBot"):
    await bot.add_cog(LogService(bot))
# bot/services/asservatenkammer_service.py

import discord
from discord import Interaction
from discord.ext import commands
import yaml
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

class AsservatenkammerService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "AsservatenkammerService"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/asservatenkammer_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/asservatenkammer_config.yaml nicht gefunden.")
            return {}

    async def create_beschlagnahmung(self, interaction: Interaction, data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt das Embed für eine Beschlagnahmung und postet es."""
        channel_id = self.config.get('channel_id')
        if not channel_id or not (channel := self.bot.get_channel(channel_id)):
            return {"success": False, "error": "Asservatenkammer-Kanal in der Config nicht gefunden."}

        # Wenn "ausgeführt für" leer ist, nimm den Nickname des ausführenden Users
        zustaendiger_soldat = data["wenn_fuer"] or interaction.user.display_name
        
        # --- START DER ANPASSUNG ---
        embed = discord.Embed(
            title="Beschlagnahmung",
            # Farbe wird entfernt, um den Standard (dunkel) zu verwenden
            timestamp=datetime.now()
        )
        embed.add_field(name="Konfisziert am", value=data["konf_date"], inline=True)
        embed.add_field(name="Täter", value=data["taeter"], inline=True)
        # Leeres Feld für den Abstand, falls Täter kurz ist
        embed.add_field(name="\u200b", value="\u200b", inline=True) 
        embed.add_field(name="Beschlagnahmt", value=data['beschlagnahmt'], inline=False)
        
        # Footer wird an das neue Format angepasst
        embed.set_footer(text=f"Zuständiger Officer: {zustaendiger_soldat}\nLSPD Asservatenkammer")
        # --- ENDE DER ANPASSUNG ---

        try:
            await channel.send(embed=embed)
            return {"success": True}
        except discord.Forbidden:
            return {"success": False, "error": f"Dem Bot fehlen Berechtigungen (z.B. 'Nachrichten senden', 'Links einbetten') im Kanal {channel.mention}."}
        except Exception as e:
            print(f"Unerwarteter Fehler in AsservatenkammerService: {e}")
            return {"success": False, "error": "Ein unerwarteter interner Fehler ist aufgetreten."}


    async def create_auslagerung(self, interaction: Interaction, data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt das Embed für eine Auslagerung und postet es."""
        channel_id = self.config.get('channel_id')
        if not channel_id or not (channel := self.bot.get_channel(channel_id)):
            return {"success": False, "error": "Asservatenkammer-Kanal in der Config nicht gefunden."}
            
        zustaendiger_soldat = data["wenn_fuer"] or interaction.user.display_name

        # --- START DER ANPASSUNG (angeglichenes Format) ---
        embed = discord.Embed(
            title="Auslagerung",
            timestamp=datetime.now()
        )
        embed.add_field(name="Ausgelagert am", value=data["datum"], inline=True)
        embed.add_field(name="Täter", value=data["taeter"], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) 
        embed.add_field(name="Beschlagnahmt", value=data['beschlagnahmt'], inline=False)
        embed.add_field(name="Grund der Auslagerung", value=data["grund"], inline=False)
        embed.set_footer(text=f"Zuständiger Officer: {zustaendiger_soldat}\nLSPD Asservatenkammer")
        # --- ENDE DER ANPASSUNG ---
        
        try:
            await channel.send(embed=embed)
            return {"success": True}
        except discord.Forbidden:
            return {"success": False, "error": f"Dem Bot fehlen Berechtigungen (z.B. 'Nachrichten senden', 'Links einbetten') im Kanal {channel.mention}."}
        except Exception as e:
            print(f"Unerwarteter Fehler in AsservatenkammerService: {e}")
            return {"success": False, "error": "Ein unerwarteter interner Fehler ist aufgetreten."}


async def setup(bot: "MyBot"):
    await bot.add_cog(AsservatenkammerService(bot))
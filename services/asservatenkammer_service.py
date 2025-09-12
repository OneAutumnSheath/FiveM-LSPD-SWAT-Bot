# bot/services/asservatenkammer_service.py

import discord
from discord import Interaction
from discord.ext import commands
import yaml
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any, Optional

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

    def _get_server_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Holt die Konfiguration für einen spezifischen Server."""
        servers = self.config.get('servers', {})
        return servers.get(str(guild_id))

    def _get_channel_for_guild(self, guild_id: int) -> Optional[discord.TextChannel]:
        """Ermittelt den Asservatenkammer-Kanal für eine Guild."""
        server_config = self._get_server_config(guild_id)
        if not server_config:
            return None
            
        channel_id = server_config.get('channel_id')
        if not channel_id:
            return None
            
        return self.bot.get_channel(channel_id)

    async def create_beschlagnahmung(self, interaction: Interaction, data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt das Embed für eine Beschlagnahmung und postet es."""
        if not interaction.guild:
            return {"success": False, "error": "Dieser Befehl kann nur in einem Server verwendet werden."}
            
        channel = self._get_channel_for_guild(interaction.guild.id)
        if not channel:
            return {"success": False, "error": f"Asservatenkammer-Kanal für Server '{interaction.guild.name}' in der Config nicht gefunden."}

        # Server-spezifische Konfiguration laden
        server_config = self._get_server_config(interaction.guild.id)
        server_name = server_config.get('name', interaction.guild.name)
        
        # Wenn "ausgeführt für" leer ist, nimm den Nickname des ausführenden Users
        zustaendiger_soldat = data["wenn_fuer"] or interaction.user.display_name
        
        embed = discord.Embed(
            title="Beschlagnahmung",
            timestamp=datetime.now()
        )
        embed.add_field(name="Konfisziert am", value=data["konf_date"], inline=True)
        embed.add_field(name="Täter", value=data["taeter"], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) 
        embed.add_field(name="Beschlagnahmt", value=data['beschlagnahmt'], inline=False)
        
        # Server-spezifischer Footer
        footer_text = f"Zuständiger Officer: {zustaendiger_soldat}\n{server_name} Asservatenkammer"
        embed.set_footer(text=footer_text)

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
        if not interaction.guild:
            return {"success": False, "error": "Dieser Befehl kann nur in einem Server verwendet werden."}
            
        channel = self._get_channel_for_guild(interaction.guild.id)
        if not channel:
            return {"success": False, "error": f"Asservatenkammer-Kanal für Server '{interaction.guild.name}' in der Config nicht gefunden."}
            
        # Server-spezifische Konfiguration laden
        server_config = self._get_server_config(interaction.guild.id)
        server_name = server_config.get('name', interaction.guild.name)
        
        zustaendiger_soldat = data["wenn_fuer"] or interaction.user.display_name

        embed = discord.Embed(
            title="Auslagerung",
            timestamp=datetime.now()
        )
        embed.add_field(name="Ausgelagert am", value=data["datum"], inline=True)
        embed.add_field(name="Täter", value=data["taeter"], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) 
        embed.add_field(name="Beschlagnahmt", value=data['beschlagnahmt'], inline=False)
        embed.add_field(name="Grund der Auslagerung", value=data["grund"], inline=False)
        
        # Server-spezifischer Footer
        footer_text = f"Zuständiger Officer: {zustaendiger_soldat}\n{server_name} Asservatenkammer"
        embed.set_footer(text=footer_text)
        
        try:
            await channel.send(embed=embed)
            return {"success": True}
        except discord.Forbidden:
            return {"success": False, "error": f"Dem Bot fehlen Berechtigungen (z.B. 'Nachrichten senden', 'Links einbetten') im Kanal {channel.mention}."}
        except Exception as e:
            print(f"Unerwarteter Fehler in AsservatenkammerService: {e}")
            return {"success": False, "error": "Ein unerwarteter interner Fehler ist aufgetreten."}

    def get_all_configured_guilds(self) -> list:
        """Gibt eine Liste aller konfigurierten Server-IDs zurück."""
        servers = self.config.get('servers', {})
        return [int(guild_id) for guild_id in servers.keys()]

async def setup(bot: "MyBot"):
    await bot.add_cog(AsservatenkammerService(bot))
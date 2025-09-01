# bot/services/display_service.py

import discord
from discord.ext import commands
import aiomysql
import yaml
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

class DisplayService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "DisplayService"
        self.config = self._load_config()
        self.seal_role_id = self.config.get('seal_role_id')

    def _load_config(self) -> dict:
        """Lädt die zentrale config.yaml."""
        try:
            with open('config/config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/config.yaml nicht für DisplayService gefunden.")
            return {}

    async def _get_deckname(self, user_id: int) -> str | None:
        """Holt den Decknamen eines Users aus der Datenbank."""
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("SELECT deckname FROM seals_decknamen WHERE user_id = %s", (user_id,))
                result = await cursor.fetchone()
                return result['deckname'] if result else None

    async def get_display(self, member: discord.Member | None, is_footer: bool = False) -> str:
        """
        Gibt den korrekten Anzeige-Namen für ein Mitglied zurück.
        Gibt "Navy-SEAL {deckname}" für SEALs zurück, ansonsten den normalen Anzeigenamen.
        Wenn is_footer True ist, wird der Name ohne @-Erwähnung zurückgegeben.
        """
        if not member:
            return "`Unbekannter User`"

        # Prüfen, ob das Mitglied die SEAL-Rolle hat
        is_seal = self.seal_role_id and any(role.id == self.seal_role_id for role in member.roles)
        
        # Logik für Navy-SEALs
        if is_seal:
            deckname = await self._get_deckname(member.id)
            if deckname:
                return f"Navy-SEAL {deckname}"
        
        # Fallback für alle anderen User oder wenn kein Deckname gefunden wurde
        if is_footer:
            # Im Footer den Nickname statt der Erwähnung zurückgeben
            return member.display_name
        else:
            # Standardmäßig die Erwähnung zurückgeben
            return member.mention

async def setup(bot: "MyBot"):
    await bot.add_cog(DisplayService(bot))
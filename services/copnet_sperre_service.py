# bot/services/copnet_sperre_service.py

import discord
from discord.ext import commands
import aiomysql
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot
    from services.personal_service import PersonalService

class CopnetSperreService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "CopnetSperreService"

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                await conn.commit()
                if fetch == "one": return await cursor.fetchone()
    
    async def create_sperre(self, message_id: int, requester: discord.Member, target_dn: str, reason: str, log_link: str) -> Dict[str, Any]:
        """Speichert eine neue Copnet-Sperre in der Datenbank."""
        personal_service: "PersonalService" = self.bot.get_cog("PersonalService")
        target_user_id = None
        if personal_service:
            # Benutze die _execute_query Methode des PersonalService, falls sie existiert, oder eine lokale
            member_details = await self._execute_query("SELECT discord_id FROM members WHERE dn = %s", (target_dn,), fetch="one")
            if member_details:
                target_user_id = member_details['discord_id']

        query = """
            INSERT INTO copnet_sperren 
            (message_id, target_dn, target_user_id, reason, log_link, requester_id, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        args = (message_id, target_dn, target_user_id, reason, log_link, requester.id, 'aktiv')
        await self._execute_query(query, args)
        return {"success": True}

    async def lift_sperre(self, message_id: int) -> Dict[str, Any]:
        """Hebt eine Sperre in der Datenbank auf."""
        query = "UPDATE copnet_sperren SET status = 'aufgehoben' WHERE message_id = %s"
        await self._execute_query(query, (message_id,))
        return {"success": True}

async def setup(bot: "MyBot"):
    await bot.add_cog(CopnetSperreService(bot))
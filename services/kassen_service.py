import discord
from discord.ext import commands
import aiomysql
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
KASSEN_CHANNEL_ID = 1213569335168081941

class KassenService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "KassenService"

    async def cog_load(self):
        """Stellt sicher, dass die Kassen-Tabelle existiert und initialisiert ist."""
        await self._ensure_table_exists()
        print("Kassen-Service geladen und Datenbanktabelle sichergestellt.")

    # --- Private Helfer ---
    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()

    async def _ensure_table_exists(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS kasse (
                id INT PRIMARY KEY DEFAULT 1,
                geld BIGINT DEFAULT 0,
                schwarzgeld BIGINT DEFAULT 0
            )
        """)
        # Stelle sicher, dass der eine Eintrag existiert
        await self._execute_query("INSERT IGNORE INTO kasse (id, geld, schwarzgeld) VALUES (1, 0, 0)")

    # --- Öffentliche API-Methoden ---

    async def get_kassenstand(self) -> Dict[str, int]:
        """Holt den aktuellen Kassenstand aus der Datenbank."""
        result = await self._execute_query("SELECT geld, schwarzgeld FROM kasse WHERE id = 1", fetch="one")
        return result if result else {"geld": 0, "schwarzgeld": 0}

    async def update_kassenstand(self, geld_diff: int, schwarzgeld_diff: int):
        """Ändert den Kassenstand in der Datenbank."""
        query = "UPDATE kasse SET geld = geld + %s, schwarzgeld = schwarzgeld + %s WHERE id = 1"
        await self._execute_query(query, (geld_diff, schwarzgeld_diff))

    async def log_transaction(self, embed: discord.Embed):
        """Sendet eine Transaktion in den Kassen-Log-Channel."""
        if channel := self.bot.get_channel(KASSEN_CHANNEL_ID):
            await channel.send(embed=embed)

async def setup(bot: "MyBot"):
    await bot.add_cog(KassenService(bot))
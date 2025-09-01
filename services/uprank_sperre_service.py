import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import aiomysql
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
UPRANK_CHANNEL_ID = 1186705436330692749
OVERVIEW_MSG_KEY = "uprank_overview_message_id"

class UprankSperreService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UprankSperreService"
        self._initial_update_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Stellt sicher, dass die Übersicht beim Start aktuell ist
        if not self._initial_update_done:
            await self.update_overview_embed()
            self._initial_update_done = True

    # --- Datenbank-Helfer ---
    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()

    async def _get_config_value(self, key: str) -> str | None:
        row = await self._execute_query("SELECT config_value FROM bot_config WHERE config_key = %s", (key,), fetch="one")
        return row['config_value'] if row else None

    async def _set_config_value(self, key: str, value: str):
        query = "INSERT INTO bot_config (config_key, config_value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)"
        await self._execute_query(query, (key, value))
        
    async def get_dn_by_userid(self, user_id: int) -> str | None:
        result = await self._execute_query("SELECT dn FROM members WHERE discord_id = %s", (user_id,), fetch="one")
        return result['dn'] if result else None

    # --- Öffentliche API-Methoden ---

    async def check_sperre(self, dn: str) -> tuple[bool, datetime | None]:
        """Prüft, ob eine DN eine aktive Uprank-Sperre hat."""
        row = await self._execute_query("SELECT sperre_ende FROM upranksperre WHERE dn = %s", (dn,), fetch="one")
        if row and row['sperre_ende'].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
            return (True, row['sperre_ende'])
        return (False, None)

    async def setze_sperre(self, dn: str, rang_id: int):
        """Setzt eine Sperre basierend auf der Rang-ID."""
        sperrzeit = self._berechne_sperrzeit(rang_id)
        if sperrzeit.days > 0:
            ende_datum = datetime.now(timezone.utc) + sperrzeit
            await self.setze_sperre_mit_datum(dn, ende_datum)

    async def setze_sperre_mit_datum(self, dn: str, ende_datum: datetime):
        """Setzt eine Sperre mit einem festen Enddatum."""
        query = "INSERT INTO upranksperre (dn, letzter_uprank, sperre_ende) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE letzter_uprank=VALUES(letzter_uprank), sperre_ende=VALUES(sperre_ende)"
        await self._execute_query(query, (dn, datetime.now(timezone.utc), ende_datum))
        await self.update_overview_embed()

    def _berechne_sperrzeit(self, rang_id: int) -> timedelta:
        """Berechnet die Dauer der Sperre basierend auf der Rang-ID."""
        if 5 <= rang_id <= 8: return timedelta(days=14)
        if 9 <= rang_id <= 12: return timedelta(days=21)
        return timedelta(days=0)

    async def update_overview_embed(self):
        """Aktualisiert das Übersichts-Embed im Uprank-Kanal."""
        query = "SELECT m.discord_id, m.name, u.sperre_ende FROM upranksperre u JOIN members m ON u.dn = m.dn WHERE u.sperre_ende > NOW() ORDER BY u.sperre_ende ASC"
        active_locks = await self._execute_query(query, fetch="all")
        
        lines = []
        if active_locks:
            for lock in active_locks:
                timestamp = int(lock['sperre_ende'].timestamp())
                lines.append(f"{lock['name']} (<@{lock['discord_id']}>): <t:{timestamp}:R>")
        
        description = "\n".join(lines) if lines else "Aktuell sind keine Sperren aktiv."

        embed = discord.Embed(
            title="Uprank-Sperren Übersicht",
            description=description,
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        ).set_footer(text="Diese Übersicht wird automatisch aktualisiert.")

        channel = self.bot.get_channel(UPRANK_CHANNEL_ID)
        if not channel: 
            print(f"FEHLER: Uprank-Übersichts-Channel (ID: {UPRANK_CHANNEL_ID}) nicht gefunden!")
            return

        msg_id = await self._get_config_value(OVERVIEW_MSG_KEY)
        message_to_edit = None
        if msg_id:
            try:
                message_to_edit = await channel.fetch_message(int(msg_id))
            except (discord.NotFound, discord.Forbidden):
                message_to_edit = None

        if message_to_edit:
            await message_to_edit.edit(embed=embed)
        else:
            new_message = await channel.send(embed=embed)
            await self._set_config_value(OVERVIEW_MSG_KEY, str(new_message.id))

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankSperreService(bot))
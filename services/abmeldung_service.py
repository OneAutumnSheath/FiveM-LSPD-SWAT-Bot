import discord
from discord.ext import commands, tasks
from datetime import datetime, date
import aiomysql
from typing import TYPE_CHECKING, List, Optional, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
ABMELDE_CHANNEL_ID = 1301272400989524050
LOG_CHANNEL_ID = 1352999239587987617
ABGEMELDET_ROLLE_ID = 1367223382646591508
GUILD_ID = 1097625621875675188

class AbmeldungService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "AbmeldungService"

    async def cog_load(self):
        """Wird beim Laden des Cogs ausgeführt."""
        await self._ensure_table_exists()
        self.abmelde_cleanup_task.start()
        print("AbmeldungService geladen, DB-Tabelle sichergestellt und Cleanup-Task gestartet.")

    def cog_unload(self):
        self.abmelde_cleanup_task.cancel()

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        """Eine Helfer-Methode für alle Datenbank-Abfragen."""
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor: # DictCursor gibt Dictionaries statt Tuples zurück
                await cursor.execute(query, args)
                if fetch == "one":
                    return await cursor.fetchone()
                if fetch == "all":
                    return await cursor.fetchall()
    
    async def _ensure_table_exists(self):
        """Stellt sicher, dass die `abmeldungen`-Tabelle existiert."""
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS abmeldungen (
                dn SMALLINT PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                user_name VARCHAR(255) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                reason TEXT,
                message_id BIGINT,
                submitted_at DATETIME NOT NULL
            );
        """)

    # --- Die öffentliche API deines Abmelde-Systems ---

    async def get_dn_for_user(self, user_id: int) -> Optional[str]:
        """Eine Helfer-Methode, um die DN eines Users zu bekommen."""
        result = await self._execute_query("SELECT dn FROM members WHERE discord_id = %s", (user_id,), fetch="one")
        return result.get("dn") if result else None

    async def get_abmeldung_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Holt die Abmeldung für einen bestimmten User anhand seiner Discord-ID."""
        return await self._execute_query("SELECT * FROM abmeldungen WHERE user_id = %s", (user_id,), fetch="one")

    async def get_active_abmeldungen(self) -> List[Dict[str, Any]]:
        """Holt alle aktiven und zukünftigen Abmeldungen."""
        return await self._execute_query("SELECT * FROM abmeldungen WHERE end_date >= CURDATE() ORDER BY end_date ASC", fetch="all")

    async def add_abmeldung(self, user: discord.Member, dn: str, start_date: date, end_date: date, reason: str, message_id: int):
        """Fügt eine neue Abmeldung hinzu oder aktualisiert sie, basierend auf der DN."""
        query = """
            INSERT INTO abmeldungen (dn, user_id, user_name, start_date, end_date, reason, message_id, submitted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                user_id = VALUES(user_id), user_name = VALUES(user_name), start_date = VALUES(start_date), 
                end_date = VALUES(end_date), reason = VALUES(reason), message_id = VALUES(message_id), 
                submitted_at = VALUES(submitted_at)
        """
        args = (dn, user.id, str(user), start_date, end_date, reason, message_id, datetime.now())
        await self._execute_query(query, args)

    async def remove_abmeldung_by_user_id(self, user_id: int) -> Optional[int]:
        """Löscht eine Abmeldung anhand der User-ID und gibt die Nachrichten-ID zurück."""
        abmeldung = await self.get_abmeldung_for_user(user_id)
        if not abmeldung:
            return None
        
        await self._execute_query("DELETE FROM abmeldungen WHERE user_id = %s", (user_id,))
        return abmeldung.get("message_id")

    # --- Hintergrund-Task ---
    @tasks.loop(hours=24)
    async def abmelde_cleanup_task(self):
        """Entfernt täglich abgelaufene Abmeldungen aus der DB und Discord."""
        guild = self.bot.get_guild(GUILD_ID)
        if not guild: return

        abgelaufene = await self._execute_query("SELECT * FROM abmeldungen WHERE end_date < CURDATE()", fetch="all")
        if not abgelaufene: return

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        abmelde_channel = guild.get_channel(ABMELDE_CHANNEL_ID)
        abgemeldet_rolle = guild.get_role(ABGEMELDET_ROLLE_ID)

        dns_to_delete = []
        for eintrag in abgelaufene:
            dns_to_delete.append(eintrag["dn"])
            
            if abmelde_channel and eintrag["message_id"]:
                try:
                    msg = await abmelde_channel.fetch_message(eintrag["message_id"])
                    await msg.delete()
                except discord.NotFound: pass
            
            member = guild.get_member(eintrag["user_id"])
            if member and abgemeldet_rolle and abgemeldet_rolle in member.roles:
                await member.remove_roles(abgemeldet_rolle, reason="Abmeldung abgelaufen")

            if log_channel:
                embed = discord.Embed(title="Abmeldung automatisch beendet", color=discord.Color.dark_grey())
                embed.add_field(name="Benutzer", value=f"<@{eintrag['user_id']}>", inline=False)
                await log_channel.send(embed=embed)
        
        if dns_to_delete:
            format_strings = ','.join(['%s'] * len(dns_to_delete))
            await self._execute_query(f"DELETE FROM abmeldungen WHERE dn IN ({format_strings})", tuple(dns_to_delete))
        
        commands_cog = self.bot.get_cog("AbmeldungCommands")
        if commands_cog:
            await commands_cog.update_abmeldungs_uebersicht_async()

    @abmelde_cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot: "MyBot"):
    await bot.add_cog(AbmeldungService(bot))
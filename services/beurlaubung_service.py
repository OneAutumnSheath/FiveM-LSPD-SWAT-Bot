# bot/services/beurlaubung_service.py

import discord
from discord.ext import commands
import aiomysql
import yaml
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot
    from services.log_service import LogService

class BeurlaubungService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "BeurlaubungService"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/beurlaubung_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/beurlaubung_config.yaml nicht gefunden.")
            return {}

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                await conn.commit()
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()

    async def get_member_by_dn(self, guild: discord.Guild, dn: str) -> discord.Member | None:
        """Sucht ein Mitglied anhand der Dienstnummer in der Datenbank und gibt das Member-Objekt zurück."""
        result = await self._execute_query("SELECT discord_id FROM members WHERE dn = %s", (dn,), fetch="one")
        if result and result['discord_id']:
            return guild.get_member(result['discord_id'])
        return None

    async def create_beurlaubung(self, requester: discord.Member, target_user: discord.Member, end_datum_text: str) -> Dict[str, Any]:
        """Speichert eine Beurlaubung und postet die Dokumentation in beiden Kanälen."""
        
        start_datum = datetime.now(timezone.utc)

        query = "INSERT INTO beurlaubungen (user_id, start_datum, end_datum, grund) VALUES (%s, %s, %s, %s)"
        grund = f"Eingetragen von {requester.display_name}"
        args = (target_user.id, start_datum.date(), end_datum_text, grund)
        await self._execute_query(query, args)

        log_channel_id = self.config.get('dokumentations_channel_id')
        if not log_channel_id or not (log_channel := self.bot.get_channel(log_channel_id)):
            return {"success": False, "error": "Der Dokumentations-Kanal konnte nicht gefunden werden. Der Antrag wurde aber in der DB gespeichert."}

        # Embed für den offiziellen Log-Kanal
        log_embed = discord.Embed(
            title="Beurlaubung eingetragen",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.set_author(name=f"Eingetragen von: {requester.display_name}", icon_url=requester.display_avatar.url)
        log_embed.add_field(name="Person", value=target_user.mention, inline=False)
        log_embed.add_field(name="Zeitraum", value=f"Von **{start_datum.strftime('%d.%m.%Y')}** bis **{end_datum_text}**", inline=False)
        
        try:
            await log_channel.send(embed=log_embed)
        except discord.HTTPException:
             return {"success": False, "error": "Der Log-Eintrag konnte nicht gesendet werden. Der Antrag wurde aber in der DB gespeichert."}
        
        # --- NEUE LOGIK: Bestätigung im Panel-Kanal posten ---
        panel_channel_id = self.config.get('panel_channel_id')
        # Sende nur eine Nachricht, wenn der Panel-Kanal nicht derselbe wie der Log-Kanal ist
        if panel_channel_id and panel_channel_id != log_channel_id:
            if panel_channel := self.bot.get_channel(panel_channel_id):
                try:
                    confirm_embed = discord.Embed(
                        title="✅ Beurlaubung eingereicht",
                        description=f"Eine Beurlaubung für {target_user.mention} vom **{start_datum.strftime('%d.%m.%Y')}** bis **{end_datum_text}** wurde erfasst.",
                        color=discord.Color.green()
                    )
                    await panel_channel.send(embed=confirm_embed)
                except discord.HTTPException:
                    # Nicht kritisch, wenn die Bestätigung fehlschlägt.
                    print(f"Konnte Bestätigungs-Embed für Beurlaubung nicht in Panel-Kanal {panel_channel_id} senden.")
                    pass
        
        log_service: "LogService" = self.bot.get_cog("LogService")
        if log_service:
            await log_service.log_event("beurlaubung", f"Beurlaubung für {target_user.name} bis {end_datum_text} durch {requester.name} eingetragen.")

        return {"success": True, "message": f"Die Beurlaubung für {target_user.mention} wurde erfolgreich eingetragen."}

async def setup(bot: "MyBot"):
    await bot.add_cog(BeurlaubungService(bot))
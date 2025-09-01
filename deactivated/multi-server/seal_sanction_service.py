import discord
import re
from discord.ext import commands
from discord import Interaction
import aiomysql
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
CROSS_GUILD_ROLE_MAPPING = {
    1097625621875675188: [1395430402109214773, 1395430476310777938],  # ARMY
}
ROLE_REMOVE_ALLOWED = [1331306902897823745]
SANCTION_ANNOUNCE_CHANNEL_ID = [ 1267535561883648001 ]

class SealSanctionService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "SealSanctionService"

    async def cog_load(self):
        await self._ensure_table_exists()

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()
    
    async def _ensure_table_exists(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS seal_sanctions (
                user_id BIGINT PRIMARY KEY, role_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
                issued_at DATETIME NOT NULL
            );
        """)

    async def get_user_id_by_deckname(self, deckname: str) -> int | None:
        result = await self._execute_query("SELECT user_id FROM seals_decknamen WHERE deckname = %s", (deckname,), fetch="one")
        return result['user_id'] if result else None

    async def create_sanction(self, interaction: Interaction, data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = await self.get_user_id_by_deckname(data["deckname"])
        if not user_id: return {"success": False, "error": "Deckname nicht gefunden."}
        
        member = interaction.guild.get_member(user_id)
        if not member: return {"success": False, "error": "Mitglied nicht auf diesem Server gefunden."}

        # Verwarnungs-Logik
        matches = re.findall(r"(\d+)\.\s*Verwarnung", data["sanktionsmaß"], re.IGNORECASE)
        verwarnung_level = int(matches[0]) if matches else 0
        
        current_server_roles = CROSS_GUILD_ROLE_MAPPING.get(interaction.guild.id, [])
        if not current_server_roles or len(current_server_roles) != 2:
            return {"success": False, "error": "Rollenkonfiguration für diesen Server fehlerhaft."}
        
        rolle1 = interaction.guild.get_role(current_server_roles[0])
        rolle2 = interaction.guild.get_role(current_server_roles[1])
        if not rolle1 or not rolle2: return {"success": False, "error": "Verwarnungsrollen nicht gefunden."}

        hat_rolle1 = rolle1 in member.roles
        rolle_zu_vergeben = None
        if verwarnung_level == 1:
            rolle_zu_vergeben = rolle1 if not hat_rolle1 else rolle2
        elif verwarnung_level == 2:
            rolle_zu_vergeben = rolle2
            if not hat_rolle1: await member.add_roles(rolle1, reason="Automatische 1. Verwarnung")

        if rolle_zu_vergeben and rolle_zu_vergeben in member.roles:
            return {"success": True, "warning": f"{member.mention} hat bereits die höchste Stufe erreicht. Eskalation!"}
        
        # Rollen auf allen Servern zuweisen
        if rolle_zu_vergeben:
            for guild_id, role_ids in CROSS_GUILD_ROLE_MAPPING.items():
                if guild := self.bot.get_guild(guild_id):
                    try:
                        target_member = await guild.fetch_member(user_id)
                        target_role_id = role_ids[0] if rolle_zu_vergeben.id == rolle1.id else role_ids[1]
                        if target_role := guild.get_role(target_role_id):
                            await target_member.add_roles(target_role, reason="SEAL Sanktion (cross-server)")
                    except discord.NotFound: continue

        # Ankündigungen
        embed = discord.Embed(title="📄 Neue SEAL-Sanktion", color=discord.Color.orange())
        embed.add_field(name="Sanktioniertes Mitglied", value=member.mention, inline=False)
        embed.add_field(name="Sanktionsmaß", value=self.sanktionsmaß.value, inline=False)
        embed.add_field(name="Rechtsgrundlage (§)", value=self.paragraphen.value, inline=False)
        embed.add_field(name="Sachverhalt", value=self.sachverhalt.value, inline=False)
        
        for channel_id in SANCTION_ANNOUNCE_CHANNEL_ID:
            if channel := self.bot.get_channel(channel_id):
                await channel.send(embed=embed)
        
        return {"success": True, "member": member, "embed": embed, "role_to_save": rolle_zu_vergeben}

    async def remove_sanction(self, member_id: int) -> bool:
        """Entfernt eine Sanktion serverübergreifend."""
        sanction_data = await self._execute_query("SELECT * FROM seal_sanctions WHERE user_id = %s", (member_id,), fetch="one")
        if not sanction_data: return False

        for guild_id, role_ids in CROSS_GUILD_ROLE_MAPPING.items():
            if guild := self.bot.get_guild(guild_id):
                try:
                    member = await guild.fetch_member(member_id)
                    roles_to_remove = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid) and guild.get_role(rid) in member.roles]
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason="SEAL Sanktion entfernt")
                except discord.NotFound: continue
        
        await self._execute_query("DELETE FROM seal_sanctions WHERE user_id = %s", (member_id,))
        return True

async def setup(bot: "MyBot"):
    await bot.add_cog(SealSanctionService(bot))
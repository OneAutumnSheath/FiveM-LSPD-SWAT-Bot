import discord
from discord.ext import commands
import aiomysql
from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from main import MyBot

class MemberService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "MemberService"
        self.RANK_MAPPING = {
            1: 935015868444868658, 2: 1294946672941465652, 3: 935015801445056592, 4: 1387536697536811058, 
            5: 1387536786716098590, 6: 935015740438880286, 7: 1131339674267435008, 8: 1387537827545481410, 
            9: 1387537817529487592, 10: 937126775010504735, 11: 1387538125060051034, 12: 962360526388727878,
            13: 1293917052511453224, 14: 935011460998893648, 15: 1293916581784584202, 16: 1361644874293837824, 
            17: 935010817580089404
        }
        self.ROLE_TO_RANK_ID_MAPPING = {v: k for k, v in self.RANK_MAPPING.items()}
        self.UNIT_MAPPING = {
            1303452595008049242: "internal_affairs", 935017371146522644: "police_academy", 935017143467147294: "human_resources", 
            1356684541204365375: "bikers", 1316223852136628234: "swat", 1401269846913585192: "asd", 
            1294106167122985082: "detectives", 1376692472213934202: "gtf", 1212825535005204521: "shp"
        }

    # --- DATENBANK-HELFER ---
    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()

    async def get_dn_by_discord_id(self, user_id: int) -> str | None:
        result = await self._execute_query("SELECT dn FROM members WHERE discord_id = %s", (user_id,), fetch="one")
        return result['dn'] if result else None

    async def check_dn_exists(self, dn: int) -> bool:
        return await self._execute_query("SELECT dn FROM members WHERE dn = %s", (dn,), fetch="one") is not None

    # --- ÖFFENTLICHE API-METHODEN ---

    async def add_member(self, guild: discord.Guild, dn: int, name: str, rank: discord.Role, discord_user: discord.Member) -> Dict[str, Any]:
        if await self.check_dn_exists(dn):
            return {"success": False, "error": f"Die Dienstnummer `{dn}` ist bereits vergeben."}
        
        rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(rank.id)
        if not rank_id:
            return {"success": False, "error": f"Die Rolle {rank.mention} ist kein gültiger Rang."}
        
        try:
            await self._execute_query("INSERT INTO members (dn, name, rank, hired_at, discord_id) VALUES (%s, %s, %s, NOW(), %s)", (dn, name, rank_id, discord_user.id))
            await self._execute_query("INSERT INTO units (dn) VALUES (%s)", (dn,))
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}

        try:
            all_rank_roles = [guild.get_role(r_id) for r_id in self.RANK_MAPPING.values()]
            await discord_user.remove_roles(*[r for r in all_rank_roles if r and r in discord_user.roles], reason="Neuer Rang bei add_member")
            await discord_user.add_roles(rank, reason="Rang bei add_member gesetzt")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Eintrag erfolgreich, aber Rollen konnten nicht gesetzt werden: {e}"}

        return {"success": True}

    async def remove_member(self, dn: int) -> Dict[str, Any]:
        if not await self.check_dn_exists(dn):
            return {"success": False, "error": f"Die Dienstnummer `{dn}` wurde nicht gefunden."}
            
        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    await cursor.execute("DELETE FROM units WHERE dn = %s", (dn,))
                    await cursor.execute("DELETE FROM members WHERE dn = %s", (dn,))
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
            
        return {"success": True}

    async def set_unit_status(self, member: discord.Member, role: discord.Role, status: bool) -> Dict[str, Any]:
        unit_name = self.UNIT_MAPPING.get(role.id)
        if not unit_name:
            return {"success": False, "error": f"{role.mention} ist keine gültige Unit-Rolle."}

        dn = await self.get_dn_by_discord_id(member.id)
        if not dn:
            return {"success": False, "error": f"{member.mention} ist nicht in der Datenbank registriert."}
        
        try:
            await self._execute_query(f"UPDATE units SET `{unit_name}` = %s WHERE dn = %s", (status, dn))
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
            
        try:
            if status:
                await member.add_roles(role, reason=f"Unit-Status gesetzt: {role.name}")
            else:
                await member.remove_roles(role, reason=f"Unit-Status entfernt: {role.name}")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Update erfolgreich, aber Rolle konnte nicht geändert werden: {e}"}
        
        return {"success": True}

    async def change_rank(self, dn: int, new_rank: discord.Role) -> Dict[str, Any]:
        if not await self.check_dn_exists(dn):
            return {"success": False, "error": f"Die Dienstnummer `{dn}` wurde nicht gefunden."}
        
        new_rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(new_rank.id)
        if not new_rank_id:
            return {"success": False, "error": f"{new_rank.mention} ist kein gültiger Rang."}

        try:
            await self._execute_query("UPDATE members SET rank = %s WHERE dn = %s", (new_rank_id, dn))
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
            
        return {"success": True}

    async def change_dn(self, current_dn: int, new_dn: int) -> Dict[str, Any]:
        if not await self.check_dn_exists(current_dn):
            return {"success": False, "error": f"Die aktuelle DN `{current_dn}` wurde nicht gefunden."}
        if await self.check_dn_exists(new_dn):
            return {"success": False, "error": f"Die neue DN `{new_dn}` ist bereits vergeben."}

        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    await cursor.execute("UPDATE members SET dn = %s WHERE dn = %s", (new_dn, current_dn))
                    await cursor.execute("UPDATE units SET dn = %s WHERE dn = %s", (new_dn, current_dn))
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
        
        return {"success": True}

async def setup(bot: "MyBot"):
    await bot.add_cog(MemberService(bot))
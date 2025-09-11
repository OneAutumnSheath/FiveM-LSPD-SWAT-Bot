import discord
from discord.ext import commands
import aiomysql
import asyncio
from functools import partial
from datetime import datetime, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_sperre_service import UprankSperreService

# --- Konstanten, die zur Logik gehören ---
SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "1Zv4l35RRpFm44Loy1kg5qAIZCPQ0b3e9P2aXGZhvK7k"
DIVISION_MAPPING = {
    (1, 15): 1213569073573793822,
    (16, 17): 1386673042289201224
}
DN_RANGES = {
    1213569073573793822: (100, 900), # LSPD
    1386673042289201224: (1, 2) # TEAM WHITE
}

class PersonalService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "PersonalService"
        self.sheet = None
        self.sheets_service = None
        self.RANK_MAPPING = {
            1: 935015868444868658, 2: 1294946672941465652, 3: 935015801445056592, 4: 1387536697536811058, 
            5: 1387536786716098590, 6: 935015740438880286, 7: 1131339674267435008, 8: 1387537817529487592, 
            9: 937126775010504735, 10: 1387538125060051034, 11: 962360526388727878, 12: 1293917052511453224,
            13: 1107769266608017559, 14: 1293916581784584202, 15: 1361644874293837824, 16: 935010817580089404
        }
        self.ROLE_TO_RANK_ID_MAPPING = {v: k for k, v in self.RANK_MAPPING.items()}
        self.bot.loop.create_task(self._async_init_sheets())

    async def _async_init_sheets(self):
        loop = asyncio.get_running_loop()
        try:
            creds_loader = partial(service_account.Credentials.from_service_account_file, SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            creds = await loop.run_in_executor(None, creds_loader)
            service_builder = partial(build, "sheets", "v4", credentials=creds)
            self.sheets_service = await loop.run_in_executor(None, service_builder)
            self.sheet = self.sheets_service.spreadsheets()
        except Exception as e:
            print(f"FATAL: Fehler bei der Initialisierung von Google Sheets im Personal-Service: {e}")

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()

    async def get_member_details(self, user_id: int) -> Dict[str, Any] | None:
        return await self._execute_query("SELECT dn, rank, name FROM members WHERE discord_id = %s", (user_id,), fetch="one")

    async def _check_dn_exists(self, dn: str) -> bool:
        result = await self._execute_query("SELECT dn FROM members WHERE dn = %s", (dn,), fetch="one")
        return result is not None

    async def _find_free_dn(self, min_dn: int, max_dn: int) -> str | None:
        query = "SELECT MIN(t1.dn + 1) as free_dn FROM members t1 LEFT JOIN members t2 ON t1.dn + 1 = t2.dn WHERE t1.dn BETWEEN %s AND %s AND t2.dn IS NULL"
        result = await self._execute_query(query, (min_dn, max_dn), fetch="one")
        if not result or not result["free_dn"]:
            check_first = await self._execute_query("SELECT dn FROM members WHERE dn = %s", (min_dn,), fetch="one")
            return str(min_dn) if not check_first else None
        return str(result["free_dn"])

    async def _change_dn_in_db(self, old_dn: str, new_dn: str, user_id: int):
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                await cursor.execute("UPDATE members SET dn = %s WHERE discord_id = %s", (new_dn, user_id))
                await cursor.execute("UPDATE units SET dn = %s WHERE dn = %s", (new_dn, old_dn))
                await cursor.execute("UPDATE upranksperre SET dn = %s WHERE dn = %s", (new_dn, old_dn))
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    async def _delete_member_from_db(self, dn: str):
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                await cursor.execute("DELETE FROM members WHERE dn = %s", (dn,))
                await cursor.execute("DELETE FROM units WHERE dn = %s", (dn,))
                await cursor.execute("DELETE FROM upranksperre WHERE dn = %s", (dn,))
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    
    async def _get_all_members_for_sheet(self):
        query = "SELECT m.dn, m.name, m.rank, DATE_FORMAT(m.hired_at, '%d.%m.%Y') as hired_at, m.discord_id, u.internal_affairs, u.police_academy, u.human_resources, u.bikers, u.swat, u.asd, u.detectives, u.gtf, u.shp FROM members m LEFT JOIN units u ON m.dn = u.dn"
        return await self._execute_query(query, fetch="all")

    def _blocking_update_google_sheets(self, members_data: list):
        if not self.sheet or not members_data: return
        try:
            values = [list(row.values()) for row in members_data]
            self.sheet.values().clear(spreadsheetId=SPREADSHEET_ID, range="Rohdaten").execute()
            self.sheet.values().update(spreadsheetId=SPREADSHEET_ID, range="Rohdaten!A1", valueInputOption="USER_ENTERED", body={"values": values}).execute()
        except Exception as e:
            print(f"Fehler beim Aktualisieren der Google Sheets Daten: {e}")

    async def update_google_sheets(self):
        if not self.sheet: return
        members = await self._get_all_members_for_sheet()
        if members is not None:
            await self.bot.loop.run_in_executor(None, self._blocking_update_google_sheets, members)

    async def hire_member(self, guild: discord.Guild, user: discord.Member, name: str, rank_role: discord.Role, reason: str, dn: str = None) -> Dict[str, Any]:
        new_rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(rank_role.id)
        if not new_rank_id: return {"success": False, "error": f"Der gewählte Rang {rank_role.mention} ist ungültig."}
        if await self.get_member_details(user.id): return {"success": False, "error": f"{user.mention} ist bereits registriert."}
        new_division_id = next((div for rng, div in DIVISION_MAPPING.items() if rng[0] <= new_rank_id <= rng[1]), None)
        if not new_division_id: return {"success": False, "error": "Keine passende Division für diesen Rang gefunden."}
        if not dn:
            min_dn, max_dn = DN_RANGES[new_division_id]
            dn = await self._find_free_dn(min_dn, max_dn)
            if not dn: return {"success": False, "error": "Keine freie Dienstnummer in der Division gefunden."}
        try:
            await self._execute_query("INSERT INTO members (dn, name, rank, discord_id, hired_at) VALUES (%s, %s, %s, %s, CURDATE())", (dn, name, new_rank_id, user.id))
            await self._execute_query("INSERT INTO units (dn) VALUES (%s)", (dn,))
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
        try:
            roles_to_add = [rank_role]
            STANDARD_ROLES = [935015868444868658, 1006304119541207140, 1213569073573793822]
            for role_id in STANDARD_ROLES:
                if role := guild.get_role(role_id): roles_to_add.append(role)
            if new_division_role := guild.get_role(new_division_id): roles_to_add.append(new_division_role)
            await user.add_roles(*roles_to_add, reason=f"Einstellung: {reason}")
            await user.edit(nick=f"[PD-{dn}] {name}", reason="Einstellung")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Eintrag erfolgreich, aber Discord-Aktion fehlgeschlagen: {e}"}
        await self.update_google_sheets()
        return {"success": True, "dn": dn, "division_id": new_division_id, "user": user, "rank_role": rank_role, "reason": reason}

    async def fire_member(self, user: discord.Member, reason: str) -> Dict[str, Any]:
        member_details = await self.get_member_details(user.id)
        if not member_details: return {"success": False, "error": f"{user.mention} ist nicht in der Datenbank."}
        dn = member_details["dn"]
        await self._delete_member_from_db(dn)
        try:
            await user.kick(reason=f"Kündigung: {reason}")
        except discord.HTTPException:
            pass
        await self.update_google_sheets()
        return {"success": True, "dn": dn, "user": user, "reason": reason}

    async def promote_member(self, guild: discord.Guild, user: discord.Member, new_rank_role: discord.Role, reason: str, ignore_lock: bool = False) -> Dict[str, Any]:
        member_details = await self.get_member_details(user.id)
        if not member_details: return {"success": False, "error": f"{user.mention} ist nicht in der Datenbank."}
        current_dn, current_rank_id, user_name = member_details["dn"], int(member_details["rank"]), member_details["name"]
        new_rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(new_rank_role.id)
        if not new_rank_id or new_rank_id <= current_rank_id: return {"success": False, "error": "Ungültiger oder niedrigerer Rang."}
        uprank_sperre_service: UprankSperreService = self.bot.get_cog("UprankSperreService")
        if uprank_sperre_service and not ignore_lock:
            is_gesperrt, sperre_ende = await uprank_sperre_service.check_sperre(current_dn)
            if is_gesperrt: return {"success": False, "error": f"{user.mention} hat eine Uprank-Sperre bis <t:{int(sperre_ende.timestamp())}:D>."}
        old_division_id = next((div for rng, div in DIVISION_MAPPING.items() if rng[0] <= current_rank_id <= rng[1]), None)
        new_division_id = next((div for rng, div in DIVISION_MAPPING.items() if rng[0] <= new_rank_id <= rng[1]), None)
        new_dn, dn_changed = current_dn, False
        if old_division_id != new_division_id:
            min_dn, max_dn = DN_RANGES[new_division_id]
            new_dn_candidate = await self._find_free_dn(min_dn, max_dn)
            if not new_dn_candidate: return {"success": False, "error": "Keine freie DN in der neuen Division gefunden."}
            await self._change_dn_in_db(current_dn, new_dn_candidate, user.id)
            new_dn, dn_changed = new_dn_candidate, True
        await self._execute_query("UPDATE members SET rank = %s WHERE dn = %s", (new_rank_id, new_dn))
        try:
            roles_to_remove = [guild.get_role(rid) for rid in self.RANK_MAPPING.values()]
            if old_division_id: roles_to_remove.append(guild.get_role(old_division_id))
            await user.remove_roles(*[r for r in roles_to_remove if r and r in user.roles], reason=f"Beförderung: {reason}")
            roles_to_add = [new_rank_role]
            if new_division_id: roles_to_add.append(guild.get_role(new_division_id))
            await user.add_roles(*[r for r in roles_to_add if r], reason=f"Beförderung: {reason}")
            if dn_changed: await user.edit(nick=f"[PD-{new_dn}] {user_name}", reason="Beförderung mit DN-Wechsel")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Update erfolgreich, aber Discord-Aktion fehlgeschlagen: {e}"}
        if uprank_sperre_service:
            await uprank_sperre_service.setze_sperre(new_dn, new_rank_id)
        await self.update_google_sheets()
        return {"success": True, "dn_changed": dn_changed, "new_dn": new_dn, "new_division_id": new_division_id}

    async def demote_member(self, guild: discord.Guild, user: discord.Member, new_rank_role: discord.Role, reason: str) -> Dict[str, Any]:
        member_details = await self.get_member_details(user.id)
        if not member_details: return {"success": False, "error": f"{user.mention} ist nicht in der Datenbank."}
        current_dn, current_rank_id, user_name = member_details["dn"], int(member_details["rank"]), member_details["name"]
        new_rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(new_rank_role.id)
        if not new_rank_id or new_rank_id >= current_rank_id: return {"success": False, "error": "Ungültiger oder höherer Rang."}
        old_division_id = next((div for rng, div in DIVISION_MAPPING.items() if rng[0] <= current_rank_id <= rng[1]), None)
        new_division_id = next((div for rng, div in DIVISION_MAPPING.items() if rng[0] <= new_rank_id <= rng[1]), None)
        new_dn, dn_changed = current_dn, False
        if old_division_id != new_division_id:
            min_dn, max_dn = DN_RANGES[new_division_id]
            new_dn_candidate = await self._find_free_dn(min_dn, max_dn)
            if not new_dn_candidate: return {"success": False, "error": "Keine freie DN in der neuen Division gefunden."}
            await self._change_dn_in_db(current_dn, new_dn_candidate, user.id)
            new_dn, dn_changed = new_dn_candidate, True
        await self._execute_query("UPDATE members SET rank = %s WHERE dn = %s", (new_rank_id, new_dn))
        try:
            roles_to_remove = [guild.get_role(rid) for rid in self.RANK_MAPPING.values()]
            if old_division_id: roles_to_remove.append(guild.get_role(old_division_id))
            await user.remove_roles(*[r for r in roles_to_remove if r and r in user.roles], reason=f"Degradierung: {reason}")
            roles_to_add = [new_rank_role]
            if new_division_id: roles_to_add.append(guild.get_role(new_division_id))
            await user.add_roles(*[r for r in roles_to_add if r], reason=f"Degradierung: {reason}")
            if dn_changed: await user.edit(nick=f"[PD-{new_dn}] {user_name}", reason="Degradierung mit DN-Wechsel")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Update erfolgreich, aber Discord-Aktion fehlgeschlagen: {e}"}
        await self.update_google_sheets()
        return {"success": True, "dn_changed": dn_changed, "new_dn": new_dn, "new_division_id": new_division_id}

    async def change_dn(self, user: discord.Member, new_dn: str) -> Dict[str, Any]:
        member_details = await self.get_member_details(user.id)
        if not member_details: return {"success": False, "error": f"{user.mention} ist nicht in der Datenbank."}
        current_dn, user_name = member_details["dn"], member_details["name"]
        if await self._check_dn_exists(new_dn): return {"success": False, "error": f"Die Dienstnummer `{new_dn}` ist bereits vergeben."}
        await self._change_dn_in_db(current_dn, new_dn, user.id)
        try:
            await user.edit(nick=f"[PD-{new_dn}] {user_name}", reason="Dienstnummer manuell geändert")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Update erfolgreich, aber Nickname-Update fehlgeschlagen: {e}"}
        await self.update_google_sheets()
        return {"success": True, "old_dn": current_dn, "new_dn": new_dn}

    async def rename_member(self, user: discord.Member, new_name: str) -> Dict[str, Any]:
        member_details = await self.get_member_details(user.id)
        if not member_details: return {"success": False, "error": f"{user.mention} ist nicht in der Datenbank."}
        dn, old_name = member_details["dn"], member_details["name"]
        await self._execute_query("UPDATE members SET name = %s WHERE discord_id = %s", (new_name, user.id))
        try:
            await user.edit(nick=f"[PD-{dn}] {new_name}", reason="Manuell umbenannt")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Update erfolgreich, aber Nickname-Update fehlgeschlagen: {e}"}
        await self.update_google_sheets()
        return {"success": True, "old_name": old_name, "new_name": new_name}

async def setup(bot: "MyBot"):
    await bot.add_cog(PersonalService(bot))
import discord
from discord.ext import commands
from discord import Interaction
import aiomysql
import asyncio
from functools import partial
from typing import TYPE_CHECKING, List, Dict, Any

# Importe für Google Sheets
from google.oauth2 import service_account
from googleapiclient.discovery import build

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "1LuBHz2JQIhJjF80I0CZVuvF8pAOmRNKU77htabzx3_k"

class UnitService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UnitService"
        self.sheet = None
        self.service = None
        self.UNIT_MAPPING = {
            1097648080020574260: "management", 1105121168383557742: "weapon_logistics", 1097648131367248016: "education", 
            1097625910242447422: "human_resources", 1289716541658497055: "military_police", 1269229762400878675: "usaf", 
            1136062113908019250: "navy", 1125174901989445693: "seals", 1339523576159666218: "soc", 
            1223450533050847375: "jag", 1187756956425920645: "infantry", 1291908029947711531: "medcorps", 
            1393596587246096474: "hundestaffel", 1228203847164497932: "kantine"
        }
        self.ROLE_DEPENDENCIES = {
            1125174901989445693: [1368937338989969458, 1351261216991088831, 1352386268939419740, 1352386667503157422, 1352386756946825266, 1352386851788423238, 1287178400573947968, 1384953553067708497, 1125174538964058223, 1186008938144075847],
            1136062113908019250: [1336018418389749771, 1197231640112549908, 1219384062498570431, 1125174775380197416, 1332110439877972068],
            1269229762400878675: [1393991280710914239, 1371956609848447047, 1371956559021604924, 1103356636015366275, 1210891795563683922, 1124848353071603772, 1317317517928042506],
            1339523576159666218: [1332705553142513774, 1332705938674815116, 1332706191486488706, 1332706409439039558],
            1187756956425920645: [1187757319535206480, 1187804329646764104, 1187804164038873298, 1317318696368341052],
            1289716541658497055: [1343961616718233660, 1384673872619638864, 1384673772510117890, 1292864071967834133, 1238831879679901768, 1289716456220528670, 1289716380580712522],
            1097648080020574260: [1108008526846103664, 1097834442283827290],
            1097625910242447422: [1097832262302695464, 1348398323077480448],
            1097648131367248016: [1097832273669267616, 1367815114564173874],
            1291908029947711531: [1370038830660456478]
        }
        self.bot.loop.create_task(self._async_init_sheets())

    async def _async_init_sheets(self):
        loop = asyncio.get_running_loop()
        try:
            creds_loader = partial(service_account.Credentials.from_service_account_file, SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            creds = await loop.run_in_executor(None, creds_loader)
            service_builder = partial(build, "sheets", "v4", credentials=creds)
            self.service = await loop.run_in_executor(None, service_builder)
            self.sheet = self.service.spreadsheets()
            print("Google Sheets Service für Unit-Service erfolgreich initialisiert.")
        except Exception as e:
            print(f"FATAL: Fehler bei der Initialisierung von Google Sheets im Unit-Service: {e}")

    # --- DATENBANK & API HELFER ---
    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()
    
    async def _set_deckname(self, user_id: int, deckname: str):
        sql = "INSERT INTO usarmy.seals_decknamen (user_id, deckname) VALUES (%s, %s) ON DUPLICATE KEY UPDATE deckname = VALUES(deckname)"
        await self._execute_query(sql, (user_id, deckname))

    async def _get_dn_for_user(self, user_id: int) -> str | None:
        result = await self._execute_query("SELECT dn FROM members WHERE discord_id = %s", (user_id,), fetch="one")
        return result['dn'] if result else None

    async def _get_unit_status(self, dn: str, unit_name: str) -> bool:
        result = await self._execute_query(f"SELECT `{unit_name}` FROM units WHERE dn = %s", (dn,), fetch="one")
        return bool(result[unit_name]) if result else False

    async def _get_unit_capacity(self, unit_name: str) -> tuple[int, int] | None:
        result = await self._execute_query("SELECT aktuelle_mitglieder, mitglieder_limit FROM unit_limits WHERE unit_name = %s", (unit_name,), fetch="one")
        return (result['aktuelle_mitglieder'], result['mitglieder_limit']) if result else None

    async def _set_unit_status(self, dn: str, unit_name: str, status: bool):
        await self._execute_query(f"UPDATE units SET `{unit_name}` = %s WHERE dn = %s", (status, dn))

    async def _change_member_count(self, unit_name: str, change: int):
        query = "UPDATE unit_limits SET aktuelle_mitglieder = GREATEST(0, aktuelle_mitglieder + %s) WHERE unit_name = %s"
        await self._execute_query(query, (change, unit_name))

    async def _get_all_members_for_sheet_async(self):
        query = "SELECT m.dn, m.name, m.rank, DATE_FORMAT(m.hired_at, '%d.%m.%Y') as hired_at, m.discord_id, u.management, u.weapon_logistics, u.education, u.human_resources, u.military_police, u.usaf, u.navy, u.seals, u.soc, u.jag, u.infantry, u.medcorps, u.hundestaffel, u.kantine FROM members m LEFT JOIN units u ON m.dn = u.dn"
        return await self._execute_query(query, fetch="all")

    def _blocking_update_google_sheets(self, members: list):
        if not self.sheet: return
        try:
            values = [[row[key] for key in row] for row in members]
            self.sheet.values().clear(spreadsheetId=SPREADSHEET_ID, range="Rohdaten").execute()
            self.sheet.values().update(spreadsheetId=SPREADSHEET_ID, range="Rohdaten!A1", valueInputOption="USER_ENTERED", body={"values": values}).execute()
        except Exception as e:
            print(f"Fehler beim Aktualisieren der Google Sheets Daten: {e}")

    async def update_google_sheets_async(self):
        members = await self._get_all_members_for_sheet_async()
        if members is not None:
            await self.bot.loop.run_in_executor(None, self._blocking_update_google_sheets, members)

    # =========================================================================
    # ÖFFENTLICHE API-METHODEN
    # =========================================================================

    async def unit_entry(self, interaction: Interaction, user: discord.Member, unit: discord.Role, grund: str,
                         zusatz_rollen: List[discord.Role], zusatz: str, deckname: str, override: bool) -> Dict[str, Any]:
        unit_name = self.UNIT_MAPPING.get(unit.id)
        if not unit_name: return {"success": False, "error": "Diese Rolle ist keiner Unit zugeordnet."}

        if override and not interaction.user.guild_permissions.administrator:
            return {"success": False, "error": "Du hast keine Berechtigung für den Override."}

        capacity = await self._get_unit_capacity(unit_name)
        if not capacity: return {"success": False, "error": f"Keine Kapazitätsdaten für Unit `{unit_name}` gefunden."}
        
        aktuelle_mitglieder, mitglieder_limit = capacity
        if aktuelle_mitglieder >= mitglieder_limit and not override:
            return {"success": False, "error": f"Die Unit `{unit.name}` ist voll (Limit: {mitglieder_limit})."}

        dn = await self._get_dn_for_user(user.id)
        if not dn: return {"success": False, "error": "Benutzer hat keine gültige Dienstnummer."}
        if await self._get_unit_status(dn, unit_name): return {"success": False, "error": f"{user.mention} ist bereits in der Unit."}

        try:
            await self._set_unit_status(dn, unit_name, True)
            await self._change_member_count(unit_name, 1)
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}

        await self.update_google_sheets_async()
        
        try:
            roles_to_add = [unit] + zusatz_rollen
            await user.add_roles(*[r for r in roles_to_add if r], reason=f"Unit Eintritt: {grund}")
        except discord.HTTPException as e:
            return {"success": True, "warning": f"DB-Eintrag erfolgreich, aber Rollenvergabe fehlgeschlagen: {e}"}

        if deckname:
            await self._set_deckname(user.id, deckname)

        if cog := self.bot.get_cog("UnitListService"): await cog.trigger_update()

        SEAL_UNIT_ROLE_ID = 1125174901989445693
        SU_SERVER_ID = 1363986017907900428
        if unit.id == SEAL_UNIT_ROLE_ID:
            if invitation_service := self.bot.get_cog("InvitationService"):
                await invitation_service.start_entry_process(interaction, user, target_guild_id=SU_SERVER_ID)
        
        return {"success": True, "user": user, "unit": unit, "grund": grund, "zusatz": zusatz}

    async def unit_exit(self, interaction: Interaction, user: discord.Member, unit: discord.Role, grund: str,
                        rollen_zum_entfernen: List[discord.Role]) -> Dict[str, Any]:
        unit_name = self.UNIT_MAPPING.get(unit.id)
        if not unit_name: return {"success": False, "error": "Diese Rolle ist keiner Unit zugeordnet."}

        dn = await self._get_dn_for_user(user.id)
        if not dn: return {"success": False, "error": "Benutzer hat keine gültige Dienstnummer."}
        if not await self._get_unit_status(dn, unit_name): return {"success": False, "error": f"{user.mention} ist nicht in der Unit."}

        try:
            await self._set_unit_status(dn, unit_name, False)
            await self._change_member_count(unit_name, -1)
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}
            
        await self.update_google_sheets_async()

        final_roles_to_remove = rollen_zum_entfernen + [unit]
        for r in final_roles_to_remove[:]:
            if r.id in self.ROLE_DEPENDENCIES:
                for dep_id in self.ROLE_DEPENDENCIES[r.id]:
                    if dep_role := interaction.guild.get_role(dep_id):
                        if dep_role not in final_roles_to_remove: final_roles_to_remove.append(dep_role)
        
        await user.remove_roles(*list(set(final_roles_to_remove)), reason=f"Unit Austritt: {grund}")

        if cog := self.bot.get_cog("UnitListService"):
            await cog.trigger_update()
            if unit.id == 1125174901989445693:
                if hasattr(cog, 'remove_deckname_async'): await cog.remove_deckname_async(user.id)
        
        return {"success": True, "user": user, "unit": unit, "grund": grund}

    async def unit_promotion(self, user: discord.Member, grund: str, roles_to_add: List[discord.Role], roles_to_remove: List[discord.Role]) -> Dict[str, Any]:
        try:
            if roles_to_add:
                await user.add_roles(*[r for r in roles_to_add if r], reason=f"Unit Aufstieg: {grund}")
            if roles_to_remove:
                await user.remove_roles(*[r for r in roles_to_remove if r], reason=f"Unit Aufstieg: {grund}")
        except discord.HTTPException as e:
            return {"success": False, "error": f"Rollenfehler: {e}"}

        if cog := self.bot.get_cog("CheckDepartments"): await cog.check_all_departments_for_member(user)
        if cog := self.bot.get_cog("UnitListService"): await cog.trigger_update()
        return {"success": True}

    async def unit_demotion(self, user: discord.Member, grund: str, alter_posten: discord.Role, neuer_posten: discord.Role | None) -> Dict[str, Any]:
        try:
            await user.remove_roles(alter_posten, reason=f"Unit Abstieg: {grund}")
            if neuer_posten:
                await user.add_roles(neuer_posten, reason=f"Unit Abstieg: {grund}")
        except discord.HTTPException as e:
            return {"success": False, "error": f"Rollenfehler: {e}"}

        if cog := self.bot.get_cog("UnitListService"): await cog.trigger_update()
        return {"success": True}


async def setup(bot: "MyBot"):
    await bot.add_cog(UnitService(bot))
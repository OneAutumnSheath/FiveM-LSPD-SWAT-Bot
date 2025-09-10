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
            1303452595008049242: "internal_affairs", 935017371146522644: "police_academy", 935017143467147294: "human_resources", 
            1356684541204365375: "bikers", 1316223852136628234: "swat", 1401269846913585192: "asd", 
            1294106167122985082: "detectives", 1376692472213934202: "gtf", 1212825535005204521: "shp"
        }
        self.ROLE_DEPENDENCIES = {
            1303452595008049242: [1303452683402874952, 1303452678915100703, 1303452678915100703, 1303452597709176917, 1254505255564214303], # IA
            935017371146522644: [1067448372744687656, 1117385633548226561, 935017286442561606], # PA
            935017143467147294: [1068295101731831978, 1117385689789640784, 935016743431188500], # HR
            1356684541204365375: [1356684451597254766, 1356684286354526219, 1356684087024291952, 1356683996100300931], # BIKERS
            1316223852136628234: [1187452851119722646, 1204733801591214100, 1039282890011324446, 1234564137191866428, 1053391614246133872, 1293333665258148000, 935018728104534117], # SWAT
            1401269846913585192: [1325637503184670783, 1325637796806787134, 1307817641448181791, 1307816089618616461, 1307815743911497810, 1401271341449089034, 1401269389793427558], # ASD
            1294106167122985082: [1294014237844443230, 1294014095116206110, 1294013934734671964, 1294013552364879903, 1294013303776874496, 1280940167032602734], # DETECTIVES
            1376692472213934202: [1376903575338352751, 1376903570854772766, 1376903562205990932, 1376903544904482919, 1376692842742681701, 1376692683288084560], # GTF
            1212825535005204521: [1325631255101968454, 1325631253189361795, 1395498540402479134, 1212825593796890694, 1212825879898759241, 1212825936592896122] # SHP
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
        sql = "INSERT INTO lspd.seals_decknamen (user_id, deckname) VALUES (%s, %s) ON DUPLICATE KEY UPDATE deckname = VALUES(deckname)"
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
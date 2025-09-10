# bot/services/termination_service.py

import discord
from discord.ext import commands
from datetime import datetime, timezone
import asyncio
import aiomysql
from functools import partial

# Importe für Google Sheets
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Import der Bot-Klasse für Type Hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MyBot

# --- Konfiguration ---
HAUPT_SERVER_ID = 1097625621875675188
SPREADSHEET_ID = "  "
SHEET_NAME = "Rohdaten"
CREDS_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PERSONAL_CHANNEL_ID = 1097625981671448698
HINWEIS_CHANNEL_ID = 1097655923465531392
MGMT_ROLE_ID = 1097648080020574260
LEITUNG_1_ROLE_ID = 1097650413165084772
LEITUNG_2_ROLE_ID = 1097650390230630580
LEITUNG_3_ROLE_ID = 1097834442283827290

class TerminationService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "TerminationService"
        self.sheet = None
        self.bot.loop.create_task(self._async_init_sheets())

    async def _async_init_sheets(self):
        loop = asyncio.get_running_loop()
        try:
            creds_loader = partial(service_account.Credentials.from_service_account_file, CREDS_FILE, scopes=SCOPES)
            creds = await loop.run_in_executor(None, creds_loader)
            service_builder = partial(build, "sheets", "v4", credentials=creds)
            sheets_service = await loop.run_in_executor(None, service_builder)
            self.sheet = sheets_service.spreadsheets()
            print("Google Sheets Service für TerminationService erfolgreich initialisiert.")
        except Exception as e:
            print(f"FATAL: Fehler bei der Initialisierung von Google Sheets im TerminationService: {e}")

    # --- Helfer-Methoden ---
    
    def _delete_from_sheet_sync(self, dn_to_delete: str):
        if not self.sheet: return
        try:
            sheet_data = self.sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_NAME).execute()
            rows = sheet_data.get("values", [])
            if not rows: return
            for index, row in enumerate(rows):
                if row and str(row[0]) == str(dn_to_delete):
                    body = {"requests": [{"deleteDimension": {"range": {"sheetId": 0, "dimension": "ROWS", "startIndex": index, "endIndex": index + 1}}}]}
                    self.sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
                    print(f"Zeile für DN {dn_to_delete} aus Google Sheet entfernt.")
                    break
        except Exception as e:
            print(f"Fehler beim Löschen aus Google Sheet: {e}")

    async def delete_from_sheet_async(self, dn_to_delete: str):
        await self.bot.loop.run_in_executor(None, self._delete_from_sheet_sync, dn_to_delete)

    async def _perform_auto_termination(self, member: discord.Member, dn: str, name: str):
        """Führt die Kündigungslogik aus (DB, Sheets, Benachrichtigungen)."""
        pool: aiomysql.Pool = self.bot.db_pool
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    await cursor.execute("DELETE FROM members WHERE dn = %s", (dn,))
                    await cursor.execute("DELETE FROM units WHERE dn = %s", (dn,))
                    await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            print(f"Mitglied [USA-{dn}] {name} aus der Datenbank entfernt.")
        except Exception as e:
            print(f"Fehler beim Löschen von [USA-{dn}] aus der DB: {e}")
            return

        await self.delete_from_sheet_async(dn)

        # HIER WURDEN DIE ÄNDERUNGEN VORGENOMMEN
        # Anstatt `member.mention` wird jetzt der aus der DB gelesene `name` verwendet.
        
        # Nachricht 1: Embed im Personal-Channel
        if personal_channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
            description_text = (f"Hiermit wird das ehemalige Mitglied **{name}** (ID: `{member.id}`) automatisch aus dem LSPD entlassen.\n\n"
                                f"**Grund:** Discord verlassen\n\n"
                                f"Hochachtungsvoll,\n<@&{MGMT_ROLE_ID}>")
            embed = discord.Embed(title="Automatische Entlassung", description=description_text, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.set_footer(text="LSPD Management")
            await personal_channel.send(embed=embed)

        # Nachricht 2: Text im Hinweis-Channel
        if hinweis_channel := self.bot.get_channel(HINWEIS_CHANNEL_ID):
            hinweis_message = (f"----------------------------\n"
                               f"Name: **{name}** (ID: `{member.id}`)\n"
                               f"DN: {dn}\n"
                               f"Grund: Automatische Kündigung: Discord verlassen\n"
                               f"<@&{LEITUNG_1_ROLE_ID}>, <@&{LEITUNG_2_ROLE_ID}>, <@&{LEITUNG_3_ROLE_ID}> —> Aus Business App kündigen\n"
                               f"<@&{MGMT_ROLE_ID}> —> Copnet löschen\n"
                               f"----------------------------")
            await hinweis_channel.send(hinweis_message)

    # --- Event-Listener ---
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Wird ausgelöst, wenn ein Mitglied den Haupt-Server verlässt."""
        if member.guild.id != HAUPT_SERVER_ID:
            return

        await asyncio.sleep(2)

        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 10:
                    return 
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == member.id and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 10:
                    return
        except discord.Forbidden:
            print("Keine Berechtigung, die Audit-Logs zu lesen.")
        
        pool: aiomysql.Pool = self.bot.db_pool
        if not pool: return

        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT dn, name FROM members WHERE discord_id = %s", (member.id,))
                    result = await cursor.fetchone()
            if result:
                dn, name = result
                print(f"Mitglied {member.display_name} hat den Server verlassen. Starte automatische Kündigung für DN {dn}.")
                await self._perform_auto_termination(member, dn, name)
        except Exception as e:
            print(f"Fehler bei der Überprüfung der DB für automatische Kündigung: {e}")

async def setup(bot: "MyBot"):
    await bot.add_cog(TerminationService(bot))
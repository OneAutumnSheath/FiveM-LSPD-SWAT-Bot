import discord
from discord.ext import commands
import aiomysql
import re
import json
import jwt
import aiohttp
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Any

if TYPE_CHECKING:
    from main import MyBot

# Konfiguration gehört zur Logik und lebt im Service
TRACKED_UNITS = {
    1187881694116720730: [1317318696368341052, 1187804164038873298, 1187804329646764104, 
                          1401617612647038996, 1187757319535206480, 1401605697636007997, 
                          1401605846374285382, 1401606282166669403, 1401606480804708383, 
                          1401606813526265856, 1187756956425920645], # INFANTRY
    1383989254652166294: [1289716380580712522, 1401989491882983544, 1401989362455154738, 1406056791258824768, 1343961616718233660, 1384673872619638864, 1384673772510117890, 1292864071967834133, 1238831879679901768], # MP
    1098251597416497212: [1317318324119666688, 1332110439877972068, 1125174775380197416, 1219384062498570431, 1336018418389749771, 1136062113908019250, 1197231640112549908], # NAVY
    1398815564733878335: [1384953553067708497, 1125174538964058223, 1186008938144075847, 1368937338989969458, 1351261216991088831, 1287178400573947968], # NAVY SEALS
    1103677113518784512: [1124848353071603772, 1317317517928042506, 1393991280710914239, 1371956609848447047, 1371956559021604924, 1103356636015366275, 1210891795563683922, 1332706191486488706, 1332706409439039558, 1332705553142513774, 1332705938674815116],
    1164815627337351269: [1317318837724516452, 1097832262302695464, 1348398323077480448, 1097625910242447422, 1097832273669267616, 1367815114564173874, 1097648131367248016, 1291908029947711531, 1395481250759704686, 1223450533050847375],
    1142910990036504576: [1097834442283827290, 1108008526846103664, 1097648080020574260],
    1338221327647248455: [1105121168383557742, 1228203847164497932]
}
MAX_FIELD_LENGTH = 1024

# Google Sheets Konfiguration
SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "1Xj_hr1nx3DrhNb2H3G-PY1Qg3QcxFnd-TJFm15sbcc0"
SHEET_RANGE = "C4:C19"

class UnitListService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UnitListService"
        # Google Sheets Cache
        self._access_token = None
        self._token_expires_at = 0

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
            CREATE TABLE IF NOT EXISTS seals_decknamen (
                user_id BIGINT PRIMARY KEY, deckname VARCHAR(255) NOT NULL
            )
        """)
        
    def _extract_dienstnummer(self, member: discord.Member):
        match = re.search(r'\[USA-(\d+)\]', member.display_name)
        return int(match.group(1)) if match else float('inf')

    async def _create_embeds_for_channel(self, channel_id: int, guild: discord.Guild) -> List[discord.Embed]:
            if channel_id not in TRACKED_UNITS: return []
            
            embeds = []
            embed = discord.Embed(title="Mitgliederliste", color=discord.Color.dark_blue())

            for role_id in TRACKED_UNITS[channel_id]:
                role = guild.get_role(role_id)
                if not role: continue

                sorted_members = sorted(role.members, key=self._extract_dienstnummer)
                member_lines = []
                for member in sorted_members:
                    deckname = await self.get_deckname(member.id)
                    member_text = f"{member.mention} [**{deckname}**]" if deckname else member.mention
                    member_lines.append(member_text)
                
                field_content = "\n".join(member_lines) or "Keine Mitglieder"
                role_name = f"**{role.name.upper()}**"

                # --- START: KORRIGIERTE LOGIK ZUM AUFTEILEN VON FELDERN ---
                
                # Prüfen, ob die Embed-Gesamtlänge überschritten wird
                # 25 Felder pro Embed, 6000 Zeichen insgesamt
                if len(embed.fields) >= 24 or len(str(embed)) + len(field_content) > 5900:
                    embed.set_footer(text=f"Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
                    embeds.append(embed)
                    embed = discord.Embed(title="Mitgliederliste (Fortsetzung)", color=discord.Color.dark_blue())

                # Teile den Inhalt auf, wenn er das Zeichenlimit für ein Feld überschreitet
                if len(field_content) > MAX_FIELD_LENGTH:
                    part_num = 1
                    current_chunk = ""
                    for line in member_lines:
                        if len(current_chunk) + len(line) + 1 > MAX_FIELD_LENGTH:
                            embed.add_field(name=f"{role_name} (Teil {part_num})", value=current_chunk, inline=False)
                            current_chunk = line
                            part_num += 1
                        else:
                            current_chunk += f"\n{line}"
                    
                    # Den letzten Teil hinzufügen
                    if current_chunk:
                        embed.add_field(name=f"{role_name} (Teil {part_num})", value=current_chunk, inline=False)
                else:
                    # Wenn der Inhalt passt, als einzelnes Feld hinzufügen
                    embed.add_field(name=role_name, value=field_content, inline=False)

                # --- ENDE: KORRIGIERTE LOGIK ---

            if embed.fields:
                embed.set_footer(text=f"Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
                embeds.append(embed)
                
            return embeds

    async def _update_channel_messages(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if not channel: return

        guild = channel.guild
        embeds = await self._create_embeds_for_channel(channel_id, guild)
        if not embeds: return

        try:
            async for message in channel.history(limit=50):
                if message.author == self.bot.user: await message.delete()
        except discord.Forbidden: pass
        
        for embed in embeds:
            await channel.send(embed=embed)

    # --- Öffentliche API-Methoden ---
    
    async def get_deckname(self, user_id: int) -> str | None:
        result = await self._execute_query("SELECT deckname FROM seals_decknamen WHERE user_id = %s", (user_id,), fetch="one")
        return result['deckname'] if result else None

    async def set_deckname(self, user_id: int, deckname: str):
        await self._execute_query("INSERT INTO seals_decknamen (user_id, deckname) VALUES (%s, %s) ON DUPLICATE KEY UPDATE deckname = VALUES(deckname)", (user_id, deckname))
        await self.trigger_update()
        await self.sync_decknamen_to_sheets()

    async def remove_deckname(self, user_id: int):
        await self._execute_query("DELETE FROM seals_decknamen WHERE user_id = %s", (user_id,))
        await self.trigger_update()
        await self.sync_decknamen_to_sheets()

    async def list_all_decknamen(self) -> List[Dict[str, Any]]:
        return await self._execute_query("SELECT user_id, deckname FROM seals_decknamen", fetch="all")

    async def trigger_update(self):
        """Löst eine vollständige Aktualisierung aller Unit-Listen aus."""
        print("[INFO] Aktualisierung aller Unit-Listen wird ausgelöst.")
        for channel_id in TRACKED_UNITS.keys():
            await self._update_channel_messages(channel_id)

    # --- Google Sheets Methoden ---
    
    async def _get_google_access_token(self) -> str:
        """Holt einen Access Token für Google Sheets API."""
        if self._access_token and datetime.now().timestamp() < self._token_expires_at:
            return self._access_token

        try:
            # Service Account Daten laden
            with open(SERVICE_ACCOUNT_FILE, 'r') as f:
                service_account = json.load(f)

            now = datetime.now()
            payload = {
                'iss': service_account['client_email'],
                'scope': 'https://www.googleapis.com/auth/spreadsheets',
                'aud': 'https://oauth2.googleapis.com/token',
                'exp': int((now + timedelta(hours=1)).timestamp()),
                'iat': int(now.timestamp())
            }

            # JWT Token erstellen
            assertion = jwt.encode(payload, service_account['private_key'], algorithm='RS256')

            # Access Token anfordern
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                    'assertion': assertion
                }
                
                async with session.post('https://oauth2.googleapis.com/token', data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self._access_token = token_data['access_token']
                        self._token_expires_at = datetime.now().timestamp() + token_data.get('expires_in', 3600) - 60
                        return self._access_token
                    else:
                        error_text = await response.text()
                        raise Exception(f"Token request failed: {response.status} - {error_text}")

        except Exception as e:
            print(f"Fehler beim Abrufen des Google Access Tokens: {e}")
            raise

    async def sync_decknamen_to_sheets(self) -> bool:
        """Synchronisiert alle Decknamen zu Google Sheets in die Spalte C4:C19."""
        try:
            print("[INFO] Starte Google Sheets Synchronisation...")
            
            # Access Token holen
            token = await self._get_google_access_token()
            
            # Alle Decknamen aus der Datenbank holen (alphabetisch sortiert)
            db_data = await self._execute_query(
                "SELECT deckname FROM seals_decknamen ORDER BY deckname", 
                fetch="all"
            )
            
            # Decknamen für Sheets vorbereiten (max. 16 Einträge für C4:C19)
            decknamen_list = []
            if db_data:
                for entry in db_data[:16]:  # Maximal 16 Einträge (C4 bis C19)
                    decknamen_list.append([entry['deckname']])
            
            # Fehlende Zeilen mit leeren Werten auffüllen
            while len(decknamen_list) < 16:
                decknamen_list.append([""])

            # Google Sheets API URL
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_RANGE}"
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            payload = {
                'values': decknamen_list
            }

            # Daten in Google Sheets schreiben
            async with aiohttp.ClientSession() as session:
                async with session.put(f"{url}?valueInputOption=USER_ENTERED", 
                                     headers=headers, json=payload) as response:
                    if response.status == 200:
                        count = len([d for d in decknamen_list if d[0]])  # Nur nicht-leere Einträge zählen
                        print(f"✅ {count} Decknamen erfolgreich zu Google Sheets synchronisiert")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"❌ Fehler beim Schreiben in Google Sheets: {response.status} - {error_text}")
                        return False

        except Exception as e:
            print(f"❌ Fehler bei der Google Sheets Synchronisation: {e}")
            return False

async def setup(bot: "MyBot"):
    await bot.add_cog(UnitListService(bot))
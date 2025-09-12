import discord
from discord.ext import commands
import aiomysql
import re
import json
import jwt
import aiohttp
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Any, Set

if TYPE_CHECKING:
    from main import MyBot

# Konfiguration: Jede Gruppe hat einen Namen und ihre Rollen
TRACKED_UNITS = {
    1348395813323411476: {
        "IA": [1303452597709176917, 1303452678915100703, 1303452683402874952, 1303452595008049242],
        "PA": [935017286442561606, 1117385633548226561, 1067448372744687656, 935017371146522644],
        "HR": [935016743431188500, 1117385689789640784, 1068295101731831978, 935017143467147294],
        "BIKERS": [1356683996100300931, 1356684087024291952, 1356684286354526219, 1356684451597254766],
        "SWAT": [935018728104534117, 1293333665258148000, 1053391614246133872, 1234564137191866428, 1039282890011324446, 1204733801591214100, 1187452851119722646],
        "ASD": [1401269389793427558, 1401271341449089034, 1307816089618616461, 1307817641448181791, 1325637796806787134, 1325637503184670783],
        "DETECTIVES": [1280940167032602734, 1294013303776874496, 1294013552364879903, 1294013934734671964, 1294014095116206110, 1294014237844443230],
#        "SHP": [1212825936592896122, 1212825879898759241, 1212825593796890694, 1395498540402479134, 1325631253189361795, 1325631255101968454]
    }
}

# Gruppen-Emojis für bessere Optik
GROUP_EMOJIS = {
    "IA": "🔍",
    "PA": "👮",
    "HR": "📋",
    "BIKERS": "🏍️",
    "SWAT": "🚁",
    "ASD": "🚨",
    "DETECTIVES": "🕵️",
#    "SHP": "🛡️"
}

# Discord Limits
MAX_FIELD_LENGTH = 1024
MAX_EMBED_LENGTH = 6000
MAX_FIELDS_PER_EMBED = 25

# Google Sheets Konfiguration
SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "1Zv4l35RRpFm44Loy1kg5qAIZCPQ0b3e9P2aXGZhvK7k"
SHEET_RANGE = "C4:C19"

class UnitListService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UnitListService"
        # Google Sheets Cache
        self._access_token = None
        self._token_expires_at = 0
        # Cache für Channel-Nachrichten: channel_id -> {group_name: [message_ids]}
        self._channel_messages = {}

    async def cog_load(self):
        await self._ensure_table_exists()
        await self._cache_existing_messages()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Event-Listener für Rollenänderungen."""
        # Prüfen ob sich Rollen geändert haben
        if set(before.roles) == set(after.roles):
            return
            
        # Prüfen ob eine der geänderten Rollen in unserem Tracking ist
        changed_roles = set(after.roles) ^ set(before.roles)
        all_tracked_roles = set()
        
        for channel_id, groups in TRACKED_UNITS.items():
            for role_ids in groups.values():
                all_tracked_roles.update(role_ids)
        
        # Wenn eine relevante Rolle geändert wurde, Update auslösen
        for role in changed_roles:
            if role.id in all_tracked_roles:
                print(f"🔄 Rolle {role.name} wurde für {after.display_name} geändert - Update wird ausgelöst")
                await self.trigger_update()
                break

    async def _cache_existing_messages(self):
        """Cached bestehende Bot-Nachrichten in den Unit-List Channels."""
        print("🔍 Cache bestehende Unit-List Nachrichten...")
        
        for channel_id in TRACKED_UNITS.keys():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue
                
            self._channel_messages[channel_id] = {}
            
            # Durchsuche die letzten 200 Nachrichten nach Bot-Nachrichten mit Embeds
            async for message in channel.history(limit=200):
                if message.author == self.bot.user and message.embeds:
                    embed = message.embeds[0]
                    if embed.title:
                        # Extrahiere Gruppenname aus dem Titel
                        for group_name in TRACKED_UNITS[channel_id].keys():
                            emoji = GROUP_EMOJIS.get(group_name, "📁")
                            if embed.title.startswith(f"{emoji} {group_name}"):
                                if group_name not in self._channel_messages[channel_id]:
                                    self._channel_messages[channel_id][group_name] = []
                                self._channel_messages[channel_id][group_name].append(message.id)
                                break
                                
        print("✅ Nachricht-Cache initialisiert")

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

    def _calculate_embed_length(self, embed: discord.Embed) -> int:
        """Berechnet die ungefähre Länge eines Embeds."""
        length = len(embed.title or "") + len(embed.description or "")
        for field in embed.fields:
            length += len(field.name) + len(field.value)
        if embed.footer:
            length += len(embed.footer.text or "")
        return length

    def _should_create_new_embed(self, current_embed: discord.Embed, new_content_length: int) -> bool:
        """Prüft, ob ein neues Embed erstellt werden sollte."""
        current_length = self._calculate_embed_length(current_embed)
        field_count = len(current_embed.fields)
        
        # Prüfe Limits
        would_exceed_length = current_length + new_content_length > MAX_EMBED_LENGTH - 200  # Buffer für Footer
        would_exceed_fields = field_count >= MAX_FIELDS_PER_EMBED - 1  # Buffer für weitere Felder
        
        return would_exceed_length or would_exceed_fields

    async def _create_embed_for_group(self, group_name: str, role_ids: List[int], guild: discord.Guild) -> List[discord.Embed]:
        """Erstellt ein oder mehrere Embeds für eine spezifische Gruppe."""
        embeds = []
        group_emoji = GROUP_EMOJIS.get(group_name, "📁")
        
        # Set für bereits verwendete Member
        used_members: Set[int] = set()
        
        # Erstes Embed für die Gruppe erstellen
        current_embed = discord.Embed(
            title=f"{group_emoji} {group_name}",
            color=discord.Color.dark_blue(),
            timestamp=datetime.now()
        )
        
        # Beschreibung hinzufügen
        total_members = 0
        unique_members: Set[int] = set()
        
        # Zähle einzigartige Members (keine Duplikate)
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role:
                for member in role.members:
                    unique_members.add(member.id)
        
        total_members = len(unique_members)
        current_embed.description = f"**Gesamtmitglieder:** {total_members}"

        for role_id in role_ids:
            role = guild.get_role(role_id)
            if not role:
                continue

            # Mitglieder sortieren und formatieren, aber nur die, die noch nicht verwendet wurden
            available_members = [m for m in role.members if m.id not in used_members]
            sorted_members = sorted(available_members, key=self._extract_dienstnummer)
            member_lines = []
            
            for member in sorted_members:
                deckname = await self.get_deckname(member.id)
                member_text = f"{member.mention} [**{deckname}**]" if deckname else member.mention
                member_lines.append(member_text)
                used_members.add(member.id)  # Als verwendet markieren
            
            # Überspringe Rollen ohne neue Members
            if not member_lines:
                continue
                
            field_content = "\n".join(member_lines)
            role_name = f"🔹 {role.name}"

            # Prüfen, ob ein neues Embed benötigt wird
            estimated_field_length = len(role_name) + len(field_content)
            
            if self._should_create_new_embed(current_embed, estimated_field_length):
                # Aktuelles Embed abschließen und zur Liste hinzufügen
                if current_embed.fields:
                    current_embed.set_footer(text=f"📅 Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
                    embeds.append(current_embed)
                
                # Neues Embed für die gleiche Gruppe erstellen
                embed_number = len(embeds) + 1
                current_embed = discord.Embed(
                    title=f"{group_emoji} {group_name} (Teil {embed_number + 1})",
                    color=discord.Color.dark_blue(),
                    timestamp=datetime.now()
                )

            # Feld-Inhalt aufteilen, wenn er zu lang ist
            if len(field_content) > MAX_FIELD_LENGTH:
                current_embed = await self._add_split_field(current_embed, role_name, member_lines, embeds, group_name, group_emoji)
            else:
                # Normales Feld hinzufügen
                current_embed.add_field(
                    name=role_name,
                    value=field_content,
                    inline=False
                )

        # Letztes Embed hinzufügen, falls es Felder hat
        if current_embed.fields or current_embed.description:
            current_embed.set_footer(text=f"📅 Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            embeds.append(current_embed)
                
        return embeds

    async def _add_split_field(self, current_embed: discord.Embed, role_name: str, member_lines: List[str], 
                              embeds: List[discord.Embed], group_name: str, group_emoji: str) -> discord.Embed:
        """Teilt ein zu langes Feld auf mehrere Felder oder Embeds auf."""
        part_num = 1
        current_chunk = ""
        
        for line in member_lines:
            line_with_newline = f"{line}\n"
            
            # Prüfen, ob die Zeile in den aktuellen Chunk passt
            if len(current_chunk) + len(line_with_newline) > MAX_FIELD_LENGTH:
                if current_chunk:  # Nur hinzufügen, wenn Chunk nicht leer ist
                    field_name = f"{role_name} (Teil {part_num})" if part_num > 1 else role_name
                    
                    # Prüfen, ob ein neues Embed benötigt wird
                    estimated_length = len(field_name) + len(current_chunk)
                    if self._should_create_new_embed(current_embed, estimated_length):
                        # Aktuelles Embed abschließen
                        if current_embed.fields:
                            current_embed.set_footer(text=f"📅 Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
                            embeds.append(current_embed)
                        
                        # Neues Embed für die gleiche Gruppe erstellen
                        embed_number = len(embeds) + 1
                        current_embed = discord.Embed(
                            title=f"{group_emoji} {group_name} (Teil {embed_number + 1})",
                            color=discord.Color.dark_blue(),
                            timestamp=datetime.now()
                        )
                    
                    current_embed.add_field(
                        name=field_name,
                        value=current_chunk.strip(),
                        inline=False
                    )
                
                # Neuen Chunk mit der aktuellen Zeile starten
                current_chunk = line_with_newline
                part_num += 1
            else:
                current_chunk += line_with_newline
        
        # Letzten Chunk hinzufügen
        if current_chunk:
            field_name = f"{role_name} (Teil {part_num})" if part_num > 1 else role_name
            
            # Prüfen, ob ein neues Embed benötigt wird
            estimated_length = len(field_name) + len(current_chunk)
            if self._should_create_new_embed(current_embed, estimated_length):
                # Aktuelles Embed abschließen
                if current_embed.fields:
                    current_embed.set_footer(text=f"📅 Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
                    embeds.append(current_embed)
                
                # Neues Embed für die gleiche Gruppe erstellen
                embed_number = len(embeds) + 1
                current_embed = discord.Embed(
                    title=f"{group_emoji} {group_name} (Teil {embed_number + 1})",
                    color=discord.Color.dark_blue(),
                    timestamp=datetime.now()
                )
            
            current_embed.add_field(
                name=field_name,
                value=current_chunk.strip(),
                inline=False
            )
        
        return current_embed

    async def _update_channel_messages(self, channel_id: int):
        """Aktualisiert Nachrichten in einem Channel durch Bearbeitung statt Neuversendung."""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"⚠️ Channel {channel_id} nicht gefunden")
            return

        guild = channel.guild
        
        if channel_id not in TRACKED_UNITS:
            print(f"⚠️ Keine Gruppen für Channel {channel_id} konfiguriert")
            return

        groups = TRACKED_UNITS[channel_id]

        # Für jede Gruppe die Nachrichten aktualisieren oder erstellen
        for group_name, role_ids in groups.items():
            try:
                print(f"🔄 Aktualisiere Gruppe: {group_name}")
                
                # Neue Embeds für diese Gruppe erstellen
                new_embeds = await self._create_embed_for_group(group_name, role_ids, guild)
                
                if not new_embeds:
                    print(f"⚠️ Keine Embeds für Gruppe {group_name} erstellt")
                    continue

                # Bestehende Nachrichten für diese Gruppe holen
                existing_messages = []
                if (channel_id in self._channel_messages and 
                    group_name in self._channel_messages[channel_id]):
                    
                    for msg_id in self._channel_messages[channel_id][group_name]:
                        try:
                            message = await channel.fetch_message(msg_id)
                            existing_messages.append(message)
                        except discord.NotFound:
                            print(f"⚠️ Nachricht {msg_id} wurde gelöscht")
                            continue

                # Nachrichten aktualisieren oder erstellen
                messages_updated = 0
                messages_created = 0
                
                for i, embed in enumerate(new_embeds):
                    if i < len(existing_messages):
                        # Bestehende Nachricht bearbeiten
                        try:
                            await existing_messages[i].edit(embed=embed)
                            messages_updated += 1
                        except Exception as e:
                            print(f"⚠️ Fehler beim Bearbeiten der Nachricht: {e}")
                    else:
                        # Neue Nachricht erstellen
                        try:
                            new_message = await channel.send(embed=embed)
                            # Cache aktualisieren
                            if channel_id not in self._channel_messages:
                                self._channel_messages[channel_id] = {}
                            if group_name not in self._channel_messages[channel_id]:
                                self._channel_messages[channel_id][group_name] = []
                            self._channel_messages[channel_id][group_name].append(new_message.id)
                            messages_created += 1
                        except Exception as e:
                            print(f"⚠️ Fehler beim Senden der Nachricht: {e}")

                # Überschüssige alte Nachrichten löschen
                messages_deleted = 0
                if len(existing_messages) > len(new_embeds):
                    for i in range(len(new_embeds), len(existing_messages)):
                        try:
                            await existing_messages[i].delete()
                            messages_deleted += 1
                            # Aus Cache entfernen
                            if (channel_id in self._channel_messages and 
                                group_name in self._channel_messages[channel_id]):
                                msg_id = existing_messages[i].id
                                if msg_id in self._channel_messages[channel_id][group_name]:
                                    self._channel_messages[channel_id][group_name].remove(msg_id)
                        except Exception as e:
                            print(f"⚠️ Fehler beim Löschen der überschüssigen Nachricht: {e}")

                print(f"✅ {group_name}: {messages_updated} aktualisiert, {messages_created} erstellt, {messages_deleted} gelöscht")
                
            except Exception as e:
                print(f"❌ Fehler beim Aktualisieren der Gruppe {group_name}: {e}")

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
        print("🔄 [INFO] Aktualisierung aller Unit-Listen wird ausgelöst.")
        for channel_id in TRACKED_UNITS.keys():
            await self._update_channel_messages(channel_id)
        print("✅ [INFO] Alle Unit-Listen wurden aktualisiert.")

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
            print(f"❌ Fehler beim Abrufen des Google Access Tokens: {e}")
            raise

    async def sync_decknamen_to_sheets(self) -> bool:
        """Synchronisiert alle Decknamen zu Google Sheets in die Spalte C4:C19."""
        try:
            print("🔄 [INFO] Starte Google Sheets Synchronisation...")
            
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
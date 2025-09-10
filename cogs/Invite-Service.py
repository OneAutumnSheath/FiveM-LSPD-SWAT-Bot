# services/lspd_invitation_service.py

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
import aiomysql
from typing import TYPE_CHECKING, Dict, Any, List, Set
from datetime import datetime, timezone, timedelta

if TYPE_CHECKING:
    from main import MyBot

class LspdInvitationService(commands.Cog):
    """
    Service für automatische LSPD Einladungen nach Rollenvergabe.
    Unterstützt bis zu 3 verschiedene Ziel-Server mit eigenen Rollen.
    """
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "LspdInvitationService"
        
        # Konfiguration - wird aus .env geladen
        self.pending_entries_file = "./data/lspd_special_units_invites.json"
        self.source_server_id = None
        self.server_configs: Dict[int, Dict] = {}  # server_id -> {name, monitored_roles, invite_channel_id}
        
        # Lade Konfiguration und Einladungen
        self._load_config()
        self.pending_entries = self._load_entries()

    def _load_config(self):
        """Lädt Konfiguration aus Umgebungsvariablen"""
        self.source_server_id = int(os.getenv('SOURCE_GUILD_ID', 0))
        
        # Lade bis zu 3 Ziel-Server mit ihren spezifischen Rollen
        for i in range(1, 4):  # 1, 2, 3
            target_id = os.getenv(f'TARGET_GUILD_ID_{i}', '').strip()
            target_name = os.getenv(f'TARGET_GUILD_NAME_{i}', f'Server {i}').strip()
            monitored_roles_str = os.getenv(f'MONITORED_ROLE_IDS_{i}', '').strip()
            invite_channel_id = os.getenv(f'INVITE_CHANNEL_ID_{i}', '').strip()
            
            if target_id and target_id.isdigit():
                server_id = int(target_id)
                monitored_roles = []
                
                # Parse die überwachten Rollen für diesen Server
                if monitored_roles_str:
                    try:
                        monitored_roles = [int(rid.strip()) for rid in monitored_roles_str.split(',') if rid.strip()]
                    except ValueError as e:
                        self.bot.log(f"Invitation Service - Fehler beim Laden der Rollen-IDs für {target_name}: {e}", level='error')
                        continue
                
                if monitored_roles:  # Nur Server mit Rollen hinzufügen
                    # Parse Channel ID (mit Fallback)
                    channel_id = None
                    if invite_channel_id and invite_channel_id.isdigit():
                        channel_id = int(invite_channel_id)
                    else:
                        # Default Channel ID falls nicht gesetzt
                        channel_id = 1411399063420665986
                    
                    self.server_configs[server_id] = {
                        'name': target_name,
                        'monitored_roles': monitored_roles,
                        'invite_channel_id': channel_id
                    }
                    self.bot.log(f"Invitation Service - Server {i}: {target_name} (ID: {server_id}) - {len(monitored_roles)} überwachte Rollen")
                else:
                    self.bot.log(f"Invitation Service - Server {i} ({target_name}) übersprungen - keine Rollen konfiguriert", level='warning')
        
        if not self.server_configs:
            self.bot.log("Invitation Service - Keine Ziel-Server mit Rollen konfiguriert!", level='warning')

    async def cog_load(self):
        """Initialisierung beim Laden des Cogs"""
        await self._ensure_table_exists()
        self.bot.log(f"LSPD Invitation Service geladen.")
        self.bot.log(f"Source Server: {self.source_server_id}")
        self.bot.log(f"Anzahl konfigurierte Ziel-Server: {len(self.server_configs)}")
        
        for server_id, config in self.server_configs.items():
            self.bot.log(f"  - {config['name']} (ID: {server_id}) - Rollen: {config['monitored_roles']}")
        
        if not self.server_configs:
            self.bot.log("⚠️ WARNUNG: Invitation Service - Keine Server konfiguriert!", level='warning')
        
        # Teste Server-Verbindungen
        source_guild = self.bot.get_guild(self.source_server_id)
        if not source_guild:
            self.bot.log(f"❌ Source Server {self.source_server_id} nicht gefunden!", level='error')
        else:
            self.bot.log(f"✅ Source Server: {source_guild.name}")
        
        # Teste Ziel-Server
        for server_id, config in self.server_configs.items():
            target_guild = self.bot.get_guild(server_id)
            if not target_guild:
                self.bot.log(f"❌ Ziel-Server {config['name']} (ID: {server_id}) nicht gefunden!", level='error')
            else:
                self.bot.log(f"✅ Ziel-Server: {target_guild.name}")
                
                # Prüfe überwachte Rollen für diesen Server
                if source_guild:
                    found_roles = []
                    missing_roles = []
                    
                    for role_id in config['monitored_roles']:
                        role = source_guild.get_role(role_id)
                        if role:
                            found_roles.append(f"{role.name} ({role_id})")
                        else:
                            missing_roles.append(str(role_id))
                    
                    if found_roles:
                        self.bot.log(f"  ✅ {config['name']} - Gefundene Rollen: {', '.join(found_roles)}")
                    if missing_roles:
                        self.bot.log(f"  ❌ {config['name']} - Nicht gefundene Rollen: {', '.join(missing_roles)}", level='warning')

    async def _ensure_table_exists(self):
        """Erstellt die Tabelle für LSPD Officers falls sie nicht existiert"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            self.bot.log("Warnung: Datenbank-Pool nicht verfügbar", level='warning')
            return
            
        try:
            pool: aiomysql.Pool = self.bot.db_pool
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        CREATE TABLE IF NOT EXISTS lspd_officers (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id BIGINT NOT NULL UNIQUE,
                            callsign VARCHAR(50) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        )
                    """)
            self.bot.log("LSPD Officers Tabelle erfolgreich initialisiert", color=self.bot.Colors.GREEN if hasattr(self.bot, 'Colors') else None)
        except Exception as e:
            self.bot.log(f"Fehler beim Erstellen der LSPD Officers Tabelle: {e}", level='error')

    def _load_entries(self):
        """Lädt die Liste der offenen Einladungen aus der JSON-Datei"""
        if os.path.exists(self.pending_entries_file):
            try:
                with open(self.pending_entries_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_entries(self):
        """Speichert die aktuelle Liste der Einladungen in die JSON-Datei"""
        os.makedirs(os.path.dirname(self.pending_entries_file), exist_ok=True)
        with open(self.pending_entries_file, "w") as f:
            json.dump(self.pending_entries, f, indent=4)

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        """Hilfsfunktion für Datenbankabfragen"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return None
            
        pool: aiomysql.Pool = self.bot.db_pool
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(query, args)
                    if fetch == "one":
                        return await cursor.fetchone()
                    elif fetch == "all":
                        return await cursor.fetchall()
        except Exception as e:
            self.bot.log(f"Datenbankfehler: {e}", level='error')
            return None

    def _get_member_roles(self, member: discord.Member) -> Set[int]:
        """Gibt die Rollen-IDs eines Members zurück"""
        return set(role.id for role in member.roles)

    def _get_servers_user_can_access(self, member: discord.Member) -> List[int]:
        """Bestimmt zu welchen Servern ein User Zugang haben sollte"""
        member_roles = self._get_member_roles(member)
        accessible_servers = []
        
        for server_id, config in self.server_configs.items():
            required_roles = set(config['monitored_roles'])
            # Prüfe ob User mindestens eine der erforderlichen Rollen hat
            if member_roles.intersection(required_roles):
                accessible_servers.append(server_id)
        
        return accessible_servers

    def _get_new_server_access(self, member_before: discord.Member, member_after: discord.Member) -> List[Dict[str, Any]]:
        """
        Bestimmt zu welchen neuen Servern ein User Zugang erhalten hat.
        Returns Liste mit Dicts: [{'server_id': int, 'role_names': [str], 'added_role_ids': [int], 'needs_codename': bool}]
        """
        old_roles = self._get_member_roles(member_before)
        new_roles = self._get_member_roles(member_after)
        added_roles = new_roles - old_roles
        
        # Definiere welche Rollen einen Decknamen benötigen (nur die Oberrollen)
        codename_requiring_roles = {
            1316223852136628234,  # SWAT-Oberrolle
            1294106167122985082   # Detective-Oberrolle
        }
        
        new_access = []
        
        for server_id, config in self.server_configs.items():
            required_roles = set(config['monitored_roles'])
            
            # Prüfe ob User vorher Zugang hatte
            had_access_before = bool(old_roles.intersection(required_roles))
            # Prüfe ob User jetzt Zugang hat
            has_access_now = bool(new_roles.intersection(required_roles))
            
            # Wenn User neu Zugang erhalten hat
            if not had_access_before and has_access_now:
                # Finde welche der hinzugefügten Rollen für diesen Server relevant sind
                relevant_added_roles = added_roles.intersection(required_roles)
                
                if relevant_added_roles:
                    # Sammle Namen der relevanten Rollen
                    role_names = []
                    for role_id in relevant_added_roles:
                        role = member_after.guild.get_role(role_id)
                        if role:
                            role_names.append(role.name)
                    
                    # Prüfe ob eine der hinzugefügten Rollen einen Decknamen benötigt
                    needs_codename = bool(relevant_added_roles.intersection(codename_requiring_roles))
                    
                    new_access.append({
                        'server_id': server_id,
                        'server_name': config['name'],
                        'role_names': role_names,
                        'added_role_ids': list(relevant_added_roles),
                        'needs_codename': needs_codename
                    })
        
        return new_access

    async def ask_for_callsign(self, user: discord.User, server_access_list: List[Dict[str, Any]]):
        """Fragt den User nach seinem gewünschten Callsign für die neuen Server (nur wenn Deckname benötigt)"""
        try:
            # Prüfe ob überhaupt ein Deckname benötigt wird
            needs_any_codename = any(access['needs_codename'] for access in server_access_list)
            
            if not needs_any_codename:
                # Kein Deckname benötigt - sende direkte Einladungen
                await self.send_direct_invitations(user, server_access_list)
                return
            
            # Sammle alle Rollen und Server-Namen
            all_role_names = []
            server_names = []
            codename_servers = []
            
            for access in server_access_list:
                all_role_names.extend(access['role_names'])
                server_names.append(access['server_name'])
                if access['needs_codename']:
                    codename_servers.append(access['server_name'])
            
            # Entferne Duplikate
            unique_roles = list(dict.fromkeys(all_role_names))
            unique_servers = list(dict.fromkeys(server_names))
            unique_codename_servers = list(dict.fromkeys(codename_servers))
            
            roles_text = "**, **".join(unique_roles)
            servers_text = "**, **".join(unique_servers)
            codename_servers_text = "**, **".join(unique_codename_servers)
            
            embed = discord.Embed(
                title="🎭 Deckname für verdeckte Operationen erforderlich",
                description=f"Herzlichen Glückwunsch! Du hast {'die Rolle' if len(unique_roles) == 1 else 'die Rollen'} **{roles_text}** erhalten.",
                color=0x003366  # LSPD Blau
            )
            
            embed.add_field(
                name="🎖️ Neuer Zugang zu:",
                value=f"**{servers_text}**",
                inline=False
            )
            
            embed.add_field(
                name="🎭 Deckname erforderlich für:",
                value=f"**{codename_servers_text}**\n(Für verdeckte Operationen)",
                inline=False
            )
            
            embed.add_field(
                name="📋 Nächster Schritt",
                value="Bitte teile mir deinen gewünschten **Decknamen** mit.\n\n"
                      "Beispiele: `Shadow-1`, `Ghost-Alpha`, `Phoenix-6`, `Viper-X`\n\n"
                      "❗ **Wichtig:** Dies ist dein Deckname für verdeckte Missionen, nicht dein normaler Callsign!\n\n"
                      "Antworte einfach mit deinem gewünschten Decknamen auf diese Nachricht.",
                inline=False
            )
            
            embed.add_field(
                name="🔗 Was passiert dann?",
                value=f"Nach der Eingabe deines Decknamens erhältst du automatisch {'eine Einladung' if len(unique_servers) == 1 else 'Einladungen'} zu {'dem entsprechenden Server' if len(unique_servers) == 1 else 'den entsprechenden Servern'}.",
                inline=False
            )
            
            embed.set_footer(text="LSPD Special Operations Recruitment System")
            
            await user.send(embed=embed)
            self.bot.log(f"Deckname-Anfrage an {user.display_name} gesendet (Zugang zu: {', '.join(unique_servers)}, Deckname für: {', '.join(unique_codename_servers)})")
            
        except discord.Forbidden:
            self.bot.log(f"⚠️ Konnte keine DM an {user.display_name} senden - DMs deaktiviert. Einladung übersprungen.", level='warning')
            
            # Entferne aus pending entries da keine Kommunikation möglich
            if str(user.id) in self.pending_entries:
                del self.pending_entries[str(user.id)]
                self._save_entries()
                
            # Logge für Admin-Übersicht
            server_names = [access['server_name'] for access in server_access_list]
            self.bot.log(f"💔 EINLADUNG FEHLGESCHLAGEN: {user.display_name} ({user.id}) - Server: {', '.join(server_names)} - DMs deaktiviert", level='warning')

    async def send_direct_invitations(self, user: discord.User, server_access_list: List[Dict[str, Any]]):
        """Sendet direkte Einladungen ohne Deckname-Abfrage (für ASD, SHP etc.)"""
        try:
            # Erstelle Einladungen für alle Server
            server_ids = [access['server_id'] for access in server_access_list]
            invites = await self.create_invites_for_servers(server_ids)
            
            if not invites:
                self.bot.log(f"Fehler beim Erstellen von Einladungen für {user.display_name}", level='error')
                return
            
            # Sammle Informationen
            all_role_names = []
            server_names = []
            
            for access in server_access_list:
                all_role_names.extend(access['role_names'])
                server_names.append(access['server_name'])
            
            unique_roles = list(dict.fromkeys(all_role_names))
            unique_servers = list(dict.fromkeys(server_names))
            
            roles_text = "**, **".join(unique_roles)
            servers_text = "**, **".join(unique_servers)
            
            embed = discord.Embed(
                title="🚀 Willkommen bei den LSPD Special Units!",
                description=f"Herzlichen Glückwunsch! Du hast {'die Rolle' if len(unique_roles) == 1 else 'die Rollen'} **{roles_text}** erhalten und bist nun berechtigt, {'dem Server' if len(unique_servers) == 1 else 'den Servern'} **{servers_text}** beizutreten!",
                color=0x10b981  # Grün
            )
            
            # Füge Einladungen für jeden Server hinzu
            invite_text = ""
            for access in server_access_list:
                server_id = access['server_id']
                if server_id in invites:
                    invite_text += f"**{access['server_name']}:**\n{invites[server_id]}\n\n"
            
            if invite_text:
                embed.add_field(
                    name="🎯 Server-Einladungen",
                    value=f"{invite_text}⚠️ Diese Einladungen sind **24 Stunden gültig** und können jeweils nur **einmal verwendet** werden.",
                    inline=False
                )
            
            embed.add_field(
                name="📋 Nächste Schritte",
                value="1. Klicke auf die entsprechenden Einladungslinks\n"
                      "2. Tritt den Servern bei\n"
                      "3. Melde dich bei einem Commander\n"
                      "4. Erhalte deine Dienstanweisung",
                inline=False
            )
            
            embed.set_footer(text="Willkommen im Team! 🚁")
            
            await user.send(embed=embed)
            
            self.bot.log(f"Direkte Einladungen erfolgreich an {user.display_name} gesendet: {', '.join(unique_servers)}")
            
        except discord.Forbidden:
            self.bot.log(f"❌ Konnte direkte Einladung nicht an {user.display_name} senden (DMs deaktiviert)", level='warning')

    async def check_callsign_exists(self, callsign: str, exclude_user_id: int = None) -> bool:
        """Prüft ob ein Callsign bereits existiert"""
        try:
            if exclude_user_id:
                # Prüfe ob Callsign von anderem User verwendet wird
                result = await self._execute_query(
                    "SELECT user_id FROM lspd_officers WHERE callsign = %s AND user_id != %s",
                    (callsign, exclude_user_id), fetch="one"
                )
            else:
                # Prüfe ob Callsign überhaupt existiert
                result = await self._execute_query(
                    "SELECT user_id FROM lspd_officers WHERE callsign = %s",
                    (callsign,), fetch="one"
                )
            
            return result is not None
            
        except Exception as e:
            self.bot.log(f"Fehler beim Prüfen des Callsigns: {e}", level='error')
            return False

    async def save_callsign_to_db(self, user_id: int, callsign: str) -> Dict[str, Any]:
        """Speichert den Callsign in der Datenbank nach Verfügbarkeitsprüfung"""
        try:
            # Prüfe ob Callsign bereits von anderem User verwendet wird
            callsign_exists = await self.check_callsign_exists(callsign, exclude_user_id=user_id)
            
            if callsign_exists:
                return {
                    "success": False, 
                    "error": "callsign_exists",
                    "message": f"Der Callsign '{callsign}' ist bereits vergeben. Bitte wähle einen anderen."
                }
            
            # Speichere den Callsign
            await self._execute_query("""
                INSERT INTO lspd_officers (user_id, callsign) 
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE 
                callsign = VALUES(callsign),
                updated_at = CURRENT_TIMESTAMP
            """, (user_id, callsign))
            
            self.bot.log(f"Callsign '{callsign}' für User {user_id} gespeichert")
            return {"success": True}
            
        except Exception as e:
            self.bot.log(f"Fehler beim Speichern des Callsigns: {e}", level='error')
            return {
                "success": False,
                "error": "database_error", 
                "message": "Es gab einen Datenbankfehler beim Speichern deines Callsigns."
            }

    async def create_invite_to_server(self, server_id: int) -> str:
        """Erstellt eine Einladung zu einem spezifischen Server"""
        try:
            if server_id not in self.server_configs:
                return None
                
            config = self.server_configs[server_id]
            target_guild = self.bot.get_guild(server_id)
            
            if not target_guild:
                self.bot.log(f"Server {config['name']} (ID: {server_id}) nicht gefunden", level='error')
                return None
                
            # Suche nach dem konfigurierten Channel
            invite_channel = target_guild.get_channel(config['invite_channel_id'])
            if not invite_channel:
                # Fallback: Ersten verfügbaren Text-Channel verwenden
                invite_channel = next(
                    (ch for ch in target_guild.text_channels 
                     if ch.permissions_for(target_guild.me).create_instant_invite), 
                    None
                )
                
            if not invite_channel:
                self.bot.log(f"Kein geeigneter Channel für Einladung zu {config['name']} gefunden", level='error')
                return None
                
            # Erstelle Einladung (24 Stunden gültig, einmalige Verwendung)
            invite = await invite_channel.create_invite(
                max_age=86400,  # 24 Stunden
                max_uses=1,     # Einmalige Verwendung
                reason=f"Automatische {config['name']} Einladung nach Rollenvergabe"
            )
            
            return invite.url
            
        except Exception as e:
            self.bot.log(f"Fehler beim Erstellen der Einladung zu {server_id}: {e}", level='error')
            return None

    async def create_invites_for_servers(self, server_ids: List[int]) -> Dict[int, str]:
        """Erstellt Einladungen für mehrere Server"""
        invites = {}
        
        for server_id in server_ids:
            invite_url = await self.create_invite_to_server(server_id)
            if invite_url:
                invites[server_id] = invite_url
        
        return invites

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """
        Wird ausgelöst wenn ein Member einem Server beitritt.
        Prüft ob alle Rollen korrekt synchronisiert wurden und führt fehlende Syncs nach.
        """
        # Nur auf Ziel-Servern reagieren (nicht Source-Server)
        if member.guild.id == self.source_server_id:
            return
            
        # Prüfe ob es ein konfigurierter Ziel-Server ist
        if member.guild.id not in self.server_configs:
            return
        
        # Kurze Verzögerung damit Discord die Member-Daten lädt
        await asyncio.sleep(3)
        
        try:
            # Hole aktualisierte Member-Daten vom Ziel-Server
            target_member = await member.guild.fetch_member(member.id)
        except discord.NotFound:
            return
        
        self.bot.log(f"Invitation Service - {target_member.display_name} ist {member.guild.name} beigetreten - prüfe Sync-Status")
        
        # Hole den Source-Server Member
        source_guild = self.bot.get_guild(self.source_server_id)
        if not source_guild:
            return
            
        try:
            source_member = await source_guild.fetch_member(member.id)
        except discord.NotFound:
            self.bot.log(f"Invitation Service - {target_member.display_name} ist nicht auf dem Source-Server")
            return
        
        # Hole die aktuellen Rollen auf beiden Servern
        source_roles = self._get_member_roles(source_member)
        target_roles = self._get_member_roles(target_member)
        target_config = self.server_configs[member.guild.id]
        
        # Prüfe welche Rollen der User auf dem Source-Server hat, die für diesen Ziel-Server relevant sind
        relevant_source_roles = source_roles.intersection(set(target_config['monitored_roles']))
        
        if relevant_source_roles:
            self.bot.log(f"Invitation Service - {target_member.display_name} hat {len(relevant_source_roles)} relevante Source-Rollen für {member.guild.name}")
            
            # Optional: Triggere externe Sync-Überprüfung
            await self._request_external_sync_check(source_member, target_member, relevant_source_roles)
        
        else:
            self.bot.log(f"Invitation Service - {target_member.display_name} hat keine relevanten Rollen für {member.guild.name}")

    async def _request_external_sync_check(self, source_member, target_member, relevant_roles):
        """
        Triggert eine externe Sync-Überprüfung durch das Role Sync System.
        Da wir keine direkten Sync-Mappings haben, verwenden wir Events.
        """
        try:
            self.bot.log(f"Invitation Service - Triggere externe Sync-Überprüfung für {source_member.display_name}")
            
            # Für jetzt: Logge die Anfrage
            roles_list = ", ".join(str(r) for r in relevant_roles)
            self.bot.log(f"Invitation Service - Externe Sync-Anfrage: {source_member.display_name} für Rollen {roles_list}")
            
        except Exception as e:
            self.bot.log(f"Invitation Service - Fehler bei externer Sync-Anfrage: {e}", level='error')

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """
        Wird ausgelöst wenn sich Member-Eigenschaften ändern (z.B. Rollen)
        ÜBERWACHT NUR - VERGIBT KEINE ROLLEN!
        """
        
        # Prüfe ob es sich um den überwachten Server handelt
        if after.guild.id != self.source_server_id:
            return
            
        # Prüfe ob Server konfiguriert sind
        if not self.server_configs:
            return
            
        # Prüfe ob neue Rollen hinzugefügt wurden
        old_role_ids = self._get_member_roles(before)
        new_role_ids = self._get_member_roles(after)
        added_roles = new_role_ids - old_role_ids
        
        if not added_roles:
            return
            
        # Bestimme zu welchen neuen Servern User Zugang erhalten hat
        new_server_access = self._get_new_server_access(before, after)
        
        if not new_server_access:
            return
            
        # Logge neue Zugänge
        for access in new_server_access:
            codename_status = " (benötigt Deckname)" if access['needs_codename'] else " (direkte Einladung)"
            self.bot.log(f"User {after.display_name} ({after.id}) hat Zugang zu {access['server_name']} erhalten (Rollen: {', '.join(access['role_names'])}){codename_status}")
        
        # Prüfe ob User bereits auf einem der Ziel-Server ist
        already_member_of = []
        for access in new_server_access:
            target_guild = self.bot.get_guild(access['server_id'])
            if target_guild:
                target_member = target_guild.get_member(after.id)
                if target_member:
                    already_member_of.append(access['server_name'])
        
        if already_member_of:
            self.bot.log(f"User {after.display_name} ist bereits Mitglied von: {', '.join(already_member_of)} - überspringe entsprechende Einladungen")
            
            # Filtere Server aus, auf denen User bereits ist
            new_server_access = [access for access in new_server_access 
                               if access['server_name'] not in already_member_of]
            
            if not new_server_access:
                return
        
        # Prüfe ob User bereits eine ausstehende Einladung hat
        if str(after.id) in self.pending_entries:
            # Aktualisiere die bestehende Einladung
            existing_data = self.pending_entries[str(after.id)]
            
            # Füge neue Server-Zugänge hinzu
            for access in new_server_access:
                server_id = access['server_id']
                if server_id not in existing_data['server_access']:
                    existing_data['server_access'][server_id] = access
            
            existing_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            self._save_entries()
            
            # Sammle alle Server-Namen für Log
            all_server_names = [access['server_name'] for access in existing_data['server_access'].values()]
            self.bot.log(f"Aktualisierte ausstehende Einladung für {after.display_name}: {', '.join(all_server_names)}")
            
            # Optional: Sende Update-Nachricht an User
            try:
                new_server_names = [access['server_name'] for access in new_server_access]
                
                # Prüfe ob Deckname benötigt wird
                needs_codename = any(a.get('needs_codename', False) for a in existing_data['server_access'].values())
                input_type = "Decknamen" if needs_codename else "Callsign"
                
                embed = discord.Embed(
                    title="🎖️ Weitere Berechtigung erhalten!",
                    description=f"Du hast Zugang zu weiteren Servern erhalten: **{', '.join(new_server_names)}**\n\nDeine Anfrage ist noch aktiv. Bitte teile mir weiterhin deinen gewünschten {input_type} mit.",
                    color=0x003366
                )
                await after.send(embed=embed)
            except discord.Forbidden:
                pass  # DM fehlgeschlagen, aber nicht kritisch
                
            return
        
        # Unterscheide zwischen Deckname-erforderlich und direkter Einladung
        needs_any_codename = any(access['needs_codename'] for access in new_server_access)
        
        if needs_any_codename:
            # Speichere die Informationen für den Deckname-Dialog
            server_access_dict = {}
            for access in new_server_access:
                server_access_dict[access['server_id']] = access
            
            self.pending_entries[str(after.id)] = {
                'guild_id': after.guild.id,
                'server_access': server_access_dict,
                'user': {
                    'id': after.id,
                    'name': after.name,
                    'display_name': after.display_name
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            self._save_entries()
            
            # Sende DM für Deckname-Eingabe
            await self.ask_for_callsign(after, new_server_access)
        else:
            # Direkte Einladung ohne Deckname
            await self.ask_for_callsign(after, new_server_access)  # Diese Funktion erkennt automatisch wenn kein Deckname benötigt wird

    @commands.Cog.listener()
    async def on_message(self, message):
        """Verarbeitet eingehende Nachrichten (für Callsign-Eingabe)"""
        
        # Ignoriere Bot-Nachrichten
        if message.author.bot:
            return
            
        # Prüfe ob es eine DM ist und der User eine ausstehende Einladung hat
        if isinstance(message.channel, discord.DMChannel) and str(message.author.id) in self.pending_entries:
            
            callsign = message.content.strip()
            
            # Hole pending entry
            pending_data = self.pending_entries[str(message.author.id)]
            server_access_list = list(pending_data['server_access'].values())
            
            # Prüfe ob ein Deckname benötigt wird
            needs_codename = any(access['needs_codename'] for access in server_access_list)
            
            if needs_codename:
                # Deckname-Validierung
                if len(callsign) < 2 or len(callsign) > 20:
                    await message.channel.send(
                        "❌ **Ungültiger Deckname!**\n"
                        "Der Deckname muss zwischen 2 und 20 Zeichen lang sein.\n"
                        "Bitte versuche es erneut."
                    )
                    return
                    
                # Entferne gefährliche Zeichen (nur Alphanumerisch, Bindestrich und Unterstrich)
                import re
                if not re.match(r'^[a-zA-Z0-9_-]+$', callsign):
                    await message.channel.send(
                        "❌ **Ungültiger Deckname!**\n"
                        "Nur Buchstaben, Zahlen, Bindestriche (-) und Unterstriche (_) sind erlaubt.\n"
                        "Bitte versuche es erneut."
                    )
                    return
                
                # Speichere Callsign in Datenbank als Deckname (mit Verfügbarkeitsprüfung)
                result = await self.save_callsign_to_db(message.author.id, callsign)
                
                if not result["success"]:
                    if result["error"] == "callsign_exists":
                        # Deckname bereits vergeben
                        await message.channel.send(
                            f"❌ **Deckname bereits vergeben!**\n"
                            f"Der Deckname `{callsign}` ist bereits von einem anderen Officer in Verwendung.\n\n"
                            f"Bitte wähle einen anderen Deckname und versuche es erneut."
                        )
                        return
                    else:
                        # Anderer Fehler (Datenbankfehler etc.)
                        await message.channel.send(
                            f"❌ **Fehler beim Speichern!**\n"
                            f"{result['message']}\n"
                            f"Bitte kontaktiere einen Administrator."
                        )
                        return
                
                # Erstelle Einladungen für alle Server
                server_ids = [access['server_id'] for access in server_access_list]
                invites = await self.create_invites_for_servers(server_ids)
                
                if not invites:
                    await message.channel.send(
                        "❌ **Fehler bei der Einladung!**\n"
                        "Es gab ein Problem beim Erstellen der Server-Einladungen. Bitte kontaktiere einen Administrator."
                    )
                    return
                
                # Erfolgsnachricht mit Einladungen
                embed = discord.Embed(
                    title="🎭 Deckname registriert!",
                    description=f"Dein Deckname **{callsign}** wurde erfolgreich registriert.",
                    color=0x10b981  # Grün
                )
                
                # Füge Einladungen für jeden Server hinzu
                invite_text = ""
                for access in server_access_list:
                    server_id = access['server_id']
                    if server_id in invites:
                        invite_text += f"**{access['server_name']}:**\n{invites[server_id]}\n\n"
                
                if invite_text:
                    embed.add_field(
                        name="🎯 Server-Einladungen",
                        value=f"{invite_text}⚠️ Diese Einladungen sind **24 Stunden gültig** und können jeweils nur **einmal verwendet** werden.",
                        inline=False
                    )
                
                embed.add_field(
                    name="🎭 Wichtiger Hinweis",
                    value=f"Dein Deckname `{callsign}` ist nur für **verdeckte Operationen** zu verwenden. Für normale Einsätze erhältst du einen separaten Callsign.",
                    inline=False
                )
                
                embed.add_field(
                    name="📋 Nächste Schritte",
                    value="1. Klicke auf die entsprechenden Einladungslinks\n"
                          "2. Tritt den Servern bei\n"
                          "3. Melde dich bei einem Commander\n"
                          "4. Erhalte deine verdeckten Missionsanweisungen",
                    inline=False
                )
                
                embed.set_footer(text="Willkommen bei den Special Operations! 🎭")
                
                await message.channel.send(embed=embed)
                
                server_names = [access['server_name'] for access in server_access_list]
                self.bot.log(f"Deckname-Einladungen erfolgreich an {message.author.display_name} (Deckname: {callsign}) gesendet: {', '.join(server_names)}")
                
            else:
                # Sollte hier eigentlich nicht ankommen, da direkte Einladungen bereits gesendet wurden
                await message.channel.send("❌ Ein unerwarteter Fehler ist aufgetreten. Bitte kontaktiere einen Administrator.")
                return
            
            # Entferne aus pending invites
            del self.pending_entries[str(message.author.id)]
            self._save_entries()

    # --- Admin Slash Commands ---
    
    lspd_group = app_commands.Group(name="lspd", description="LSPD Multi-Server Invitation System Commands")
    
    @lspd_group.command(name="status", description="Zeigt LSPD Bot-Status")
    @app_commands.default_permissions(administrator=True)
    async def lspd_status(self, interaction: discord.Interaction):
        """Admin-Command: Zeigt LSPD Bot-Status"""
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="🤖 LSPD Multi-Server Bot Status",
            color=0x003366
        )
        
        embed.add_field(
            name="🏢 Konfigurierte Server",
            value=f"Source Guild: {self.source_server_id}\nAnzahl Ziel-Server: {len(self.server_configs)}",
            inline=False
        )
        
        # Server-Details
        server_details = ""
        for server_id, config in self.server_configs.items():
            server_details += f"**{config['name']}** (ID: {server_id})\n"
            server_details += f"  └ Rollen: {len(config['monitored_roles'])} konfiguriert\n"
        
        if server_details:
            embed.add_field(
                name="📊 Server-Details",
                value=server_details,
                inline=False
            )
        
        embed.add_field(
            name="⏳ Ausstehende Einladungen",
            value=f"Anzahl: {len(self.pending_entries)}",
            inline=False
        )
        
        # Server-Status prüfen
        source_guild = self.bot.get_guild(self.source_server_id)
        status_text = f"Source: {'✅ ' + source_guild.name if source_guild else '❌ Nicht gefunden'}\n"
        
        for server_id, config in self.server_configs.items():
            target_guild = self.bot.get_guild(server_id)
            status_text += f"{config['name']}: {'✅ Verbunden' if target_guild else '❌ Nicht gefunden'}\n"
        
        embed.add_field(
            name="🌐 Server-Verbindungen",
            value=status_text,
            inline=False
        )
        
        # Datenbank-Status prüfen
        db_status = "✅ Verbunden" if hasattr(self.bot, 'db_pool') and self.bot.db_pool else "❌ Nicht verbunden"
        embed.add_field(
            name="🗄️ Datenbank",
            value=db_status,
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @lspd_group.command(name="pending", description="Zeigt ausstehende Einladungen")
    @app_commands.default_permissions(administrator=True)
    async def lspd_pending(self, interaction: discord.Interaction):
        """Admin-Command: Zeigt ausstehende Einladungen"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.pending_entries:
            await interaction.followup.send("📭 Keine ausstehenden Einladungen.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="⏳ Ausstehende LSPD Einladungen",
            color=0xf59e0b
        )
        
        for user_id, data in list(self.pending_entries.items())[:10]:  # Max 10 zeigen
            user = self.bot.get_user(int(user_id))
            user_name = user.display_name if user else f"User {user_id}"
            
            timestamp_str = "Unbekannt"
            if 'timestamp' in data:
                try:
                    timestamp_dt = datetime.fromisoformat(data['timestamp'])
                    timestamp_str = f"<t:{int(timestamp_dt.timestamp())}:R>"
                except:
                    timestamp_str = "Parsing-Fehler"
            
            # Sammle Server-Namen
            server_names = []
            if 'server_access' in data:
                for access in data['server_access'].values():
                    server_names.append(access['server_name'])
            
            embed.add_field(
                name=f"👤 {user_name}",
                value=f"Server: {', '.join(server_names) if server_names else 'Unbekannt'}\nErstellt: {timestamp_str}",
                inline=False
            )
        
        if len(self.pending_entries) > 10:
            embed.set_footer(text=f"... und {len(self.pending_entries) - 10} weitere")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @lspd_group.command(name="force_invite", description="Erstellt manuell eine Einladung für einen User zu einem bestimmten Server")
    @app_commands.describe(
        user="Der User der eingeladen werden soll",
        server="Ziel-Server auswählen",
        callsign="Der gewünschte Callsign für den User"
    )
    @app_commands.default_permissions(administrator=True)
    async def lspd_force_invite(self, interaction: discord.Interaction, user: discord.Member, server: str, callsign: str):
        """Admin-Command: Manueller Einladungsprozess für bestimmten Server"""
        await interaction.response.defer(ephemeral=True)
        
        # Finde Server ID basierend auf Namen oder ID
        target_server_id = None
        target_config = None
        
        # Versuche erst als ID
        if server.isdigit():
            server_id = int(server)
            if server_id in self.server_configs:
                target_server_id = server_id
                target_config = self.server_configs[server_id]
        
        # Versuche als Name
        if not target_server_id:
            for server_id, config in self.server_configs.items():
                if config['name'].lower() == server.lower():
                    target_server_id = server_id
                    target_config = config
                    break
        
        if not target_server_id:
            available_servers = [f"{config['name']} (ID: {sid})" for sid, config in self.server_configs.items()]
            await interaction.followup.send(
                f"❌ Server '{server}' nicht gefunden.\n\n"
                f"Verfügbare Server:\n{chr(10).join(available_servers)}", 
                ephemeral=True
            )
            return
        
        try:
            # Prüfe ob Callsign bereits existiert
            callsign_exists = await self.check_callsign_exists(callsign, exclude_user_id=user.id)
            if callsign_exists:
                await interaction.followup.send(f"❌ Der Callsign `{callsign}` ist bereits vergeben. Bitte wähle einen anderen.", ephemeral=True)
                return
            
            # Speichere Callsign
            result = await self.save_callsign_to_db(user.id, callsign)
            if not result["success"]:
                await interaction.followup.send(f"❌ Fehler beim Speichern des Callsigns: {result['message']}", ephemeral=True)
                return
                
            # Erstelle Einladung
            invite_url = await self.create_invite_to_server(target_server_id)
            if not invite_url:
                await interaction.followup.send(f"❌ Fehler beim Erstellen der Einladung für {target_config['name']}", ephemeral=True)
                return
                
            # Sende Einladung per DM
            try:
                embed = discord.Embed(
                    title="🚁 Manuelle LSPD Einladung",
                    description=f"Du wurdest manuell zu **{target_config['name']}** eingeladen!\n\nCallsign: **{callsign}**",
                    color=0x003366
                )
                embed.add_field(
                    name="🔗 Einladungslink",
                    value=invite_url,
                    inline=False
                )
                embed.add_field(
                    name="👨‍💼 Eingeladen von",
                    value=interaction.user.mention,
                    inline=True
                )
                
                await user.send(embed=embed)
                
                # Erfolgsnachricht an Admin
                success_embed = discord.Embed(
                    title="✅ Einladung erfolgreich gesendet",
                    description=f"**User:** {user.mention}\n**Server:** {target_config['name']}\n**Callsign:** {callsign}",
                    color=0x10b981
                )
                success_embed.add_field(name="📤 Status", value="DM erfolgreich gesendet", inline=True)
                success_embed.add_field(name="🔗 Einladung", value="24h gültig, einmalige Verwendung", inline=True)
                
                await interaction.followup.send(embed=success_embed, ephemeral=True)
                
            except discord.Forbidden:
                # Wenn DM fehlschlägt, trotzdem Callsign in DB aber Info an Admin
                error_embed = discord.Embed(
                    title="⚠️ DM fehlgeschlagen",
                    description=f"**User:** {user.mention}\n**Server:** {target_config['name']}\n**Callsign:** {callsign} (gespeichert)",
                    color=0xffa500
                )
                error_embed.add_field(
                    name="❌ Problem", 
                    value=f"{user.mention} hat DMs deaktiviert", 
                    inline=False
                )
                error_embed.add_field(
                    name="🔗 Einladungslink", 
                    value=f"Manuell weiterleiten:\n{invite_url}", 
                    inline=False
                )
                
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                
        except Exception as e:
            self.bot.log(f"Fehler bei manueller Einladung: {e}", level='error')
            await interaction.followup.send(f"❌ Unerwarteter Fehler: {str(e)}", ephemeral=True)

    @lspd_force_invite.autocomplete('server')
    async def server_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete für Server-Auswahl"""
        choices = []
        for server_id, config in self.server_configs.items():
            server_display = f"{config['name']} (ID: {server_id})"
            if current.lower() in server_display.lower():
                choices.append(app_commands.Choice(name=server_display, value=str(server_id)))
        
        return choices[:25]  # Discord Limit

    @lspd_group.command(name="cleanup", description="Bereinigt alte ausstehende Einladungen")
    @app_commands.describe(hours="Ältere Einladungen als X Stunden werden entfernt (Standard: 24)")
    @app_commands.default_permissions(administrator=True)
    async def lspd_cleanup(self, interaction: discord.Interaction, hours: int = 24):
        """Admin-Command: Bereinigt alte ausstehende Einladungen"""
        await interaction.response.defer(ephemeral=True)
        
        if hours < 1 or hours > 168:  # Max 7 Tage
            await interaction.followup.send("❌ Stunden müssen zwischen 1 und 168 (7 Tage) liegen.", ephemeral=True)
            return
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        removed_count = 0
        
        # Erstelle Liste der zu entfernenden Einträge
        to_remove = []
        for user_id, data in self.pending_entries.items():
            if 'timestamp' in data:
                try:
                    entry_time = datetime.fromisoformat(data['timestamp'])
                    if entry_time < cutoff_time:
                        to_remove.append(user_id)
                except:
                    # Bei Parsing-Fehlern auch entfernen
                    to_remove.append(user_id)
        
        # Entferne alte Einträge
        for user_id in to_remove:
            del self.pending_entries[user_id]
            removed_count += 1
        
        # Speichere Änderungen
        if removed_count > 0:
            self._save_entries()
        
        embed = discord.Embed(
            title="🧹 Cleanup abgeschlossen",
            color=0x10b981
        )
        
        embed.add_field(
            name="📊 Statistiken",
            value=f"**Entfernt:** {removed_count}\n**Verbleibend:** {len(self.pending_entries)}\n**Alter:** Älter als {hours} Stunden",
            inline=False
        )
        
        if removed_count == 0:
            embed.add_field(name="ℹ️ Ergebnis", value="Keine alten Einträge gefunden.", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: "MyBot"):
    # Registriere die App Commands Group am Bot
    await bot.add_cog(LspdInvitationService(bot))
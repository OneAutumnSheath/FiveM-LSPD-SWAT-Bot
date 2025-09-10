# services/lspd_exit_service.py

import discord
from discord.ext import commands
import os
import aiomysql
from typing import TYPE_CHECKING, List, Dict, Set

if TYPE_CHECKING:
    from main import MyBot

class LspdExitService(commands.Cog):
    """
    Service der automatisch User von konfigurierten Ziel-Servern entfernt,
    wenn sie die entsprechenden überwachten Rollen auf dem Source-Server verlieren.
    Jeder Ziel-Server kann eigene überwachte Rollen haben.
    """
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "LspdExitService"
        
        # Konfiguration - wird aus .env geladen
        self.source_server_id = None
        self.server_configs: Dict[int, Dict] = {}  # server_id -> {name, monitored_roles}
        
        # Lade Konfiguration aus Umgebungsvariablen
        self._load_config()

    def _load_config(self):
        """Lädt Konfiguration aus Umgebungsvariablen"""
        self.source_server_id = int(os.getenv('SOURCE_GUILD_ID', 0))
        
        # Lade bis zu 3 Ziel-Server mit ihren spezifischen Rollen
        for i in range(1, 4):  # 1, 2, 3
            target_id = os.getenv(f'TARGET_GUILD_ID_{i}', '').strip()
            target_name = os.getenv(f'TARGET_GUILD_NAME_{i}', f'Server {i}').strip()
            monitored_roles_str = os.getenv(f'MONITORED_ROLE_IDS_{i}', '').strip()
            
            if target_id and target_id.isdigit():
                server_id = int(target_id)
                monitored_roles = []
                
                # Parse die überwachten Rollen für diesen Server
                if monitored_roles_str:
                    try:
                        monitored_roles = [int(rid.strip()) for rid in monitored_roles_str.split(',') if rid.strip()]
                    except ValueError as e:
                        self.bot.log(f"Exit Service - Fehler beim Laden der Rollen-IDs für {target_name}: {e}", level='error')
                        continue
                
                if monitored_roles:  # Nur Server mit Rollen hinzufügen
                    self.server_configs[server_id] = {
                        'name': target_name,
                        'monitored_roles': monitored_roles
                    }
                    self.bot.log(f"Exit Service - Server {i}: {target_name} (ID: {server_id}) - {len(monitored_roles)} überwachte Rollen")
                else:
                    self.bot.log(f"Exit Service - Server {i} ({target_name}) übersprungen - keine Rollen konfiguriert", level='warning')
        
        if not self.server_configs:
            self.bot.log("Exit Service - Keine Ziel-Server mit Rollen konfiguriert!", level='warning')

    async def cog_load(self):
        """Initialisierung beim Laden des Cogs"""
        self.bot.log(f"LSPD Exit Service geladen.")
        self.bot.log(f"Source Server: {self.source_server_id}")
        self.bot.log(f"Anzahl konfigurierte Ziel-Server: {len(self.server_configs)}")
        
        for server_id, config in self.server_configs.items():
            self.bot.log(f"  - {config['name']} (ID: {server_id}) - Rollen: {config['monitored_roles']}")
        
        if not self.server_configs:
            self.bot.log("⚠️ WARNUNG: Exit Service - Keine Server konfiguriert!", level='warning')

    async def _execute_query(self, query: str, args: tuple = None):
        """Hilfsfunktion für Datenbankabfragen"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            self.bot.log("Exit Service - Datenbank-Pool nicht verfügbar", level='warning')
            return
            
        pool: aiomysql.Pool = self.bot.db_pool
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, args)
        except Exception as e:
            self.bot.log(f"Exit Service - Datenbankfehler: {e}", level='error')

    async def _delete_callsign_from_db(self, user_id: int) -> bool:
        """Löscht den Callsign des Users aus der Datenbank"""
        try:
            await self._execute_query(
                "DELETE FROM lspd_officers WHERE user_id = %s",
                (user_id,)
            )
            self.bot.log(f"Exit Service - Callsign für User {user_id} aus Datenbank gelöscht")
            return True
        except Exception as e:
            self.bot.log(f"Exit Service - Fehler beim Löschen des Callsigns für User {user_id}: {e}", level='error')
            return False

    def _get_member_roles(self, member: discord.Member) -> Set[int]:
        """Gibt die Rollen-IDs eines Members zurück"""
        return set(role.id for role in member.roles)

    def _has_required_roles_for_server(self, member: discord.Member, server_id: int) -> bool:
        """Prüft ob ein Member die erforderlichen Rollen für einen bestimmten Server hat"""
        if server_id not in self.server_configs:
            return False
            
        member_role_ids = self._get_member_roles(member)
        required_roles = set(self.server_configs[server_id]['monitored_roles'])
        
        # Prüfe ob es eine Überschneidung gibt
        has_roles = bool(member_role_ids.intersection(required_roles))
        
        return has_roles

    def _get_servers_to_kick_from(self, member_before: discord.Member, member_after: discord.Member) -> List[int]:
        """
        Bestimmt von welchen Servern ein User gekickt werden soll.
        Returns Liste der Server-IDs von denen gekickt werden soll.
        """
        servers_to_kick = []
        
        for server_id, config in self.server_configs.items():
            # Hatte der User vorher Zugang zu diesem Server?
            had_access_before = self._has_required_roles_for_server(member_before, server_id)
            # Hat der User jetzt noch Zugang?
            has_access_now = self._has_required_roles_for_server(member_after, server_id)
            
            # Wenn User Zugang verloren hat, von diesem Server kicken
            if had_access_before and not has_access_now:
                servers_to_kick.append(server_id)
                
                # Logge welche Rollen für diesen Server verloren wurden
                before_roles = self._get_member_roles(member_before)
                after_roles = self._get_member_roles(member_after)
                lost_roles = before_roles - after_roles
                
                server_monitored_roles = set(config['monitored_roles'])
                lost_monitored_roles = lost_roles.intersection(server_monitored_roles)
                
                if lost_monitored_roles:
                    lost_role_names = []
                    for role_id in lost_monitored_roles:
                        role = member_before.guild.get_role(role_id)
                        if role:
                            lost_role_names.append(role.name)
                    
                    self.bot.log(f"Exit Service - {member_after.display_name} verliert Zugang zu {config['name']} (verlorene Rollen: {', '.join(lost_role_names)})")
        
        return servers_to_kick

    def _get_servers_user_had_access_to(self, member: discord.Member) -> List[int]:
        """Bestimmt zu welchen Servern ein User Zugang hatte (für member_remove Event)"""
        servers_with_access = []
        
        for server_id, config in self.server_configs.items():
            if self._has_required_roles_for_server(member, server_id):
                servers_with_access.append(server_id)
        
        return servers_with_access

    async def _kick_from_server(self, server_id: int, user_id: int, reason: str, user_name: str = "Unknown") -> bool:
        """Kickt einen User von einem spezifischen Server"""
        if server_id not in self.server_configs:
            return False
            
        config = self.server_configs[server_id]
        target_guild = self.bot.get_guild(server_id)
        
        if not target_guild:
            self.bot.log(f"Exit Service - Server {config['name']} (ID: {server_id}) nicht gefunden", level='error')
            return False

        try:
            # Hole das Mitglied vom Ziel-Server
            member_to_kick = await target_guild.fetch_member(user_id)
            await member_to_kick.kick(reason=reason)
            
            self.bot.log(f"Exit Service - {member_to_kick.display_name} (ID: {user_id}) wurde von {config['name']} gekickt. Grund: {reason}")
            return True
            
        except discord.NotFound:
            # User war nicht auf dem Server
            self.bot.log(f"Exit Service - User {user_name} (ID: {user_id}) war nicht auf {config['name']}")
            return False
        except discord.Forbidden:
            self.bot.log(f"Exit Service - Keine Berechtigung, User {user_name} von {config['name']} zu kicken", level='error')
            return False
        except Exception as e:
            self.bot.log(f"Exit Service - Unerwarteter Fehler beim Kicken von {user_name} von {config['name']}: {e}", level='error')
            return False

    async def _kick_from_servers(self, server_ids: List[int], user_id: int, reason: str, user_name: str = "Unknown"):
        """Kickt einen User von den angegebenen Servern"""
        if not server_ids:
            return
        
        successful_kicks = 0
        
        # Versuche von allen angegebenen Servern zu kicken
        for server_id in server_ids:
            success = await self._kick_from_server(server_id, user_id, reason, user_name)
            if success:
                successful_kicks += 1
        
        # Lösche Callsign aus Datenbank wenn von mindestens einem Server gekickt
        if successful_kicks > 0:
            await self._delete_callsign_from_db(user_id)
        
        server_names = [self.server_configs[sid]['name'] for sid in server_ids if sid in self.server_configs]
        self.bot.log(f"Exit Service - {user_name} wurde von {successful_kicks}/{len(server_ids)} Servern entfernt ({', '.join(server_names)})")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Wird ausgelöst, wenn sich die Rollen eines Mitglieds ändern.
        Kickt User von Servern, wenn sie die entsprechenden Rollen verlieren.
        """
        
        # Reagiere nur auf Änderungen auf dem Source-Server
        if before.guild.id != self.source_server_id:
            return
            
        # Prüfe ob Server konfiguriert sind
        if not self.server_configs:
            return

        # Prüfe ob überhaupt Rollen entfernt wurden
        old_role_ids = self._get_member_roles(before)
        new_role_ids = self._get_member_roles(after)
        removed_roles = old_role_ids - new_role_ids
        
        if not removed_roles:
            return  # Keine Rollen entfernt
        
        # Bestimme von welchen Servern gekickt werden soll
        servers_to_kick = self._get_servers_to_kick_from(before, after)
        
        if not servers_to_kick:
            return  # Kein Zugang zu Servern verloren
        
        # Kick von den entsprechenden Servern
        reason = f"Erforderliche Rollen auf dem Hauptserver verloren"
        await self._kick_from_servers(servers_to_kick, after.id, reason, after.display_name)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Wird ausgelöst, wenn ein Mitglied den Source-Server verlässt.
        Kickt automatisch von allen Servern zu denen der User Zugang hatte.
        """
        
        # Reagiere nur auf Abgänge vom Source-Server
        if member.guild.id != self.source_server_id:
            return
        
        # Prüfe ob Server konfiguriert sind
        if not self.server_configs:
            return
        
        # Bestimme von welchen Servern gekickt werden soll
        servers_with_access = self._get_servers_user_had_access_to(member)
        
        if not servers_with_access:
            return  # User hatte keinen Zugang zu überwachten Servern
        
        # Kick von allen Servern zu denen User Zugang hatte
        server_names = [self.server_configs[sid]['name'] for sid in servers_with_access]
        self.bot.log(f"Exit Service - {member.display_name} hat den Source-Server verlassen (hatte Zugang zu: {', '.join(server_names)})")
        
        reason = f"Hat den Hauptserver verlassen"
        await self._kick_from_servers(servers_with_access, member.id, reason, member.display_name)

async def setup(bot: "MyBot"):
    await bot.add_cog(LspdExitService(bot))
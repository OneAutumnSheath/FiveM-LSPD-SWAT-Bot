import discord
from discord.ext import commands
import asyncio
import time

class RoleSyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False  # Track wenn Bot ready ist
        
        # Server IDs
        self.SERVERS = {
            'LSPD': 934974535369891840,  # DEINE_LSPD_SERVER_ID
            'SPECIAL_UNITS': 1391787690625728625,  # DEINE_SPECIAL_UNITS_SERVER_ID
            'UNITS':  1227968932342927380
        }
        
        # Rollen-Synchronisation: LSPD Server -> Special Units Server
        self.SYNC_ROLES = {
            # LSPD Server -> Special Units Server
            self.SERVERS['LSPD']: {
                # SWAT Rollen
                1316223852136628234: 1395463372215947324, # SWAT-Oberrolle
                1187452851119722646: 1395462422331920394, # SWAT-Rookie
                1204733801591214100: 1395462369605320897, # SWAT-Officer
                1039282890011324446: 1395462265582391327, # SWAT-Sergeant
                1234564137191866428: 1395460834439729343, # SWAT-Lieutenant
                1053391614246133872: 1395462201137172581, # SWAT-Commander
                1293333665258148000: 1395462134342619157, # SWAT-CoDirect
                935018728104534117: 1395462087249104918, # SWAT-Direct
                
                # ASD Rollen
                1401269846913585192: 1398516923473592401, # ASD-Oberrolle
                1325637503184670783: 1398517312218333184, # ASD-FlightStudent
                1325637796806787134: 1398517270577156197, # ASD-FlightOfficer
                1307817641448181791: 1398517229053542552, # ASD-FlightSergeant
                1307816089618616461: 1398517195621011558, # ASD-FlightCaptain
                1307815743911497810: 1398517135470362665, # ASD-FlightCommander
                1401271341449089034: 1401271903682822286, # ASD-CoDirect
                1401269389793427558: 1401271990094139422, # ASD-Director
                
                # Detective Rollen
                1294106167122985082: 1395458451588513822, # Detective-Oberrolle
                1294014237844443230: 1395461339891109972, # Detective-Rekrut
                1294014095116206110: 1395461294559068212, # Detective-Officer
                1294013934734671964: 1395469223710691338, # Detective-Sergeant
                1294013552364879903: 1395460902278533181, # Detective-Lieutenant
                1294013303776874496: 1395460771194081371, # Detective-CoDirect
                1280940167032602734: 1395460732442906674, # Detective-Direct
                
                # SHP Rollen
                1212825535005204521: 1395458236437500008, # SHP-Oberrolle
                1325631255101968454: 1395462998818295930, # SHP-Rookie
                1325631253189361795: 1395462952114458706, # SHP-Trooper
                1395498540402479134: 1395498464946946109, # SHP-SeniorTrooper
                1212825593796890694: 1395462878554886144, # SHP-HeadTrooper
                1212825879898759241: 1395462699663757312, # SHP-CoDirect
                1212825936592896122: 1395462736984670258, # SHP-Direct
            }
        }
        
        # LSPD Server -> UNITS Server (nur IA, PA, HR, BIKERS)
        self.SYNC_ROLES_UNITS = {
            self.SERVERS['LSPD']: {
                # IA Rollen -> UNITS
                1303452597709176917: 1303453417888288788, # IA-Direct
                1303452678915100703: 1303453417888288788, # IA-CoDirect
                1303452683402874952: 1303453421793316974, # IA-Instructor
                1303452595008049242: 1303453422170804275, # IA
                
                # PA Rollen -> UNITS
                935017286442561606: 1227968932355244119, # PA-Direct
                1117385633548226561: 1227968932355244119, # PA-CoDirect
                1067448372744687656: 1227995470824083486, # PA-Instructor
                935017371146522644: 1227968932355244118, # PA
                
                # HR Rollen -> UNITS
                935016743431188500: 1227968932355244117, # HR-Direct
                1117385689789640784: 1231227968932355244117123, # HR-CoDirect
                1068295101731831978: 1227995141772542012, # HR-Instructor
                935017143467147294: 1227968932355244116, # HR
                
                # BIKERS Rollen -> UNITS
                1356683996100300931: 1356684667612434754, # BIKERS-Direct
                1356684087024291952: 1356684667612434754, # BIKERS-CoDirect
                1356684286354526219: 1375057593185075210, # Road-Lead BIKERS
                1356684451597254766: 1356684746020749474, # BIKERS-Member
                1356684541204365375: 1356684746020749474, # BIKERS
            }
        }
        
        # Zusätzliche Rollen die automatisch vergeben werden (nur Special Units)
        self.AUTO_ROLES = {
            self.SERVERS['SPECIAL_UNITS']: {
                1395463372215947324: [1395463588394565672, 1395463299956740267],
                1395458451588513822: [1395463588394565672, 1395463299956740267],
                1398516923473592401: [1395463588394565672, 1395463299956740267],
                1395458236437500008: [1395463588394565672, 1395463299956740267]
            }
        }
        
        # Set um Endlosschleifen zu vermeiden
        self.processed_actions = set()
        
        # Rollen die eine Decknamen-Abfrage auslösen
        self.CODENAME_ROLES = [
            1395463372215947324,  # SWAT
            1395458451588513822   # Detective
        ]
        
        # Rollen die eine Einladung auslösen (aber keine Decknamen-Abfrage)
        self.INVITE_ONLY_ROLES = [
            1398516923473592401,  # ASD
            1395458236437500008   # SHP
        ]
        
        # Alle Rollen die eine Einladung bekommen (Codename + Invite-Only)
        self.ALL_INVITE_ROLES = self.CODENAME_ROLES + self.INVITE_ONLY_ROLES
        
        # In-Memory Storage für Decknamen (sollte später durch Datenbank ersetzt werden)
        self.codenames = {}  # user_id: {"codename": str, "set_by": user_id, "timestamp": timestamp}
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Wird ausgeführt wenn der Bot vollständig geladen ist"""
        self.ready = True
        print("🔄 Role Sync System ist bereit!")
        
        # Prüfe Server-Verbindungen
        for name, guild_id in self.SERVERS.items():
            guild = self.bot.get_guild(guild_id)
            if guild:
                print(f"✅ {name}: {guild.name} ({guild.member_count} Mitglieder)")
            else:
                print(f"❌ {name}: Server {guild_id} nicht gefunden!")
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Reagiert auf Rollenänderungen bei Mitgliedern"""
        # Warte bis Bot ready ist
        if not self.ready:
            return
        try:
            # Nur auf konfigurierten Servern reagieren
            if after.guild.id not in [self.SERVERS['LSPD'], self.SERVERS['SPECIAL_UNITS'], self.SERVERS['UNITS']]:
                return
            
            # Rollenänderungen ermitteln
            added_roles = set(after.roles) - set(before.roles)
            removed_roles = set(before.roles) - set(after.roles)
            
            action_id = f"{after.id}-{int(time.time())}"
            
            # Verhindere Endlosschleifen
            if action_id in self.processed_actions:
                return
            
            self.processed_actions.add(action_id)
            
            # Lösche nach 5 Sekunden aus dem Set
            await asyncio.sleep(0.1)  # Kurze Verzögerung
            asyncio.create_task(self._cleanup_action_id(action_id, 5))
            
            # Verarbeite hinzugefügte Rollen
            for role in added_roles:
                await self._handle_role_change(after, role.id, 'added')
            
            # Verarbeite entfernte Rollen
            for role in removed_roles:
                await self._handle_role_change(after, role.id, 'removed')
        
        except Exception as e:
            print(f'Fehler bei on_member_update: {e}')
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Reagiert wenn ein Member einem Server beitritt und prüft vorhandene Rollen"""
        # Warte bis Bot ready ist
        if not self.ready:
            return
        
        try:
            # Nur auf konfigurierten Servern reagieren
            if member.guild.id not in [self.SERVERS['LSPD'], self.SERVERS['SPECIAL_UNITS'], self.SERVERS['UNITS']]:
                return
            
            # Spezielle Sync-Prüfung für Ziel-Server
            if member.guild.id in [self.SERVERS['SPECIAL_UNITS'], self.SERVERS['UNITS']]:
                await self._check_and_repair_sync(member)
                return
            
            # Normale Rollen-Prüfung für LSPD Server
            print(f"👋 {member.display_name} ist {member.guild.name} beigetreten - prüfe Rollen...")
            
            # Kurze Verzögerung damit Discord die Rollen lädt
            await asyncio.sleep(2)
            
            # Aktualisiere Member-Daten
            try:
                member = await member.guild.fetch_member(member.id)
            except discord.NotFound:
                return
            
            # Prüfe alle vorhandenen Rollen des Members
            for role in member.roles:
                if role.id == member.guild.default_role.id:  # @everyone Rolle überspringen
                    continue
                
                # Verarbeite jede Rolle als "hinzugefügt"
                await self._handle_role_change(member, role.id, 'added')
                
                # Kleine Verzögerung zwischen Rollen
                await asyncio.sleep(0.5)
            
            print(f"✅ Rollen-Check für {member.display_name} abgeschlossen")
        
        except Exception as e:
            print(f'Fehler bei on_member_join: {e}')

    async def _check_and_repair_sync(self, member):
        """Prüft und repariert fehlende Rollen-Synchronisation bei Server-Beitritt"""
        await asyncio.sleep(3)  # Warte auf Discord-Daten
        print(f"🔍 Sync-Check für {member.display_name} auf {member.guild.name}")
        
        # Hole Source-Server Member
        source_guild = self.bot.get_guild(self.SERVERS['LSPD'])
        if not source_guild:
            print("❌ Source-Server nicht gefunden")
            return
            
        try:
            source_member = await source_guild.fetch_member(member.id)
            target_member = await member.guild.fetch_member(member.id)
        except discord.NotFound:
            print(f"❌ {member.display_name} nicht auf Source-Server gefunden")
            return
        
        # Bestimme welche Sync-Tabelle verwendet werden soll
        if member.guild.id == self.SERVERS['SPECIAL_UNITS']:
            sync_rules = self.SYNC_ROLES[self.SERVERS['LSPD']]
            server_type = "Special Units"
        elif member.guild.id == self.SERVERS['UNITS']:
            sync_rules = self.SYNC_ROLES_UNITS[self.SERVERS['LSPD']]
            server_type = "UNITS"
        else:
            print(f"❌ Unbekannter Ziel-Server: {member.guild.id}")
            return
        
        print(f"🔧 Prüfe {server_type} Sync-Regeln ({len(sync_rules)} Rollen)")
        
        # Prüfe jede Sync-Regel
        missing_roles = []
        extra_roles = []
        
        for source_role_id, target_role_id in sync_rules.items():
            source_role = source_guild.get_role(source_role_id)
            target_role = member.guild.get_role(target_role_id)
            
            if not source_role or not target_role:
                continue
                
            has_source_role = source_role in source_member.roles
            has_target_role = target_role in target_member.roles
            
            # Fehlende Synchronisation erkannt
            if has_source_role and not has_target_role:
                missing_roles.append((source_role, target_role))
                print(f"🔧 Fehlende Rolle: {source_role.name} → {target_role.name}")
                
            elif not has_source_role and has_target_role:
                extra_roles.append((source_role, target_role))
                print(f"🔧 Überflüssige Rolle: {target_role.name}")
        
        # Repariere fehlende Rollen
        for source_role, target_role in missing_roles:
            try:
                # Erstelle Action ID um Endlosschleifen zu vermeiden
                action_id = f"sync-repair-{member.id}-{target_role.id}-{int(time.time())}"
                self.processed_actions.add(action_id)
                
                await target_member.add_roles(target_role)
                print(f"✅ Rolle hinzugefügt: {target_role.name}")
                
                # Triggere auch Auto-Rollen (nur für Special Units Server)
                if member.guild.id == self.SERVERS['SPECIAL_UNITS'] and target_role.id in self.AUTO_ROLES.get(member.guild.id, {}):
                    for auto_role_id in self.AUTO_ROLES[member.guild.id][target_role.id]:
                        auto_role = member.guild.get_role(auto_role_id)
                        if auto_role and auto_role not in target_member.roles:
                            await target_member.add_roles(auto_role)
                            print(f"✅ Auto-Rolle hinzugefügt: {auto_role.name}")
                
                # Lösche nach 5 Sekunden
                asyncio.create_task(self._cleanup_action_id(action_id, 5))
                
            except Exception as e:
                print(f"❌ Fehler beim Hinzufügen von {target_role.name}: {e}")
        
        # Entferne überflüssige Rollen
        for source_role, target_role in extra_roles:
            try:
                # Erstelle Action ID um Endlosschleifen zu vermeiden
                action_id = f"sync-remove-{member.id}-{target_role.id}-{int(time.time())}"
                self.processed_actions.add(action_id)
                
                await target_member.remove_roles(target_role)
                print(f"🗑️ Rolle entfernt: {target_role.name}")
                
                # Entferne auch entsprechende Auto-Rollen (nur für Special Units Server)
                if member.guild.id == self.SERVERS['SPECIAL_UNITS'] and target_role.id in self.AUTO_ROLES.get(member.guild.id, {}):
                    for auto_role_id in self.AUTO_ROLES[member.guild.id][target_role.id]:
                        auto_role = member.guild.get_role(auto_role_id)
                        if auto_role and auto_role in target_member.roles:
                            await target_member.remove_roles(auto_role)
                            print(f"🗑️ Auto-Rolle entfernt: {auto_role.name}")
                
                # Lösche nach 5 Sekunden
                asyncio.create_task(self._cleanup_action_id(action_id, 5))
                
            except Exception as e:
                print(f"❌ Fehler beim Entfernen von {target_role.name}: {e}")
        
        # Zusammenfassung
        if missing_roles or extra_roles:
            print(f"🔧 Sync-Reparatur abgeschlossen für {member.display_name} auf {server_type}: {len(missing_roles)} hinzugefügt, {len(extra_roles)} entfernt")
            
            # Optional: Sende Benachrichtigung an User
            try:
                if missing_roles:
                    added_role_names = [role.name for _, role in missing_roles]
                    embed = discord.Embed(
                        title="🔧 Rollen-Synchronisation",
                        description=f"Deine Rollen wurden automatisch auf **{server_type}** synchronisiert.\n\n**Hinzugefügte Rollen:**\n{chr(10).join('• ' + name for name in added_role_names)}",
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="Automatische Synchronisation beim Server-Beitritt")
                    await member.send(embed=embed)
            except discord.Forbidden:
                pass  # DM fehlgeschlagen, nicht kritisch
                
        else:
            print(f"✅ Sync bereits korrekt für {member.display_name} auf {server_type}")
    
    async def _cleanup_action_id(self, action_id, delay):
        """Entfernt Action-ID nach Verzögerung"""
        await asyncio.sleep(delay)
        self.processed_actions.discard(action_id)
    
    async def _handle_role_change(self, member, role_id, action):
        """Verarbeitet Rollenänderungen"""
        guild_id = member.guild.id
        
        try:
            # 1. Zusätzliche Rollen verwalten (nur Special Units)
            if guild_id in self.AUTO_ROLES and role_id in self.AUTO_ROLES[guild_id]:
                await self._manage_additional_roles(member, role_id, action, guild_id)
            
            # 2. Server-übergreifende Synchronisation (nur von LSPD aus)
            if guild_id == self.SERVERS['LSPD']:
                # Prüfe Special Units Sync
                if role_id in self.SYNC_ROLES[guild_id]:
                    await self._sync_role_across_servers(member, role_id, action, guild_id)
                    print(f"🔄 Special Units Sync ausgelöst für Rolle {role_id}")
                
                # Prüfe UNITS Sync
                if role_id in self.SYNC_ROLES_UNITS[guild_id]:
                    await self._sync_role_across_servers(member, role_id, action, guild_id)
                    print(f"🔄 UNITS Sync ausgelöst für Rolle {role_id}")
            
            # 3. Decknamen-Abfrage für spezielle Rollen (nur bei hinzufügen)
            if action == 'added' and role_id in self.CODENAME_ROLES:
                await self._send_codename_request(member, role_id)
            
            # 4. Einladung für alle speziellen Rollen (nur bei hinzufügen)  
            if action == 'added' and role_id in self.ALL_INVITE_ROLES:
                await self._send_invitation(member, role_id)
        
        except Exception as e:
            print(f'Fehler beim Verarbeiten der Rolle {role_id}: {e}')
    
    async def _manage_additional_roles(self, member, main_role_id, action, guild_id):
        """Verwaltet zusätzliche Rollen"""
        additional_role_ids = self.AUTO_ROLES[guild_id][main_role_id]
        
        for additional_role_id in additional_role_ids:
            try:
                role = member.guild.get_role(additional_role_id)
                if not role:
                    print(f'Rolle {additional_role_id} nicht gefunden')
                    continue
                
                if action == 'added':
                    if role not in member.roles:
                        await member.add_roles(role)
                        print(f'✅ Zusatzrolle {role.name} zu {member.display_name} hinzugefügt')
                
                elif action == 'removed':
                    if role in member.roles:
                        await member.remove_roles(role)
                        print(f'❌ Zusatzrolle {role.name} von {member.display_name} entfernt')
            
            except Exception as e:
                print(f'Fehler bei Zusatzrolle {additional_role_id}: {e}')
    
    async def _sync_role_across_servers(self, member, role_id, action, source_guild_id):
        """Synchronisiert Rollen zwischen Servern (LSPD -> Special Units und LSPD -> UNITS)"""
        
        # Synchronisation nur vom LSPD Server
        if source_guild_id != self.SERVERS['LSPD']:
            return
        
        # Synchronisiere zu Special Units Server
        if role_id in self.SYNC_ROLES[source_guild_id]:
            target_role_id = self.SYNC_ROLES[source_guild_id][role_id]
            await self._sync_to_server(member, role_id, target_role_id, action, self.SERVERS['SPECIAL_UNITS'])
        
        # Synchronisiere zu UNITS Server
        if role_id in self.SYNC_ROLES_UNITS[source_guild_id]:
            target_role_id = self.SYNC_ROLES_UNITS[source_guild_id][role_id]
            await self._sync_to_server(member, role_id, target_role_id, action, self.SERVERS['UNITS'])

    async def _sync_to_server(self, member, source_role_id, target_role_id, action, target_guild_id):
        """Synchronisiert eine Rolle zu einem spezifischen Ziel-Server"""
        try:
            target_guild = self.bot.get_guild(target_guild_id)
            if not target_guild:
                print(f'❌ Zielserver {target_guild_id} nicht gefunden - Bot möglicherweise noch nicht ready')
                return
            
            target_member = target_guild.get_member(member.id)
            if not target_member:
                try:
                    target_member = await target_guild.fetch_member(member.id)
                except discord.NotFound:
                    print(f'User {member.display_name} ist nicht auf Server {target_guild.name}')
                    return
            
            target_role = target_guild.get_role(target_role_id)
            if not target_role:
                print(f'Zielrolle {target_role_id} nicht gefunden auf {target_guild.name}')
                return
            
            # Erstelle eine einzigartige Action-ID für den Zielserver
            sync_action_id = f"sync-{member.id}-{target_role_id}-{int(time.time())}"
            self.processed_actions.add(sync_action_id)
            
            if action == 'added':
                if target_role not in target_member.roles:
                    await target_member.add_roles(target_role)
                    print(f'🔄 Rolle {target_role.name} zu {member.display_name} auf {target_guild.name} synchronisiert (hinzugefügt)')
            
            elif action == 'removed':
                if target_role in target_member.roles:
                    await target_member.remove_roles(target_role)
                    print(f'🔄 Rolle {target_role.name} von {member.display_name} auf {target_guild.name} synchronisiert (entfernt)')
            
            # Lösche nach 3 Sekunden
            asyncio.create_task(self._cleanup_action_id(sync_action_id, 3))
        
        except Exception as e:
            print(f'Fehler bei Server-Synchronisation zu {target_guild_id}: {e}')
    
    async def _send_codename_request(self, member, role_id):
        """Sendet eine Decknamen-Abfrage an den User"""
        try:
            # Bestimme welche Rolle es war
            role = member.guild.get_role(role_id)
            role_name = role.name if role else "Unbekannte Rolle"
            
            # Erstelle Embed für die Decknamen-Abfrage
            embed = discord.Embed(
                title="🎭 Deckname erforderlich",
                description=f"Du hast die Rolle **{role_name}** erhalten und benötigst einen Decknamen.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="📝 Was du tun musst:",
                value="Bitte wende dich an einen Administrator oder nutze das entsprechende System, um deinen Decknamen zu registrieren.",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ Wichtig:",
                value="Dein Deckname wird für alle verdeckten Operationen verwendet.",
                inline=False
            )
            
            embed.set_footer(text=f"Server: {member.guild.name}")
            
            # Sende DM an den User
            try:
                await member.send(embed=embed)
                print(f"📬 Decknamen-Abfrage an {member.display_name} gesendet ({role_name})")
            
            except discord.Forbidden:
                print(f"❌ Konnte DM nicht an {member.display_name} senden (DMs deaktiviert)")
        
        except Exception as e:
            print(f'Fehler beim Senden der Decknamen-Abfrage: {e}')
    
    async def _send_invitation(self, member, role_id):
        """Sendet eine Einladung an den User"""
        try:
            # Bestimme welche Rolle es war
            role = member.guild.get_role(role_id)
            role_name = role.name if role else "Unbekannte Rolle"
            
            # Verschiedene Nachrichten je nach Rolle
            if role_id in self.CODENAME_ROLES:
                title = "🎖️ Willkommen im Team!"
                description = f"Du wurdest für die **{role_name}** Einheit ausgewählt."
                extra_info = "Da du eine verdeckte Rolle hast, wirst du separat kontaktiert für weitere Informationen."
            else:  # INVITE_ONLY_ROLES (ASD, SHP)
                title = "🚀 Einladung zur Spezialeinheit"  
                description = f"Du wurdest für die **{role_name}** Einheit eingeladen."
                extra_info = "Ein Administrator wird sich bald mit weiteren Details bei dir melden."
            
            # Erstelle Embed für die Einladung
            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📋 Nächste Schritte:",
                value=extra_info,
                inline=False
            )
            
            embed.add_field(
                name="📞 Support:",
                value="Bei Fragen wende dich an einen Administrator.",
                inline=False
            )
            
            embed.set_footer(text=f"Server: {member.guild.name}")
            
            # Sende DM an den User
            try:
                await member.send(embed=embed)
                print(f"📨 Einladung an {member.display_name} gesendet ({role_name})")
            
            except discord.Forbidden:
                print(f"❌ Konnte Einladung nicht an {member.display_name} senden (DMs deaktiviert)")
        
        except Exception as e:
            print(f'Fehler beim Senden der Einladung: {e}')
    
    @discord.app_commands.command(name="setcodename", description="Setzt oder ändert den Decknamen eines Users")
    @discord.app_commands.describe(
        user="Der User dessen Deckname geändert werden soll",
        codename="Der neue Deckname (2-20 Zeichen, nur Buchstaben, Zahlen, - und _)"
    )
    @discord.app_commands.default_permissions(administrator=True)
    async def set_codename(self, interaction: discord.Interaction, user: discord.Member, codename: str):
        """Admin-Command: Setzt oder ändert den Decknamen eines Users"""
        await interaction.response.defer(ephemeral=True)
        
        # Validierung des Decknamens
        if len(codename) < 2 or len(codename) > 20:
            await interaction.followup.send(
                "❌ **Ungültiger Deckname!**\nDer Deckname muss zwischen 2 und 20 Zeichen lang sein.", 
                ephemeral=True
            )
            return
        
        # Nur Alphanumerisch, Bindestrich und Unterstrich erlauben
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', codename):
            await interaction.followup.send(
                "❌ **Ungültiger Deckname!**\nNur Buchstaben, Zahlen, Bindestriche (-) und Unterstriche (_) sind erlaubt.", 
                ephemeral=True
            )
            return
        
        # Prüfe ob Deckname bereits verwendet wird
        for existing_user_id, data in self.codenames.items():
            if data["codename"].lower() == codename.lower() and existing_user_id != user.id:
                existing_user = self.bot.get_user(existing_user_id)
                existing_name = existing_user.display_name if existing_user else f"User {existing_user_id}"
                await interaction.followup.send(
                    f"❌ **Deckname bereits vergeben!**\nDer Deckname `{codename}` wird bereits von {existing_name} verwendet.", 
                    ephemeral=True
                )
                return
        
        # Prüfe ob User eine Deckname-Rolle hat
        user_has_codename_role = any(role.id in self.CODENAME_ROLES for role in user.roles)
        
        if not user_has_codename_role:
            # Warnung aber trotzdem erlauben
            embed = discord.Embed(
                title="⚠️ Warnung",
                description=f"{user.mention} hat keine Rolle, die normalerweise einen Decknamen benötigt.",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="Deckname trotzdem setzen?", 
                value="Der Deckname wird gesetzt, auch wenn keine entsprechende Rolle vorhanden ist.",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="✅ Deckname gesetzt",
                description=f"Deckname für {user.mention} wurde erfolgreich geändert.",
                color=discord.Color.green()
            )
        
        # Speichere alten Decknamen für Log
        old_codename = None
        if user.id in self.codenames:
            old_codename = self.codenames[user.id]["codename"]
        
        # Setze neuen Decknamen
        self.codenames[user.id] = {
            "codename": codename,
            "set_by": interaction.user.id,
            "timestamp": int(time.time()),
            "previous": old_codename
        }
        
        # Embed Details
        embed.add_field(
            name="👤 User",
            value=f"{user.mention} ({user.display_name})",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Neuer Deckname", 
            value=f"`{codename}`",
            inline=True
        )
        
        if old_codename:
            embed.add_field(
                name="📝 Alter Deckname",
                value=f"`{old_codename}`", 
                inline=True
            )
        
        embed.add_field(
            name="👨‍💼 Gesetzt von",
            value=interaction.user.mention,
            inline=True
        )
        
        embed.set_footer(text=f"User ID: {user.id}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Log für Konsole
        action = "geändert" if old_codename else "gesetzt"
        print(f"🎭 Deckname {action}: {user.display_name} -> '{codename}' (von {interaction.user.display_name})")
        
        # Benachrichtige den User per DM
        try:
            user_embed = discord.Embed(
                title="🎭 Deckname aktualisiert",
                description=f"Dein Deckname wurde von einem Administrator {'geändert' if old_codename else 'gesetzt'}.",
                color=discord.Color.blue()
            )
            
            user_embed.add_field(
                name="🎯 Neuer Deckname",
                value=f"`{codename}`",
                inline=True
            )
            
            if old_codename:
                user_embed.add_field(
                    name="📋 Vorheriger Deckname", 
                    value=f"`{old_codename}`",
                    inline=True
                )
            
            user_embed.add_field(
                name="👨‍💼 Geändert von",
                value=interaction.user.display_name,
                inline=True
            )
            
            user_embed.set_footer(text="Dieser Deckname wird für verdeckte Operationen verwendet.")
            
            await user.send(embed=user_embed)
            
        except discord.Forbidden:
            print(f"❌ Konnte Deckname-Bestätigung nicht an {user.display_name} senden (DMs deaktiviert)")
    
    @discord.app_commands.command(name="getcodename", description="Zeigt den aktuellen Decknamen eines Users")
    @discord.app_commands.describe(user="Der User dessen Deckname angezeigt werden soll")
    @discord.app_commands.default_permissions(administrator=True)
    async def get_codename(self, interaction: discord.Interaction, user: discord.Member):
        """Admin-Command: Zeigt den Decknamen eines Users"""
        await interaction.response.defer(ephemeral=True)
        
        if user.id not in self.codenames:
            embed = discord.Embed(
                title="❌ Kein Deckname gefunden",
                description=f"{user.mention} hat keinen Decknamen gesetzt.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="💡 Tipp",
                value="Verwende `/setcodename` um einen Decknamen zu setzen.",
                inline=False
            )
        else:
            data = self.codenames[user.id]
            set_by_user = self.bot.get_user(data["set_by"])
            set_by_name = set_by_user.display_name if set_by_user else f"User {data['set_by']}"
            
            embed = discord.Embed(
                title="🎭 Deckname Information",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="👤 User",
                value=f"{user.mention} ({user.display_name})",
                inline=False
            )
            
            embed.add_field(
                name="🎭 Aktueller Deckname",
                value=f"`{data['codename']}`",
                inline=True
            )
            
            embed.add_field(
                name="👨‍💼 Gesetzt von",
                value=set_by_name,
                inline=True
            )
            
            embed.add_field(
                name="📅 Zeitpunkt",
                value=f"<t:{data['timestamp']}:F>",
                inline=True
            )
            
            if "previous" in data and data["previous"]:
                embed.add_field(
                    name="📝 Vorheriger Deckname",
                    value=f"`{data['previous']}`",
                    inline=True
                )
        
        embed.set_footer(text=f"User ID: {user.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="listcodenames", description="Zeigt alle gesetzten Decknamen")
    @discord.app_commands.default_permissions(administrator=True)
    async def list_codenames(self, interaction: discord.Interaction):
        """Admin-Command: Zeigt alle Decknamen"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.codenames:
            embed = discord.Embed(
                title="📭 Keine Decknamen",
                description="Es sind derzeit keine Decknamen gesetzt.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎭 Alle Decknamen",
            description=f"Insgesamt {len(self.codenames)} Decknamen gesetzt:",
            color=discord.Color.blue()
        )
        
        # Sortiere nach Deckname
        sorted_codenames = sorted(self.codenames.items(), key=lambda x: x[1]["codename"].lower())
        
        # Zeige max 20 Einträge (Discord Embed Limit)
        for i, (user_id, data) in enumerate(sorted_codenames[:20]):
            user = self.bot.get_user(user_id)
            user_name = user.display_name if user else f"User {user_id}"
            
            embed.add_field(
                name=f"`{data['codename']}`",
                value=f"{user_name}\n<t:{data['timestamp']}:R>",
                inline=True
            )
        
        if len(self.codenames) > 20:
            embed.set_footer(text=f"... und {len(self.codenames) - 20} weitere")
        else:
            embed.set_footer(text=f"Alle {len(self.codenames)} Decknamen angezeigt")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="deletecodename", description="Löscht den Decknamen eines Users")
    @discord.app_commands.describe(user="Der User dessen Deckname gelöscht werden soll")
    @discord.app_commands.default_permissions(administrator=True)
    async def delete_codename(self, interaction: discord.Interaction, user: discord.Member):
        """Admin-Command: Löscht den Decknamen eines Users"""
        await interaction.response.defer(ephemeral=True)
        
        if user.id not in self.codenames:
            embed = discord.Embed(
                title="❌ Kein Deckname gefunden",
                description=f"{user.mention} hat keinen Decknamen gesetzt.",
                color=discord.Color.red()
            )
        else:
            deleted_codename = self.codenames[user.id]["codename"]
            del self.codenames[user.id]
            
            embed = discord.Embed(
                title="🗑️ Deckname gelöscht",
                description=f"Deckname für {user.mention} wurde erfolgreich gelöscht.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🎭 Gelöschter Deckname",
                value=f"`{deleted_codename}`",
                inline=True
            )
            
            embed.add_field(
                name="👨‍💼 Gelöscht von",
                value=interaction.user.mention,
                inline=True
            )
            
            print(f"🗑️ Deckname gelöscht: {user.display_name} ('{deleted_codename}') von {interaction.user.display_name}")
            
            # Benachrichtige User
            try:
                user_embed = discord.Embed(
                    title="🗑️ Deckname entfernt",
                    description=f"Dein Deckname `{deleted_codename}` wurde von einem Administrator entfernt.",
                    color=discord.Color.orange()
                )
                user_embed.add_field(
                    name="👨‍💼 Entfernt von",
                    value=interaction.user.display_name,
                    inline=True
                )
                await user.send(embed=user_embed)
            except discord.Forbidden:
                pass
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="roleinfo", description="Zeigt Informationen über die Rollen-Konfiguration")
    @discord.app_commands.default_permissions(administrator=True)
    async def role_info(self, interaction: discord.Interaction):
        """Zeigt Informationen über die Rollen-Konfiguration"""
        embed = discord.Embed(
            title="🤖 Role Sync System",
            description="Konfiguration der automatischen Rollen-Synchronisation",
            color=discord.Color.blue()
        )
        
        # Server Info
        lspd_guild = self.bot.get_guild(self.SERVERS['LSPD'])
        su_guild = self.bot.get_guild(self.SERVERS['SPECIAL_UNITS'])
        units_guild = self.bot.get_guild(self.SERVERS['UNITS'])
        
        server_info = f"**LSPD Server:** {lspd_guild.name if lspd_guild else 'Nicht gefunden'}\n"
        server_info += f"**Special Units:** {su_guild.name if su_guild else 'Nicht gefunden'}\n"
        server_info += f"**UNITS:** {units_guild.name if units_guild else 'Nicht gefunden'}"
        embed.add_field(name="📊 Server", value=server_info, inline=False)
        
        # Sync Rules
        sync_count_su = len(self.SYNC_ROLES.get(self.SERVERS['LSPD'], {}))
        sync_count_units = len(self.SYNC_ROLES_UNITS.get(self.SERVERS['LSPD'], {}))
        embed.add_field(name="🔄 Synchronisierte Rollen", value=f"Special Units: {sync_count_su}\nUNITS: {sync_count_units}", inline=True)
        
        # Auto Rules
        auto_count_su = len(self.AUTO_ROLES.get(self.SERVERS['SPECIAL_UNITS'], {}))
        embed.add_field(name="⚡ Auto-Rollen", value=f"Special Units: {auto_count_su}\nUNITS: 0", inline=True)
        
        embed.add_field(name="📋 Richtung", value="LSPD → Special Units\nLSPD → UNITS\n(Einseitig)", inline=True)
        
        # Deckname Stats
        embed.add_field(name="🎭 Decknamen", value=f"{len(self.codenames)} gesetzt", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="reloadsync", description="Lädt das Role Sync System neu")
    @discord.app_commands.default_permissions(administrator=True)
    async def reload_sync(self, interaction: discord.Interaction):
        """Lädt das Role Sync System neu"""
        self.processed_actions.clear()
        # Decknamen werden NICHT gecleared, um Datenverlust zu vermeiden
        await interaction.response.send_message("✅ Role Sync System wurde neugeladen! (Decknamen bleiben erhalten)")

async def setup(bot):
    await bot.add_cog(RoleSyncCog(bot))
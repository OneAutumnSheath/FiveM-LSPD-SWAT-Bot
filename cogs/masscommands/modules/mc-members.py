import discord
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MyBot
    from services.permission_service import PermissionService

# --- Modul-Konfiguration & Konstanten ---
COMMAND_NAME = "member"
FRIENDLY_NAME = "Mitgliederverwaltung"
SYNTAX = """
member add <dn> "<name>" <rang_key> <user_id>
member remove <dn>
member setunit <dn_oder_id> <unit_role_id> <status>
member changerank <dn> <neuer_rang_key>
member changedn <alte_dn> <neue_dn>

Rang-Keys (1-17):
1=Rekrut, 2=Gefreiter, 3=Obergefreiter, 4=Hauptgefreiter, 5=Stabsgefreiter,
6=Unteroffizier, 7=Stabsunteroffizier, 8=Feldwebel, 9=Oberfeldwebel,
10=Hauptfeldwebel, 11=Stabsfeldwebel, 12=Leutnant, 13=Oberleutnant,
14=Hauptmann, 15=Major, 16=Oberstleutnant, 17=Oberst
"""

class MC_MemberModule:
    def __init__(self, bot: "MyBot"):
        self.bot = bot
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
        pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                if fetch == "one": 
                    result = await cursor.fetchone()
                    return dict(zip([desc[0] for desc in cursor.description], result)) if result else None
                if fetch == "all": 
                    results = await cursor.fetchall()
                    return [dict(zip([desc[0] for desc in cursor.description], row)) for row in results]

    async def _resolve_user(self, guild: discord.Guild, identifier: str) -> discord.Member | None:
        """Findet ein Mitglied auf dem Server anhand von DN oder ID."""
        user_id = None
        if identifier.isdigit() and len(identifier) > 15:
            # Es ist wahrscheinlich eine Discord-ID
            user_id = int(identifier)
        else:
            # Es könnte eine DN sein, versuche Discord-ID aus DB zu holen
            details = await self._execute_query(
                "SELECT discord_id FROM members WHERE dn = %s", 
                (identifier,), 
                fetch="one"
            )
            if details:
                user_id = details.get('discord_id')
        
        if user_id:
            try:
                return await guild.fetch_member(user_id)
            except discord.NotFound:
                return None
        return None

    def _resolve_role(self, guild: discord.Guild, identifier: str) -> discord.Role | None:
        """Findet eine Rolle anhand einer Rang-ID oder Rollen-ID."""
        if identifier.isdigit():
            # Prüfe zuerst ob es eine Rang-ID ist (1-17)
            rank_key = int(identifier)
            if role_id_from_rank := self.RANK_MAPPING.get(rank_key):
                return guild.get_role(role_id_from_rank)
            # Sonst direkte Rollen-ID
            return guild.get_role(int(identifier))
        # Name-basierte Suche
        return discord.utils.get(guild.roles, name=identifier)

    def _resolve_unit_role(self, guild: discord.Guild, identifier: str) -> discord.Role | None:
        """Findet eine Unit-Rolle anhand der ID."""
        if identifier.isdigit():
            return guild.get_role(int(identifier))
        return discord.utils.get(guild.roles, name=identifier)

    async def _check_dn_exists(self, dn: int) -> bool:
        """Prüft ob eine DN bereits existiert."""
        result = await self._execute_query("SELECT dn FROM members WHERE dn = %s", (dn,), fetch="one")
        return result is not None

    async def handle(self, interaction: discord.Interaction, tokens: list[str],
                     line: str, line_no: int, errors: list, successes: list):

        if len(tokens) < 3:
            return errors.append((line_no, line, "Zu wenige Argumente für 'member'."))

        sub_cmd = tokens[1].lower()
        
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not permission_service or not permission_service.has_permission(interaction.user, f"mitglieder.{sub_cmd}"):
            return errors.append((line_no, line, f"Keine Berechtigung für 'mitglieder.{sub_cmd}'."))

        try:
            if sub_cmd == "add":
                if len(tokens) < 6: 
                    raise ValueError("Format: add <dn> \"<name>\" <rang_key> <user_id>")
                
                dn_str, name, rank_key_str, user_id_str = tokens[2], tokens[3], tokens[4], tokens[5]
                
                # Validierung der DN
                if not dn_str.isdigit():
                    raise ValueError("DN muss eine Zahl sein.")
                dn = int(dn_str)
                
                # Prüfe ob DN bereits existiert
                if await self._check_dn_exists(dn):
                    raise ValueError(f"Die Dienstnummer `{dn}` ist bereits vergeben.")
                
                # User finden
                user = await self._resolve_user(interaction.guild, user_id_str)
                if not user:
                    raise ValueError(f"User mit ID '{user_id_str}' nicht gefunden.")
                
                # Rang-Rolle über Rang-Key finden
                rank_role = self._resolve_role(interaction.guild, rank_key_str)
                if not rank_role:
                    raise ValueError(f"Rang-Key '{rank_key_str}' nicht gefunden. Verwenden Sie 1-17.")
                
                # Rang-ID für DB ermitteln
                rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(rank_role.id)
                if not rank_id:
                    raise ValueError(f"Die Rolle {rank_role.mention} ist kein gültiger Rang.")
                
                # In Datenbank einfügen
                await self._execute_query(
                    "INSERT INTO members (dn, name, rank, hired_at, discord_id) VALUES (%s, %s, %s, NOW(), %s)",
                    (dn, name, rank_id, user.id)
                )
                await self._execute_query("INSERT INTO units (dn) VALUES (%s)", (dn,))
                
                # Discord-Rollen setzen
                try:
                    all_rank_roles = [interaction.guild.get_role(r_id) for r_id in self.RANK_MAPPING.values()]
                    await user.remove_roles(*[r for r in all_rank_roles if r and r in user.roles], reason="Neuer Rang bei add_member")
                    await user.add_roles(rank_role, reason="Rang bei add_member gesetzt")
                except discord.HTTPException as e:
                    successes.append((line_no, f"Mitglied {user.mention} hinzugefügt, aber Rollen konnten nicht gesetzt werden: {e}"))
                    return

            elif sub_cmd == "remove":
                if len(tokens) < 3: 
                    raise ValueError("Format: remove <dn>")
                
                dn_str = tokens[2]
                if not dn_str.isdigit():
                    raise ValueError("DN muss eine Zahl sein.")
                dn = int(dn_str)
                
                # Prüfe ob DN existiert
                if not await self._check_dn_exists(dn):
                    raise ValueError(f"Die Dienstnummer `{dn}` wurde nicht gefunden.")
                
                # Aus Datenbank entfernen
                async with self.bot.db_pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                        await cursor.execute("DELETE FROM units WHERE dn = %s", (dn,))
                        await cursor.execute("DELETE FROM members WHERE dn = %s", (dn,))
                        await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

            elif sub_cmd == "setunit":
                if len(tokens) < 5: 
                    raise ValueError("Format: setunit <dn_oder_id> <unit_role_id> <status>")
                
                user_identifier, unit_role_id_str, status_str = tokens[2], tokens[3], tokens[4]
                
                # User finden
                user = await self._resolve_user(interaction.guild, user_identifier)
                if not user:
                    raise ValueError(f"User mit Kennung '{user_identifier}' nicht gefunden.")
                
                # DN des Users ermitteln
                user_data = await self._execute_query("SELECT dn FROM members WHERE discord_id = %s", (user.id,), fetch="one")
                if not user_data:
                    raise ValueError(f"{user.mention} ist nicht in der Datenbank registriert.")
                dn = user_data['dn']
                
                # Unit-Rolle finden
                unit_role = self._resolve_unit_role(interaction.guild, unit_role_id_str)
                if not unit_role:
                    raise ValueError(f"Unit-Rolle '{unit_role_id_str}' nicht gefunden.")
                
                # Unit-Name ermitteln
                unit_name = self.UNIT_MAPPING.get(unit_role.id)
                if not unit_name:
                    raise ValueError(f"{unit_role.mention} ist keine gültige Unit-Rolle.")
                
                # Status parsen
                status_lower = status_str.lower()
                if status_lower in ["true", "1", "aktiv", "active"]:
                    status = True
                elif status_lower in ["false", "0", "inaktiv", "inactive"]:
                    status = False
                else:
                    raise ValueError("Status muss 'true/false', '1/0' oder 'aktiv/inaktiv' sein.")
                
                # Datenbank aktualisieren
                await self._execute_query(f"UPDATE units SET `{unit_name}` = %s WHERE dn = %s", (status, dn))
                
                # Discord-Rolle setzen
                try:
                    if status:
                        await user.add_roles(unit_role, reason=f"Unit-Status gesetzt: {unit_role.name}")
                    else:
                        await user.remove_roles(unit_role, reason=f"Unit-Status entfernt: {unit_role.name}")
                except discord.HTTPException as e:
                    successes.append((line_no, f"DB-Update erfolgreich, aber Rolle konnte nicht geändert werden: {e}"))
                    return

            elif sub_cmd == "changerank":
                if len(tokens) < 4: 
                    raise ValueError("Format: changerank <dn> <neuer_rang_key>")
                
                dn_str, new_rank_key_str = tokens[2], tokens[3]
                
                if not dn_str.isdigit():
                    raise ValueError("DN muss eine Zahl sein.")
                dn = int(dn_str)
                
                # Prüfe ob DN existiert
                if not await self._check_dn_exists(dn):
                    raise ValueError(f"Die Dienstnummer `{dn}` wurde nicht gefunden.")
                
                # Neue Rang-Rolle über Rang-Key finden
                new_rank_role = self._resolve_role(interaction.guild, new_rank_key_str)
                if not new_rank_role:
                    raise ValueError(f"Rang-Key '{new_rank_key_str}' nicht gefunden. Verwenden Sie 1-17.")
                
                # Rang-ID für DB ermitteln
                new_rank_id = self.ROLE_TO_RANK_ID_MAPPING.get(new_rank_role.id)
                if not new_rank_id:
                    raise ValueError(f"{new_rank_role.mention} ist kein gültiger Rang.")
                
                # Datenbank aktualisieren
                await self._execute_query("UPDATE members SET rank = %s WHERE dn = %s", (new_rank_id, dn))

            elif sub_cmd == "changedn":
                if len(tokens) < 4: 
                    raise ValueError("Format: changedn <alte_dn> <neue_dn>")
                
                current_dn_str, new_dn_str = tokens[2], tokens[3]
                
                if not current_dn_str.isdigit() or not new_dn_str.isdigit():
                    raise ValueError("Beide DNs müssen Zahlen sein.")
                
                current_dn, new_dn = int(current_dn_str), int(new_dn_str)
                
                # Prüfe ob aktuelle DN existiert
                if not await self._check_dn_exists(current_dn):
                    raise ValueError(f"Die aktuelle DN `{current_dn}` wurde nicht gefunden.")
                
                # Prüfe ob neue DN bereits vergeben ist
                if await self._check_dn_exists(new_dn):
                    raise ValueError(f"Die neue DN `{new_dn}` ist bereits vergeben.")
                
                # Datenbank aktualisieren
                async with self.bot.db_pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                        await cursor.execute("UPDATE members SET dn = %s WHERE dn = %s", (new_dn, current_dn))
                        await cursor.execute("UPDATE units SET dn = %s WHERE dn = %s", (new_dn, current_dn))
                        await cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

            else:
                raise ValueError(f"Unbekanntes Member-Subkommando: '{sub_cmd}'")

            # Erfolg melden
            successes.append((line_no, f"Aktion '{sub_cmd}' erfolgreich ausgeführt."))

        except (ValueError, IndexError) as e:
            errors.append((line_no, line, f"Formatfehler oder ungültiger Wert: {e}"))
        except Exception as e:
            errors.append((line_no, line, f"Allgemeiner Fehler: {e}"))
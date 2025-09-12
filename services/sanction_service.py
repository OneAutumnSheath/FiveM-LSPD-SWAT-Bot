# bot/services/sanction_service.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import aiomysql
import yaml
import re
from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from main import MyBot
    from services.display_service import DisplayService

class SanctionService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "SanctionService"
        self.config = self._load_config()

    async def cog_load(self):
        await self._ensure_table_exists()
        await self._ensure_sanctions_table_exists()  # Neue Tabelle für Sanktionen
        self.verwarnung_cleanup_task.start()

    def cog_unload(self):
        self.verwarnung_cleanup_task.cancel()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/sanctions_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/sanctions_config.yaml nicht gefunden.")
            return {}

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": 
                    result = await cursor.fetchone()
                elif fetch == "all": 
                    result = await cursor.fetchall()
                else: 
                    result = None
                await conn.commit()
                return result

    async def _ensure_table_exists(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS verwarnungen (
                id INT AUTO_INCREMENT PRIMARY KEY, 
                user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL, 
                granted_at DATETIME NOT NULL, 
                KEY user_id_idx (user_id)
            );
        """)

    async def _ensure_sanctions_table_exists(self):
        """Erstellt die Tabelle für Sanktionen falls sie nicht existiert."""
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS sanktionen (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                user_name VARCHAR(255) NOT NULL,
                deckname VARCHAR(255) DEFAULT NULL,
                strafe TEXT NOT NULL,
                grund TEXT NOT NULL,
                zahlungsdatum VARCHAR(50) NOT NULL,
                erstellt_von_id BIGINT NOT NULL,
                erstellt_von_name VARCHAR(255) NOT NULL,
                erstellt_am DATETIME NOT NULL,
                erledigt BOOLEAN DEFAULT FALSE,
                erledigt_am DATETIME DEFAULT NULL,
                erledigt_von_id BIGINT DEFAULT NULL,
                erledigt_von_name VARCHAR(255) DEFAULT NULL,
                KEY user_id_idx (user_id),
                KEY erledigt_idx (erledigt),
                KEY erstellt_am_idx (erstellt_am)
            );
        """)

    async def count_warnings_from_db(self, user_id: int) -> int:
        """Zählt aktive Verwarnungen für einen User aus der Datenbank."""
        result = await self._execute_query(
            "SELECT COUNT(*) as count FROM verwarnungen WHERE user_id = %s", 
            (user_id,), 
            fetch="one"
        )
        return result['count'] if result else 0

    async def save_sanction_to_db(self, user: discord.Member, strafe: str, grund: str, 
                                 zahlungsdatum: str, erstellt_von: discord.Member, deckname: str = None):
        """Speichert eine neue Sanktion in der Datenbank."""
        await self._execute_query("""
            INSERT INTO sanktionen (
                user_id, user_name, deckname, strafe, grund, zahlungsdatum,
                erstellt_von_id, erstellt_von_name, erstellt_am
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user.id, user.display_name, deckname, strafe, grund, zahlungsdatum,
            erstellt_von.id, erstellt_von.display_name, datetime.now(timezone.utc)
        ))

    async def get_open_sanctions(self, user_id: int = None) -> List[Dict]:
        """Holt alle offenen Sanktionen oder nur die eines bestimmten Users."""
        if user_id:
            query = "SELECT * FROM sanktionen WHERE user_id = %s AND erledigt = FALSE ORDER BY erstellt_am DESC"
            args = (user_id,)
        else:
            query = "SELECT * FROM sanktionen WHERE erledigt = FALSE ORDER BY erstellt_am DESC"
            args = None
        
        result = await self._execute_query(query, args, fetch="all")
        return result if result else []

    async def get_sanction_by_id(self, sanction_id: int) -> Dict:
        """Holt eine Sanktion anhand ihrer ID."""
        result = await self._execute_query(
            "SELECT * FROM sanktionen WHERE id = %s", 
            (sanction_id,), 
            fetch="one"
        )
        return result

    async def mark_sanction_as_completed(self, sanction_id: int, completed_by: discord.Member) -> bool:
        """Markiert eine Sanktion als erledigt."""
        # Prüfe ob Sanktion existiert und noch offen ist
        sanction = await self.get_sanction_by_id(sanction_id)
        if not sanction or sanction['erledigt']:
            return False

        await self._execute_query("""
            UPDATE sanktionen 
            SET erledigt = TRUE, erledigt_am = %s, erledigt_von_id = %s, erledigt_von_name = %s 
            WHERE id = %s
        """, (
            datetime.now(timezone.utc), 
            completed_by.id, 
            completed_by.display_name, 
            sanction_id
        ))
        return True

    async def get_all_sanctions(self, user_id: int = None, limit: int = 50) -> List[Dict]:
        """Holt alle Sanktionen (erledigt und offen) mit optionalem User-Filter."""
        if user_id:
            query = "SELECT * FROM sanktionen WHERE user_id = %s ORDER BY erstellt_am DESC LIMIT %s"
            args = (user_id, limit)
        else:
            query = "SELECT * FROM sanktionen ORDER BY erstellt_am DESC LIMIT %s"
            args = (limit,)
        
        result = await self._execute_query(query, args, fetch="all")
        return result if result else []

    async def extract_and_process_warnings(self, member: discord.Member, strafe: str) -> int:
        """
        Extrahiert Verwarnungen aus der Strafe und verarbeitet sie.
        Gibt die Anzahl der neuen Verwarnungen zurück.
        """
        # Verwarnungen aus der Strafe extrahieren
        verwarnung_patterns = [
            r"(\d+)\s*\.?\s*verwarnung",
            r"verwarnung",
            r"(\d+)\s*verwarn",
            r"verwarn"
        ]
        
        neue_verwarnungen = 0
        strafe_lower = strafe.lower()
        
        # Prüfe auf explizite Anzahl (z.B. "1. Verwarnung", "2 Verwarnungen")
        for pattern in verwarnung_patterns[:2]:  # Nur die ersten beiden mit Zahlen
            matches = re.findall(pattern, strafe_lower, re.IGNORECASE)
            if matches:
                neue_verwarnungen = sum(int(m) for m in matches if m.isdigit())
                break
        
        # Wenn keine Zahl gefunden, aber "Verwarnung" im Text, dann 1 Verwarnung
        if neue_verwarnungen == 0:
            for pattern in verwarnung_patterns[2:]:  # Die ohne Zahlen
                if re.search(pattern, strafe_lower, re.IGNORECASE):
                    neue_verwarnungen = 1
                    break

        # Verwarnungen verarbeiten falls welche gefunden
        if neue_verwarnungen > 0:
            await self._process_warnings(member, neue_verwarnungen)
        
        return neue_verwarnungen

    async def _process_warnings(self, member: discord.Member, neue_verwarnungen: int):
        """Verarbeitet neue Verwarnungen für ein Mitglied."""
        aktuelle_verwarnungen = await self.count_warnings_from_db(member.id)
        gesamt = aktuelle_verwarnungen + neue_verwarnungen
        
        print(f"🔄 Verarbeite {neue_verwarnungen} neue Verwarnungen für {member.display_name}")
        print(f"   Vorher: {aktuelle_verwarnungen}, Nachher: {gesamt}")
        
        # Rollen basierend auf Verwarnungsanzahl zuweisen
        rollen_config = [
            (1, self.config.get('verwarnung_1_role_id')),
            (2, self.config.get('verwarnung_2_role_id'))
        ]
        
        for stufe, rollen_id in rollen_config:
            if gesamt >= stufe and rollen_id:
                rolle = member.guild.get_role(rollen_id)
                if rolle and rolle not in member.roles:
                    try:
                        await member.add_roles(rolle, reason=f"Sanktion: {gesamt} Verwarnungen erreicht")
                        await self._execute_query(
                            "INSERT INTO verwarnungen (user_id, role_id, granted_at) VALUES (%s, %s, %s)", 
                            (member.id, rolle.id, datetime.now(timezone.utc))
                        )
                        print(f"✅ Rolle {rolle.name} für {member.display_name} hinzugefügt")
                    except Exception as e:
                        print(f"❌ Fehler beim Hinzufügen der Rolle {rolle.name}: {e}")

        # Eskalation bei 3+ Verwarnungen
        if gesamt >= 3:
            await self._handle_escalation(member, gesamt)

    async def _handle_escalation(self, member: discord.Member, gesamt_verwarnungen: int):
        """Behandelt Eskalation bei 3+ Verwarnungen."""
        # Eskalation nur loggen, keine Channel-Benachrichtigung mehr
        print(f"⚠️ ESKALATION: {member.display_name} hat {gesamt_verwarnungen} Verwarnungen erreicht!")

    @tasks.loop(hours=1)
    async def verwarnung_cleanup_task(self):
        """Entfernt abgelaufene Verwarnungen (nach 7 Tagen)."""
        guild = self.bot.get_guild(self.config.get('guild_id'))
        if not guild: 
            return

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        abgelaufene = await self._execute_query(
            "SELECT * FROM verwarnungen WHERE granted_at < %s", 
            (seven_days_ago,), 
            fetch="all"
        )
        
        if not abgelaufene: 
            return

        print(f"🧹 Bereinige {len(abgelaufene)} abgelaufene Verwarnungen (nach 7 Tagen)...")
        
        ids_to_delete = [eintrag["id"] for eintrag in abgelaufene]
        
        for eintrag in abgelaufene:
            try:
                member = await guild.fetch_member(eintrag["user_id"])
                rolle = guild.get_role(eintrag["role_id"])
                if member and rolle and rolle in member.roles:
                    await member.remove_roles(rolle, reason="Verwarnung abgelaufen (7 Tage)")
                    print(f"✅ Verwarnung-Rolle {rolle.name} von {member.display_name} entfernt (nach 7 Tagen)")
            except discord.NotFound:
                print(f"⚠️ Mitglied {eintrag['user_id']} nicht mehr auf dem Server")
                continue
            except Exception as e:
                print(f"❌ Fehler beim Entfernen abgelaufener Verwarnungs-Rolle: {e}")

        # Datenbankeinträge löschen
        if ids_to_delete:
            format_strings = ','.join(['%s'] * len(ids_to_delete))
            await self._execute_query(
                f"DELETE FROM verwarnungen WHERE id IN ({format_strings})", 
                tuple(ids_to_delete)
            )
            print(f"🗑️ {len(ids_to_delete)} abgelaufene Verwarnungseinträge aus DB gelöscht (nach 7 Tagen)")

    @verwarnung_cleanup_task.before_loop
    async def before_cleanup_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: "MyBot"):
    await bot.add_cog(SanctionService(bot))
import discord
from discord.ext import commands
import aiomysql  # Wichtig: Diese Bibliothek wird für die Datenbankverbindung benötigt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# Importiere die Konfiguration aus der separaten Datei
from config.role_sync_mapping import ROLE_SYNC_MAPPING

class RoleSyncService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "RoleSyncService"

    async def _get_deckname(self, user_id: int) -> str | None:
        """Holt den Decknamen eines Users aus der Datenbank `usarmy.seal_decknamen`."""
        # Stellt sicher, dass ein DB-Pool im Bot existiert
        if not hasattr(self.bot, 'db_pool'):
            return None
            
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT deckname FROM usarmy.seals_decknamen WHERE user_id = %s", 
                    (user_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else None

    async def sync_roles_for_member(self, member: discord.Member):
            """
            Synchronisiert die Rollen UND den Nicknamen für ein Mitglied basierend auf der Konfiguration.
            Diese Version stellt den korrekten SOLL-Zustand her.
            """
            source_guild = member.guild
            if source_guild.id not in ROLE_SYNC_MAPPING:
                return

            config = ROLE_SYNC_MAPPING[source_guild.id]
            target_guild = self.bot.get_guild(config["target_guild_id"])
            role_map = config["roles"]

            if not target_guild:
                return

            try:
                target_member = await target_guild.fetch_member(member.id)
            except discord.NotFound:
                return

            # Zuerst den Nicknamen synchronisieren
            deckname = await self._get_deckname(member.id)
            if deckname:
                new_nick = f"[SEAL] {deckname}"
                if target_member.nick != new_nick:
                    try:
                        await target_member.edit(nick=new_nick, reason="Automatischer Sync des Decknamens")
                    except discord.Forbidden:
                        print(f"[RoleSync] Fehler: Keine Berechtigung, den Nickname auf '{target_guild.name}' zu ändern.")

            # --- START: KORRIGIERTE LOGIK FÜR ROLLEN-SYNC ---

            # 1. Bestimme den SOLL-Zustand: Welche Rollen sollte der User auf dem Ziel-Server haben?
            soll_rollen_ids = set()
            for source_id, target_id in role_map.items():
                # Wenn der User die Quell-Rolle hat...
                if any(role.id == source_id for role in member.roles):
                    # ...sollte er auch die Ziel-Rolle haben.
                    soll_rollen_ids.add(target_id)

            # 2. Bestimme den IST-Zustand: Welche synchronisierten Rollen hat der User bereits?
            #    Wir betrachten nur die Rollen, die auch im Mapping vorkommen.
            ist_rollen_ids = {role.id for role in target_member.roles if role.id in role_map.values()}

            # 3. Berechne die Differenz und führe die Aktionen aus
            ids_to_add = soll_rollen_ids - ist_rollen_ids
            ids_to_remove = ist_rollen_ids - soll_rollen_ids

            # Führe die Aktionen aus
            try:
                if ids_to_add:
                    roles_to_add = [target_guild.get_role(rid) for rid in ids_to_add if target_guild.get_role(rid)]
                    await target_member.add_roles(*roles_to_add, reason=f"Sync von Server {source_guild.id}")
                    print(f"[RoleSync] Rollen hinzugefügt für {target_member.display_name}: {[r.name for r in roles_to_add]}")

                if ids_to_remove:
                    roles_to_remove = [target_guild.get_role(rid) for rid in ids_to_remove if target_guild.get_role(rid)]
                    await target_member.remove_roles(*roles_to_remove, reason=f"Sync von Server {source_guild.id}")
                    print(f"[RoleSync] Rollen entfernt für {target_member.display_name}: {[r.name for r in roles_to_remove]}")

            except discord.Forbidden:
                print(f"[RoleSync] Fehler: Keine Berechtigung, Rollen auf '{target_guild.name}' zu verwalten.")
            
            # --- ENDE: KORRIGIERTE LOGIK FÜR ROLLEN-SYNC ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        await self.sync_roles_for_member(after)


async def setup(bot: "MyBot"):
    await bot.add_cog(RoleSyncService(bot))
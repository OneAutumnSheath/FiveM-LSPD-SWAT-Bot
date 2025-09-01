import discord
from discord.ext import commands
import json
import os
import aiomysql
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MyBot
    from services.role_sync_service import RoleSyncService
    from commands.checkDepartments import CheckDepartments

# --- Konfiguration ---
PENDING_ENTRIES_FILE = "./data/su_server_invites.json"
HAUPT_SERVER_ID = 1097625621875675188 # Wichtig für den Abgleich

class InvitationService(commands.Cog):
    """
    Dieser Cog dient als zentraler Service, um einen User zum SU-Server einzuladen
    und den Synchronisationsprozess anzustoßen.
    """
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "InvitationService"
        self.pending_entries = self._load_entries()

    def _load_entries(self):
        """Lädt die Liste der offenen Eintritte aus der JSON-Datei."""
        if os.path.exists(PENDING_ENTRIES_FILE):
            try:
                with open(PENDING_ENTRIES_FILE, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {} # Falls die Datei leer oder korrupt ist
        return {}

    def _save_entries(self):
        """Speichert die aktuelle Liste der Eintritte in die JSON-Datei."""
        os.makedirs(os.path.dirname(PENDING_ENTRIES_FILE), exist_ok=True)
        with open(PENDING_ENTRIES_FILE, "w") as f:
            json.dump(self.pending_entries, f, indent=4)
            
    async def _get_deckname(self, user_id: int) -> str | None:
        """Holt den Decknamen eines Users aus der Datenbank."""
        if not hasattr(self.bot, 'db_pool'):
            return None
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT deckname FROM usarmy.seal_decknamen WHERE user_id = %s", (user_id,))
                result = await cursor.fetchone()
                return result[0] if result else None

    async def start_entry_process(self, interaction: discord.Interaction, user: discord.User, target_guild_id: int):
        """
        Startet den Einladungsprozess. Speichert die Absicht, den User zu synchronisieren.
        """
        target_guild = self.bot.get_guild(target_guild_id)
        if not target_guild:
            await interaction.followup.send("❌ Fehler: Der Ziel-Server für die Einladung wurde nicht gefunden.", ephemeral=True)
            return False

        # Du musst hier eine gültige Kanal-ID vom SU-SERVER eintragen
        invite_channel = target_guild.get_channel(1397719841326108742)
        if not invite_channel:
            await interaction.followup.send("❌ Fehler: Der Einladungs-Kanal auf dem Ziel-Server wurde nicht gefunden.", ephemeral=True)
            return False

        try:
            invite = await invite_channel.create_invite(max_uses=1, unique=True, reason=f"Einladung für {user.name}")
        except discord.Forbidden:
             await interaction.followup.send(f"❌ Fehler: Ich habe keine Berechtigung, Einladungen für den Server '{target_guild.name}' zu erstellen.", ephemeral=True)
             return False

        # Speichere die Absicht für den Beitritt auf dem SU-Server
        self.pending_entries[str(user.id)] = { "target_guild_id": target_guild_id }
        self._save_entries()

        # Sende die DM
        try:
            await user.send(f"Willkommen bei den Special Units! Bitte benutze diesen Link, um dem SU-Server beizutreten:\n{invite.url}")
            return True
        except discord.Forbidden:
            await interaction.followup.send(f"⚠️ {user.mention} konnte keine DM empfangen. Bitte sende den Link manuell: {invite.url}", ephemeral=True)
            return True

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Wird ausgelöst, wenn ein Mitglied beitritt und delegiert die gesamte Logik an den RoleSyncService.
        """
        member_id_str = str(member.id)
        if member_id_str not in self.pending_entries:
            return

        entry_data = self.pending_entries[member_id_str]
        
        # Reagiere nur, wenn der User dem richtigen (SU) Server beitritt
        if member.guild.id != entry_data.get("target_guild_id"):
            return

        del self.pending_entries[member_id_str]
        self._save_entries()

        print(f"User {member.name} ist dem Ziel-Server beigetreten. Starte Synchronisation...")

        role_sync_service: RoleSyncService = self.bot.get_cog("RoleSyncService")
        if not role_sync_service:
            print("[WARNUNG] RoleSyncService nicht gefunden. User konnte nicht synchronisiert werden.")
            return

        main_guild = self.bot.get_guild(HAUPT_SERVER_ID)
        if not main_guild:
            print(f"[FEHLER] Haupt-Server mit ID {HAUPT_SERVER_ID} nicht gefunden.")
            return
            
        try:
            main_server_member = await main_guild.fetch_member(member.id)
        except discord.NotFound:
            print(f"[WARNUNG] User {member.name} wurde auf dem Haupt-Server nicht gefunden. Sync abgebrochen.")
            return

        await role_sync_service.sync_roles_for_member(main_server_member)

async def setup(bot: "MyBot"):
    await bot.add_cog(InvitationService(bot))
import discord
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# --- Konfiguration ---
# Die IDs der beiden relevanten Server
HAUPT_SERVER_ID = 1097625621875675188
SU_SERVER_ID = 1363986017907900428

# Die ID der Rolle auf dem HAUPT-SERVER, die den Zugang zum SU-Server steuert
SEAL_UNIT_ROLE_ID = 1125174901989445693

class ExitService(commands.Cog):
    """
    Dieser Service managed das automatische Entfernen von Mitgliedern
    vom SU-Server, wenn sie die Berechtigung auf dem Haupt-Server verlieren.
    """
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "ExitService"

    async def _kick_from_su_server(self, user_id: int, reason: str):
        """
        Eine Hilfsmethode, die versucht, einen User anhand seiner ID
        vom SU-Server zu kicken.
        """
        su_guild = self.bot.get_guild(SU_SERVER_ID)
        if not su_guild:
            print(f"[ExitService] Fehler: SU-Server mit ID {SU_SERVER_ID} nicht gefunden.")
            return

        try:
            # Wir holen das Mitglied über die API, um sicherzugehen, dass es da ist
            member_to_kick = await su_guild.fetch_member(user_id)
            await member_to_kick.kick(reason=reason)
            print(f"[ExitService] User {member_to_kick.display_name} (ID: {user_id}) wurde vom SU-Server gekickt. Grund: {reason}")
        except discord.NotFound:
            # User war nicht (oder nicht mehr) auf dem SU-Server, also ist alles gut.
            pass
        except discord.Forbidden:
            print(f"[ExitService] FEHLER: Keine Berechtigung, User vom SU-Server zu kicken. Bitte Bot-Rollen prüfen.")
        except Exception as e:
            print(f"[ExitService] Ein unerwarteter Fehler beim Kicken vom SU-Server ist aufgetreten: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Wird ausgelöst, wenn sich die Rollen eines Mitglieds ändern.
        """
        # Reagiere nur auf Änderungen auf dem Haupt-Server
        if before.guild.id != HAUPT_SERVER_ID:
            return

        # Hole das Rollen-Objekt
        seal_role = before.guild.get_role(SEAL_UNIT_ROLE_ID)
        if not seal_role:
            return # Rolle nicht gefunden, nichts zu tun

        # Prüfe, ob die entscheidende Rolle entfernt wurde
        if seal_role in before.roles and seal_role not in after.roles:
            print(f"[ExitService] {after.display_name} hat die SEALs-Rolle verloren. Starte Kick-Prozess...")
            await self._kick_from_su_server(after.id, "Hat die SEALs-Unit auf dem Haupt-Server verlassen.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Wird ausgelöst, wenn ein Mitglied einen Server verlässt.
        """
        # Reagiere nur auf Abgänge vom Haupt-Server
        if member.guild.id != HAUPT_SERVER_ID:
            return
            
        print(f"[ExitService] {member.display_name} hat den Haupt-Server verlassen. Starte Kick-Prozess...")
        await self._kick_from_su_server(member.id, "Hat den Haupt-Server verlassen.")

async def setup(bot: "MyBot"):
    await bot.add_cog(ExitService(bot))
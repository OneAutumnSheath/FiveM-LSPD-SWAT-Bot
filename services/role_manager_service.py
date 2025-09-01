import discord
from discord.ext import commands
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot

class RoleManagerService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "RoleManagerService"

    async def add_role(self, user: discord.Member, role: discord.Role, reason: str) -> Dict[str, Any]:
        """Fügt einem Mitglied eine Rolle hinzu."""
        if role in user.roles:
            return {"success": False, "error": f"{user.mention} hat die Rolle '{role.name}' bereits."}

        try:
            await user.add_roles(role, reason=reason)
            return {"success": True, "message": f"Rolle '{role.name}' wurde {user.mention} erfolgreich gegeben."}
        except discord.Forbidden:
            return {"success": False, "error": "Ich habe keine Berechtigung, diese Rolle zu vergeben."}
        except Exception as e:
            return {"success": False, "error": f"Ein unerwarteter Fehler ist aufgetreten: {e}"}

    async def remove_role(self, user: discord.Member, role: discord.Role, reason: str) -> Dict[str, Any]:
        """Entfernt eine Rolle von einem Mitglied."""
        if role not in user.roles:
            return {"success": False, "error": f"{user.mention} hat die Rolle '{role.name}' nicht."}

        try:
            await user.remove_roles(role, reason=reason)
            return {"success": True, "message": f"Rolle '{role.name}' wurde {user.mention} erfolgreich entfernt."}
        except discord.Forbidden:
            return {"success": False, "error": "Ich habe keine Berechtigung, diese Rolle zu entfernen."}
        except Exception as e:
            return {"success": False, "error": f"Ein unerwarteter Fehler ist aufgetreten: {e}"}

async def setup(bot: "MyBot"):
    await bot.add_cog(RoleManagerService(bot))
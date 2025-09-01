import discord
from discord.ext import commands
import yaml
import os
import asyncio
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MyBot

CONFIG_FILE = './config/permissions.yaml'

class PermissionService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "PermissionService"
        self._permissions = {"users": {}, "roles": {}}
        self._write_lock = asyncio.Lock()
        self.bot.loop.create_task(self._load_permissions())

    async def _load_permissions(self):
        async with self._write_lock:
            if not os.path.exists(CONFIG_FILE):
                self._permissions = {"users": {}, "roles": {}}
                return
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._permissions = yaml.safe_load(f) or {"users": {}, "roles": {}}
                print("Berechtigungen erfolgreich in den Speicher geladen.")
            except Exception as e:
                print(f"FEHLER beim Laden der Berechtigungen: {e}")
                self._permissions = {"users": {}, "roles": {}}

    async def _save_permissions(self):
        async with self._write_lock:
            try:
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    yaml.dump(self._permissions, f, indent=4)
            except Exception as e:
                print(f"FEHLER beim Speichern der Berechtigungen: {e}")

    # --- Die öffentliche API deines Permission-Systems ---

    def has_permission(self, user: discord.Member, permission_node: str) -> bool:
        """Prüft Berechtigungen blitzschnell aus dem Arbeitsspeicher."""
        user_id_str = str(user.id)
        
        user_perms = self._permissions.get("users", {}).get(user_id_str, [])
        if "*" in user_perms or permission_node in user_perms:
            return True

        for role in user.roles:
            role_perms = self._permissions.get("roles", {}).get(str(role.id), [])
            if "*" in role_perms or permission_node in role_perms:
                return True
        
        return False

    async def grant_permission(self, target: discord.User | discord.Role, permission_node: str):
        """Fügt eine Berechtigung hinzu."""
        target_id_str = str(target.id)
        target_type = "users" if isinstance(target, discord.Member) or isinstance(target, discord.User) else "roles"
        
        perms_map = self._permissions.setdefault(target_type, {})
        perms_list = perms_map.setdefault(target_id_str, [])
        
        if permission_node not in perms_list:
            perms_list.append(permission_node)
            await self._save_permissions()

    async def revoke_permission(self, target: discord.User | discord.Role, permission_node: str):
        """Entfernt eine Berechtigung."""
        target_id_str = str(target.id)
        target_type = "users" if isinstance(target, discord.Member) or isinstance(target, discord.User) else "roles"
        
        perms_list = self._permissions.get(target_type, {}).get(target_id_str, [])
        if permission_node in perms_list:
            perms_list.remove(permission_node)
            await self._save_permissions()
    
    def get_permissions_for(self, target: discord.User | discord.Role) -> List[str]:
        """Gibt eine Liste der Berechtigungen für ein Ziel zurück."""
        target_id_str = str(target.id)
        target_type = "users" if isinstance(target, discord.Member) or isinstance(target, discord.User) else "roles"
        return self._permissions.get(target_type, {}).get(target_id_str, [])

async def setup(bot: "MyBot"):
    await bot.add_cog(PermissionService(bot))
import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, Union
from utils.decorators import log_on_completion
if TYPE_CHECKING:
    from main import MyBot
    from services.permission_service import PermissionService
    from services.log_service import LogService
    
TargetType = Union[discord.User, discord.Role]

class PermissionCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    perm_group = app_commands.Group(name="perm", description="Verwaltet die Berechtigungen des Bots.")

    @perm_group.command(name="grant", description="Vergibt eine Berechtigung an einen User oder eine Rolle.")
    @app_commands.describe(target="Der User oder die Rolle", permission="Die Berechtigung (z.B. 'units.eintritt')")
    @log_on_completion
    async def grant(self, interaction: discord.Interaction, target: TargetType, permission: str):
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not permission_service:
            return await interaction.response.send_message("Fehler: PermissionService nicht gefunden.", ephemeral=True)

        await permission_service.grant_permission(target, permission)
        await interaction.response.send_message(f"✅ Berechtigung `{permission}` wurde an {target.mention} vergeben.", ephemeral=True)

    @perm_group.command(name="revoke", description="Entzieht eine Berechtigung von einem User oder einer Rolle.")
    @app_commands.describe(target="Der User oder die Rolle", permission="Die Berechtigung (z.B. 'units.eintritt')")
    @log_on_completion
    async def revoke(self, interaction: discord.Interaction, target: TargetType, permission: str):
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not permission_service:
            return await interaction.response.send_message("Fehler: PermissionService nicht gefunden.", ephemeral=True)

        await permission_service.revoke_permission(target, permission)
        await interaction.response.send_message(f"🗑️ Berechtigung `{permission}` wurde von {target.mention} entfernt.", ephemeral=True)

    @perm_group.command(name="view", description="Zeigt die Berechtigungen eines Users oder einer Rolle an.")
    @app_commands.describe(target="Der User oder die Rolle")
    @log_on_completion
    async def view(self, interaction: discord.Interaction, target: TargetType):
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not permission_service:
            return await interaction.response.send_message("Fehler: PermissionService nicht gefunden.", ephemeral=True)

        perms = permission_service.get_permissions_for(target)
        
        embed = discord.Embed(title=f"Berechtigungen für {target.name}", color=target.color if isinstance(target, discord.Role) else discord.Color.blue())
        if perms:
            embed.description = "```\n" + "\n".join(perms) + "\n```"
        else:
            embed.description = "Keine spezifischen Berechtigungen gefunden."
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(PermissionCommands(bot))
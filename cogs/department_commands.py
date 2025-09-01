import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.department_service import DepartmentService
    from services.log_service import LogService
    
class DepartmentCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    check_roles_group = app_commands.Group(name="checkdepartments", description="Überprüft die Department-Rollen manuell.")

    @check_roles_group.command(name="user", description="Überprüft die Überschriften-Rollen für ein bestimmtes Mitglied.")
    @app_commands.describe(member="Das Mitglied, das überprüft werden soll.")
    @has_permission("departments.check.user")
    @log_on_completion
    async def check_user(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        service: DepartmentService = self.bot.get_cog("DepartmentService")
        if not service:
            return await interaction.followup.send("❌ Fehler: Department-Service nicht gefunden.", ephemeral=True)
            
        await service.check_all_departments_for_member(member)
        await interaction.followup.send(f"✅ Rollen für {member.mention} wurden erfolgreich überprüft und ggf. aktualisiert.", ephemeral=True)

    @check_roles_group.command(name="all", description="Überprüft die Überschriften-Rollen für ALLE Mitglieder.")
    @has_permission("departments.check.all")
    @log_on_completion
    async def check_all_members(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔁 Überprüfung aller Mitglieder gestartet. Dies kann einige Zeit dauern...", ephemeral=True)
        
        service: DepartmentService = self.bot.get_cog("DepartmentService")
        if not service:
            return await interaction.followup.send("❌ Fehler: Department-Service nicht gefunden.", ephemeral=True)
        
        count = 0
        for member in interaction.guild.members:
            if not member.bot:
                await service.check_all_departments_for_member(member)
                count += 1
        
        await interaction.followup.send(f"✅ Überprüfung abgeschlossen. {count} Mitglieder wurden überprüft.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(DepartmentCommands(bot))
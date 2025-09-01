import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.role_manager_service import RoleManagerService
    from services.log_service import LogService
    
class RoleManagerCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    @app_commands.command(name="rolle", description="Verwaltet die Rollen eines Mitglieds.")
    @app_commands.describe(
        user="Das Mitglied, dessen Rollen verwaltet werden sollen.",
        role="Die zu verwaltende Rolle.",
        action="Ob die Rolle hinzugefügt oder entfernt werden soll."
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="geben", value="add"),
        app_commands.Choice(name="entfernen", value="remove"),
    ])
    @has_permission("role.manage") # Unser neuer, zentraler Permission-Check
    @log_on_completion
    async def role_command(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, action: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)

        # Hierarchie-Prüfung (gehört zur UI, da sie die Interaktion direkt betrifft)
        if interaction.guild.me.top_role <= role:
            await interaction.followup.send(f"❌ Fehler: Ich kann die Rolle '{role.name}' nicht verwalten, da sie über meiner eigenen liegt.", ephemeral=True)
            return
        
        # Service holen
        service: RoleManagerService = self.bot.get_cog("RoleManagerService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: RoleManager-Service nicht gefunden.", ephemeral=True)

        reason = f"Durch {interaction.user} via /rolle"
        result = None

        # Passende Service-Methode aufrufen
        if action.value == "add":
            result = await service.add_role(user, role, reason)
        elif action.value == "remove":
            result = await service.remove_role(user, role, reason)
        
        # Auf das Ergebnis reagieren
        if result and result["success"]:
            await self.log_module.on_command_completion(interaction)
            await interaction.followup.send(f"✅ {result['message']}")
        elif result:
            # Falls "success" False ist (z.B. User hat Rolle schon), senden wir die "error"-Nachricht vom Service.
            # Diese ist in diesem Fall eher eine Info-Nachricht.
            await interaction.followup.send(f"ℹ️ {result['error']}", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(RoleManagerCommands(bot))
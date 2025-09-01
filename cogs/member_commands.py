import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.member_service import MemberService
    from services.log_service import LogService
class MemberCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    # Erstellt eine Gruppe für alle Befehle, z.B. /member add
    member_group = app_commands.Group(name="member", description="Grundlegende Verwaltung von Mitgliedern in der Datenbank.")

    @member_group.command(name="add", description="Fügt ein Mitglied zur Datenbank hinzu.")
    @app_commands.describe(dn="Die Dienstnummer", name="Vollständiger Name", rank="Die Rang-Rolle", discord_user="Das Discord-Mitglied")
    @has_permission("mitglieder.add")
    @log_on_completion
    async def add_member(self, interaction: discord.Interaction, dn: int, name: str, rank: discord.Role, discord_user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: MemberService = self.bot.get_cog("MemberService")
        if not service: return await interaction.followup.send("Fehler: Member-Service nicht gefunden.", ephemeral=True)
        
        result = await service.add_member(interaction.guild, dn, name, rank, discord_user)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)
        
        await self.log_module.on_command_completion(interaction)
        
        response_message = f"✅ **{name}** wurde mit DN `{dn}` und Rang {rank.mention} hinzugefügt."
        if result.get("warning"):
            response_message += f"\n⚠️ **Warnung:** {result.get('warning')}"
        await interaction.followup.send(response_message, ephemeral=True)

    @member_group.command(name="remove", description="Entfernt ein Mitglied aus der Datenbank.")
    @app_commands.describe(dn="Die DN des Mitglieds", discord_user="Das Discord-Mitglied")
    @has_permission("mitglieder.remove")
    @log_on_completion
    async def remove_member(self, interaction: discord.Interaction, dn: int = None, discord_user: discord.Member = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: MemberService = self.bot.get_cog("MemberService")
        if not service: return await interaction.followup.send("Fehler: Member-Service nicht gefunden.", ephemeral=True)
        
        if not dn and discord_user:
            dn_result = await service.get_dn_by_discord_id(discord_user.id)
            if dn_result:
                dn = int(dn_result)
        
        if not dn:
            return await interaction.followup.send("❌ Bitte eine gültige DN oder ein registriertes Mitglied angeben.", ephemeral=True)
        
        result = await service.remove_member(dn)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        await self.log_module.on_command_completion(interaction)
        await interaction.followup.send(f"✅ Mitglied mit DN `{dn}` wurde erfolgreich entfernt.", ephemeral=True)

    @member_group.command(name="setunit", description="Setzt eine Unit für ein Mitglied.")
    @app_commands.describe(member="Das Mitglied", role="Die Unit-Rolle", status="Aktiv (True) oder Inaktiv (False)")
    @has_permission("mitglieder.setunit")
    @log_on_completion
    async def set_unit(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, status: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: MemberService = self.bot.get_cog("MemberService")
        if not service: return await interaction.followup.send("Fehler: Member-Service nicht gefunden.", ephemeral=True)
        
        result = await service.set_unit_status(member, role, status)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        await self.log_module.on_command_completion(interaction)
        
        response_message = f"✅ **{member.display_name}** ist nun `{'aktiv' if status else 'inaktiv'}` in **{role.name}**."
        if result.get("warning"):
            response_message += f"\n⚠️ **Warnung:** {result.get('warning')}"
        await interaction.followup.send(response_message, ephemeral=True)

    @member_group.command(name="changerank", description="Ändert den Rang eines Mitglieds in der DB.")
    @app_commands.describe(dn="Die DN des Mitglieds", new_rank="Die neue Rang-Rolle")
    @has_permission("mitglieder.changerank")
    @log_on_completion
    async def changerank(self, interaction: discord.Interaction, dn: int, new_rank: discord.Role):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: MemberService = self.bot.get_cog("MemberService")
        if not service: return await interaction.followup.send("Fehler: Member-Service nicht gefunden.", ephemeral=True)
        
        result = await service.change_rank(dn, new_rank)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        await self.log_module.on_command_completion(interaction)
        await interaction.followup.send(f"✅ Rang für DN `{dn}` wurde auf {new_rank.mention} geändert.", ephemeral=True)

    @member_group.command(name="changedn", description="Ändert die Dienstnummer eines Mitglieds in der DB.")
    @app_commands.describe(current_dn="Die aktuelle DN", new_dn="Die neue DN")
    @has_permission("mitglieder.changedn")
    @log_on_completion
    async def changedn(self, interaction: discord.Interaction, current_dn: int, new_dn: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: MemberService = self.bot.get_cog("MemberService")
        if not service: return await interaction.followup.send("Fehler: Member-Service nicht gefunden.", ephemeral=True)
        
        result = await service.change_dn(current_dn, new_dn)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        await self.log_module.on_command_completion(interaction)
        await interaction.followup.send(f"✅ Dienstnummer `{current_dn}` wurde erfolgreich zu `{new_dn}` geändert.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(MemberCommands(bot))
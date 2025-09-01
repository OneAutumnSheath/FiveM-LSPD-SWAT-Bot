import discord
from discord import *
from discord.ext import commands
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.unit_list_service import UnitListService
    from services.role_sync_service import RoleSyncService
    from services.log_service import LogService  # Wichtig für den direkten Aufruf

# =========================================================================
# Die View für die Bestätigungs-Buttons
# =========================================================================
class ConfirmUpdateView(discord.ui.View):
    # NIMMT DAS LOG_MODULE NICHT MEHR ENTGEGEN
    def __init__(self, unit_list_service: "UnitListService", original_interaction: discord.Interaction):
        super().__init__(timeout=30)
        self.unit_list_service = unit_list_service
        self.original_interaction = original_interaction

    @discord.ui.button(label="Bestätigen", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        for item in self.children:
            item.disabled = True
        await self.original_interaction.edit_original_response(view=self)

        try:
            await self.unit_list_service.trigger_update()

            # RUFT JETZT DIREKT DEN LOGSERVICE AUF
            log_service: LogService = self.unit_list_service.bot.get_cog("LogService")
            if log_service:
                await log_service.log_command(self.original_interaction)

            await interaction.followup.send("✅ **Unit-Listen wurden erfolgreich aktualisiert!**", ephemeral=True)
        except Exception as e:
            print(f"Fehler bei der manuellen Aktualisierung der Unit-Listen: {e}")
            await interaction.followup.send("❌ **Ein Fehler ist während der Aktualisierung aufgetreten.**", ephemeral=True)

    @discord.ui.button(label="Abbrechen", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ **Aktualisierung abgebrochen.**", view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.original_interaction.edit_original_response(
                content="⚠️ **Zeitüberschreitung.** Die Aktualisierung wurde abgebrochen.", view=self
            )
        except discord.NotFound:
            pass

# =========================================================================
# Der Command-Cog
# =========================================================================
class UnitListCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        # self.log_module = LogModule(bot) <-- ENTFERNT

    unitlist_group = app_commands.Group(
        name="unitlist", description="Befehle zur Verwaltung von Unit-Listen und Decknamen."
    )

    @unitlist_group.command(name="set-deckname", description="Setzt den Decknamen eines Benutzers.")
    @app_commands.describe(user="Der Benutzer", deckname="Der neue Deckname")
    @has_permission("unitlist.deckname.set")
    @log_on_completion
    async def set_deckname_command(self, interaction: discord.Interaction, user: discord.User, deckname: str):
        await interaction.response.defer(ephemeral=True)
        service: UnitListService = self.bot.get_cog("UnitListService")
        if not service:
            return await interaction.followup.send("Fehler: UnitList-Service nicht gefunden.", ephemeral=True)
        await service.set_deckname(user.id, deckname)
        await interaction.followup.send(f"✅ Deckname für {user.mention} gesetzt auf: **{deckname}**")
        if member := interaction.guild.get_member(user.id):
            role_sync_service: RoleSyncService = self.bot.get_cog("RoleSyncService")
            if role_sync_service:
                await role_sync_service.sync_roles_for_member(member)

    @unitlist_group.command(name="remove-deckname", description="Entfernt den Decknamen eines Benutzers.")
    @app_commands.describe(user="Der Benutzer")
    @has_permission("unitlist.deckname.remove")
    @log_on_completion
    async def remove_deckname_command(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        service: UnitListService = self.bot.get_cog("UnitListService")
        if not service:
            return await interaction.followup.send("Fehler: UnitList-Service nicht gefunden.", ephemeral=True)
        await service.remove_deckname(user.id)
        await interaction.followup.send(f"🗑️ Deckname für {user.mention} wurde entfernt.")

    @unitlist_group.command(name="list-decknamen", description="Listet alle gesetzten Decknamen.")
    @has_permission("unitlist.deckname.list")
    @log_on_completion
    async def list_decknamen_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        service: UnitListService = self.bot.get_cog("UnitListService")
        if not service:
            return await interaction.followup.send("Fehler: UnitList-Service nicht gefunden.", ephemeral=True)
        eintraege = await service.list_all_decknamen()
        if not eintraege:
            return await interaction.followup.send("ℹ️ Es sind keine Decknamen gespeichert.", ephemeral=True)
        embed = discord.Embed(title="📜 Gespeicherte Decknamen", color=discord.Color.blue())
        description = [f"<@{e['user_id']}>: **{e['deckname']}**" for e in eintraege]
        embed.description = "\n".join(description)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @unitlist_group.command(name="update", description="Erzwingt eine manuelle Aktualisierung aller Unit-Listen.")
    @has_permission("unitlist.update")
    async def update_unitlists_command(self, interaction: discord.Interaction):
        service: UnitListService = self.bot.get_cog("UnitListService")
        if not service:
            return await interaction.response.send_message("❌ Fehler: UnitList-Service nicht gefunden.", ephemeral=True)

        # Erstellt die View ohne das log_module
        view = ConfirmUpdateView(service, interaction)
        await interaction.response.send_message(
            "⚠️ **Bist du sicher, dass du alle Unit-Listen manuell aktualisieren möchtest?**",
            view=view,
            ephemeral=True,
        )

    @unitlist_group.command(name="sync-sheets", description="Synchronisiert Decknamen zu Google Sheets.")
    @has_permission("unitlist.sheets.sync")
    @log_on_completion
    async def sync_sheets_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: UnitListService = self.bot.get_cog("UnitListService")
        if not service:
            return await interaction.followup.send("❌ Fehler: UnitList-Service nicht gefunden.", ephemeral=True)
        
        try:
            success = await service.sync_decknamen_to_sheets()
            
            if success:
                await interaction.followup.send("✅ **Decknamen erfolgreich zu Google Sheets synchronisiert!**", ephemeral=True)
            else:
                await interaction.followup.send("❌ **Fehler bei der Synchronisation zu Google Sheets.**", ephemeral=True)
                
        except Exception as e:
            print(f"Fehler bei Google Sheets Synchronisation: {e}")
            await interaction.followup.send("❌ **Ein Fehler ist während der Synchronisation aufgetreten.**", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(UnitListCommands(bot))
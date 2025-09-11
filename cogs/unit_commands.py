# bot/cogs/unit_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING, List

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.unit_service import UnitService
    from services.log_service import LogService

# --- Konstanten (wie im Original) ---
UNIT_CHANNEL_ID = 1213569262602559568
MGMT_ID = 1097648080020574260

class UnitCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    unit_group = app_commands.Group(name="unit", description="Befehle zur Verwaltung von Units.")

    @unit_group.command(name="eintritt", description="Lässt einen Benutzer einer Unit beitreten.")
    @app_commands.describe(user="Benutzer", unit="Unit-Rolle", grund="Grund", zusätzliche_rolle_1="Opt. Rolle", zusätzliche_rolle_2="Opt. Rolle", deckname="Opt. Deckname", zusatz="Opt. Zusatztext", override="Kapazitätsprüfung ignorieren")
    @has_permission("units.eintritt")
    @log_on_completion
    async def unit_eintritt(self, interaction: discord.Interaction, user: discord.Member, unit: discord.Role, grund: str,
                            zusätzliche_rolle_1: discord.Role = None, zusätzliche_rolle_2: discord.Role = None,
                            zusatz: str = None, deckname: str = None, override: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: UnitService = self.bot.get_cog("UnitService")
        
        if not service:
            return await interaction.followup.send("Fehler: Unit-Service wurde nicht gefunden.", ephemeral=True)

        zusatz_rollen = [r for r in [zusätzliche_rolle_1, zusätzliche_rolle_2] if r]
        result = await service.unit_entry(interaction, user, unit, grund, zusatz_rollen, zusatz, deckname, override)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        zusatz_text = f"\n\n📌 **Zusatz:** {result.get('zusatz')}" if result.get('zusatz') else ""
        
        embed = discord.Embed(
            title="🟢 Unit Eintritt", 
            description=f"📌 {user.mention} ist der Unit {result.get('unit').mention} beigetreten.\n\n✍️ **Grund:** {result.get('grund')}{zusatz_text}", 
            color=discord.Color.green()
        ).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        
        if channel := self.bot.get_channel(UNIT_CHANNEL_ID):
            await channel.send(content=user.mention, embed=embed)
        await interaction.followup.send(f"✅ **Erfolg:** {user.mention} wurde erfolgreich der Unit {result.get('unit').mention} hinzugefügt.", ephemeral=True)

    @unit_group.command(name="austritt", description="Lässt einen Benutzer aus einer Unit austreten.")
    @app_commands.describe(user="Benutzer", unit="Unit-Rolle", grund="Grund", zu_entfernende_rolle_1="Opt. Rolle", zu_entfernende_rolle_2="Opt. Rolle")
    @has_permission("units.austritt")
    @log_on_completion
    async def unit_austritt(self, interaction: discord.Interaction, user: discord.Member, unit: discord.Role, grund: str,
                            zu_entfernende_rolle_1: discord.Role = None, zu_entfernende_rolle_2: discord.Role = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: UnitService = self.bot.get_cog("UnitService")
        
        if not service:
            return await interaction.followup.send("Fehler: Unit-Service wurde nicht gefunden.", ephemeral=True)

        rollen_zum_entfernen = [r for r in [zu_entfernende_rolle_1, zu_entfernende_rolle_2] if r]
        
        result = await service.unit_exit(interaction, user, unit, grund, rollen_zum_entfernen)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)
            
        embed = discord.Embed(
            title="🔴 Unit Austritt", 
            description=f"📌 {user.mention} hat die Unit {result.get('unit').mention} verlassen.\n\n✍️ Grund: {result.get('grund')}", 
            color=discord.Color.red()
        ).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        
        if channel := self.bot.get_channel(UNIT_CHANNEL_ID):
            await channel.send(content=user.mention, embed=embed)
        await interaction.followup.send(f"✅ **Erfolg:** {user.mention} wurde erfolgreich aus der Unit {result.get('unit').mention} entfernt.", ephemeral=True)
    
    @unit_group.command(name="aufstieg", description="Lässt einen Benutzer aufsteigen.")
    @app_commands.describe(user="Benutzer", unit="Unit", grund="Grund", zu_entfernende_rolle_1="Alte Rolle", zu_entfernende_rolle_2="Weitere alte Rolle", neuer_posten="Neue Rolle", zusätzliche_rolle="Zusätzliche neue Rolle")
    @has_permission("units.aufstieg")
    @log_on_completion
    async def unit_aufstieg(self, interaction: discord.Interaction, user: discord.Member, unit: discord.Role, grund: str,
                            zu_entfernende_rolle_1: discord.Role = None, zu_entfernende_rolle_2: discord.Role = None,
                            neuer_posten: discord.Role = None, zusätzliche_rolle: discord.Role = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: UnitService = self.bot.get_cog("UnitService")
        
        if not service:
            return await interaction.followup.send("Fehler: Unit-Service wurde nicht gefunden.", ephemeral=True)
        
        roles_to_add = [unit, neuer_posten, zusätzliche_rolle]
        roles_to_remove = [zu_entfernende_rolle_1, zu_entfernende_rolle_2]
        
        result = await service.unit_promotion(user, grund, [r for r in roles_to_add if r], [r for r in roles_to_remove if r])
        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        embed = discord.Embed(
            title="🔹 Unit Aufstieg",
            description=(f"📌 **{user.mention} steigt innerhalb der Unit {unit.mention} auf.**\n\n✍️ **Grund:** {grund}\n\n📌 **Neuer Posten:** {neuer_posten.mention if neuer_posten else 'Zum vollwertigen Mitglied'}"),
            color=discord.Color.blue()
        ).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        
        if channel := self.bot.get_channel(UNIT_CHANNEL_ID):
            await channel.send(content=user.mention, embed=embed)
        await interaction.followup.send("✅ **Erfolg:** Der Aufstieg wurde erfolgreich durchgeführt.", ephemeral=True)

    @unit_group.command(name="abstieg", description="Degradiert einen Benutzer innerhalb einer Unit.")
    @app_commands.describe(user="Benutzer", unit="Unit", alter_posten="Alte Rolle", grund="Grund", neuer_posten="Neue Rolle")
    @has_permission("units.abstieg")
    @log_on_completion
    async def unit_abstieg(self, interaction: discord.Interaction, user: discord.Member, unit: discord.Role,
                           alter_posten: discord.Role, grund: str, neuer_posten: discord.Role = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: UnitService = self.bot.get_cog("UnitService")
        
        if not service:
            return await interaction.followup.send("Fehler: Unit-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.unit_demotion(user, grund, alter_posten, neuer_posten)
        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        desc = (f"⚠️ **{user.mention} wurde innerhalb der Unit {unit.mention} degradiert.**\n\n✍️ **Grund:** {grund}\n\n❌ **Alter Posten:** {alter_posten.mention}\n\n")
        if neuer_posten:
            desc += f"📌 **Neuer Posten:** {neuer_posten.mention}\n\n"
        desc += f"Hochachtungsvoll,\n<@&{MGMT_ID}>"
        
        embed = discord.Embed(title="🔻 Unit Abstieg", description=desc, color=discord.Color.orange())
        embed.set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        
        if channel := self.bot.get_channel(UNIT_CHANNEL_ID):
            await channel.send(content=user.mention, embed=embed)
        await interaction.followup.send("✅ **Erfolg:** Der Abstieg wurde erfolgreich durchgeführt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(UnitCommands(bot))
# bot/cogs/personal_commands.py

import discord
from discord.ext import commands
from discord import app_commands, Interaction
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion
from datetime import datetime, timezone

if TYPE_CHECKING:
    from main import MyBot
    from services.personal_service import PersonalService
    from services.log_service import LogService

PERSONAL_CHANGE = 1213569259024678973
PERSONAL_FIRE = 1213569260996010135
PERSONAL_HIRE = 1231644627698712586
TRAINING_CHANNEL = 1213569272379473970
MGMT_ID = 1097648080020574260

class PersonalCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    personal_group = app_commands.Group(name="personal", description="Befehle zur Personalverwaltung.")

    @personal_group.command(name="einstellen", description="Stellt einen neuen Rekruten ein.")
    @app_commands.describe(user="Der einzustellende Benutzer", name="Vollständiger Name", dienstgrad="Der Start-Dienstgrad", grund="Grund der Einstellung", dn="Optionale feste Dienstnummer")
    @has_permission("personal.einstellen")
    @log_on_completion
    async def einstellen(self, interaction: Interaction, user: discord.Member, name: str, dienstgrad: discord.Role, grund: str, dn: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.hire_member(interaction.guild, user, name, dienstgrad, grund, dn)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)
        
        # Embed im neuen Format erstellen
        embed_announcement = discord.Embed(
            title="Einstellung im Los Santos Police Department",
            description=f"Sehr geehrtes Los Santos Police Department!\nHiermit geben wir die Einstellung von {user.mention} bekannt.",
            color=discord.Color.green()
        )
        
        # Felder hinzufügen
        embed_announcement.add_field(name="Grund", value=result['reason'], inline=False)
        
        # Footer mit Datum
        embed_announcement.set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster • {datetime.now().strftime('%d.%m.%Y, %H:%M Uhr')}")
        
        if channel := self.bot.get_channel(PERSONAL_HIRE):
            await channel.send(content=user.mention, embed=embed_announcement)

        embed_confirm = discord.Embed(
            title="✅ Einstellung erfolgreich",
            description=(f"{user.mention} wurde erfolgreich als {result['rank_role'].mention} eingestellt.\n"
                         f"📋 **Dienstnummer:** `{result['dn']}`\n"
                         f"📂 **Division:** <@&{result['division_id']}>"),
            color=discord.Color.green()
        )
        if result.get("warning"):
            embed_confirm.add_field(name="⚠️ Warnung", value=result["warning"], inline=False)
        await interaction.followup.send(embed=embed_confirm, ephemeral=True)

    @personal_group.command(name="kuendigen", description="Entlässt ein Mitglied.")
    @app_commands.describe(user="Das zu entlassende Mitglied", grund="Grund der Kündigung")
    @has_permission("personal.kuendigen")
    @log_on_completion
    async def kuendigen(self, interaction: Interaction, user: discord.Member, grund: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.fire_member(user, grund)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        # Embed im neuen Format erstellen
        embed_announcement = discord.Embed(
            title="Kündigung vom Los Santos Police Department",
            description=f"Sehr geehrtes Los Santos Police Department!\nHiermit geben wir die Kündigung von {user.display_name} bekannt.",
            color=discord.Color.red()
        )
        
        # Felder hinzufügen
        embed_announcement.add_field(name="Name", value=user.display_name, inline=False)
        embed_announcement.add_field(name="Dienstnummer", value=result['dn'], inline=False)
        embed_announcement.add_field(name="Grund", value=result['reason'], inline=False)
        
        # Footer mit Datum
        embed_announcement.set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster • {datetime.now().strftime('%d.%m.%Y, %H:%M Uhr')}")
        
        if channel := self.bot.get_channel(PERSONAL_FIRE):
            await channel.send(content=user.mention, embed=embed_announcement)
        await interaction.followup.send(f"✅ {user.display_name} wurde erfolgreich gekündigt.", ephemeral=True)

    @personal_group.command(name="kuendigung_ankuendigung", description="Erstellt eine einfache Kündigungs-Ankündigung.")
    @app_commands.describe(user="Der Name der Person", grund="Grund der Kündigung", dn="Dienstnummer der Person")
    @has_permission("personal.kuendigung_ankuendigung")
    @log_on_completion
    async def kuendigung_ankuendigung(self, interaction: Interaction, user: str, grund: str, dn: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Embed für die Ankündigung erstellen
        embed_announcement = discord.Embed(
            title="Kündigung vom Los Santos Police Department",
            description=f"Sehr geehrtes Los Santos Police Department!\nHiermit geben wir die Kündigung von {user} bekannt.",
            color=discord.Color.red()
        )
        
        # Felder hinzufügen
        embed_announcement.add_field(name="Name", value=user, inline=False)
        embed_announcement.add_field(name="Dienstnummer", value=dn, inline=False)
        embed_announcement.add_field(name="Grund", value=grund, inline=False)
        
        # Footer mit Datum
        embed_announcement.set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster • {datetime.now().strftime('%d.%m.%Y, %H:%M Uhr')}")
        
        # Ankündigung im Personal-Kanal posten
        if channel := self.bot.get_channel(PERSONAL_FIRE):
            await channel.send(embed=embed_announcement)
        
        # Bestätigung an den ausführenden User
        await interaction.followup.send(f"✅ Kündigungs-Ankündigung für {user} wurde erfolgreich gepostet.", ephemeral=True)

    @personal_group.command(name="training_absolviert", description="Markiert ein Training als absolviert und gibt dem User die entsprechende Rolle.")
    @app_commands.describe(user="Das Mitglied", ausbildungsrolle="Die zu vergebende Ausbildungsrolle", grund="Grund/Art der Ausbildung")
    @has_permission("personal.training_absolviert")
    @log_on_completion
    async def training_absolviert(self, interaction: Interaction, user: discord.Member, ausbildungsrolle: discord.Role, grund: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Rolle dem User geben
        try:
            await user.add_roles(ausbildungsrolle, reason=f"Training absolviert: {grund}")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ **Fehler:** Konnte {ausbildungsrolle.mention} nicht zu {user.mention} hinzufügen. {e}", ephemeral=True)
        
        # Embed für die Ankündigung erstellen
        embed_announcement = discord.Embed(
            title="Ausbildung im Los Santos Police Department",
            description=f"Sehr geehrtes Los Santos Police Department!\nHiermit geben wir die Ausbildung von {user.mention} bekannt.",
            color=discord.Color.green()
        )
        
        # Felder hinzufügen
        embed_announcement.add_field(name="Ausbildungsrolle", value=ausbildungsrolle.mention, inline=False)
        embed_announcement.add_field(name="Grund", value=grund, inline=False)
        
        # Footer mit Datum
        embed_announcement.set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster • {datetime.now().strftime('%d.%m.%Y, %H:%M Uhr')}")
        
        # Ankündigung im Training-Kanal posten
        if channel := self.bot.get_channel(TRAINING_CHANNEL):
            await channel.send(content=user.mention, embed=embed_announcement)
        
        # Bestätigung an den ausführenden User
        await interaction.followup.send(f"✅ {user.mention} hat erfolgreich die Ausbildung absolviert und {ausbildungsrolle.mention} erhalten.", ephemeral=True)

    @personal_group.command(name="uprank", description="Befördert ein Mitglied.")
    @app_commands.describe(user="Das Mitglied", neuer_rang="Der neue Rang", grund="Grund", sperre_ignorieren="Ignoriert Uprank-Sperre (Admin)")
    @has_permission("personal.uprank")
    @log_on_completion
    async def uprank(self, interaction: Interaction, user: discord.Member, neuer_rang: discord.Role, grund: str, sperre_ignorieren: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if sperre_ignorieren and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("❌ Du hast keine Berechtigung, die Uprank-Sperre zu ignorieren.", ephemeral=True)
            
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.promote_member(interaction.guild, user, neuer_rang, grund, ignore_lock=sperre_ignorieren)
        
        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        description = f"Hiermit wurde {user.mention} zum {neuer_rang.mention} befördert.\n\nGrund: {grund}\n\n"
        if result["dn_changed"]:
            description += f"Neue Dienstnummer: **{result['new_dn']}**\n\n"
        
        embed = discord.Embed(title="Beförderung", description=description, color=discord.Color.green()).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        if channel := self.bot.get_channel(PERSONAL_CHANGE):
            await channel.send(content=user.mention, embed=embed)
        
        embed_confirm = discord.Embed(title="✅ Beförderung erfolgreich", description=f"{user.mention} wurde erfolgreich befördert.\n📋 **Neuer Rang:** {neuer_rang.mention}\n📂 **Division:** <@&{result['new_division_id']}>", color=discord.Color.green())
        await interaction.followup.send(embed=embed_confirm, ephemeral=True)

    @personal_group.command(name="derank", description="Degradiert ein Mitglied.")
    @app_commands.describe(user="Das Mitglied", neuer_rang="Der neue Rang", grund="Grund")
    @has_permission("personal.derank")
    @log_on_completion
    async def derank(self, interaction: Interaction, user: discord.Member, neuer_rang: discord.Role, grund: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.demote_member(interaction.guild, user, neuer_rang, grund)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)

        description = f"Hiermit wurde {user.mention} zum {neuer_rang.mention} degradiert.\n\nGrund: {grund}\n\n"
        if result["dn_changed"]:
            description += f"Neue Dienstnummer: **{result['new_dn']}**\n\n"

        embed = discord.Embed(title="Degradierung", description=description, color=discord.Color.red()).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        if channel := self.bot.get_channel(PERSONAL_CHANGE):
            await channel.send(content=user.mention, embed=embed)

        embed_confirm = discord.Embed(title="✅ Degradierung erfolgreich", description=f"{user.mention} wurde erfolgreich degradiert.\n📋 **Neuer Rang:** {neuer_rang.mention}\n📂 **Division:** <@&{result['new_division_id']}>", color=discord.Color.red())
        await interaction.followup.send(embed=embed_confirm, ephemeral=True)

    @personal_group.command(name="neuedn", description="Ändert die Dienstnummer eines Mitglieds.")
    @app_commands.describe(user="Das Mitglied", neue_dn="Die neue Dienstnummer")
    @has_permission("personal.neuedn")
    @log_on_completion
    async def neuedn(self, interaction: Interaction, user: discord.Member, neue_dn: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.change_dn(user, neue_dn)

        if not result.get("success"):
            return await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)
        
        embed_announcement = discord.Embed(
            title="🔄 Dienstnummer Änderung",
            description=(f"**Dienstnummer-Update für {user.mention}!**\n\n**Alte DN:** `{result['old_dn']}`\n**Neue DN:** `{result['new_dn']}`"),
            color=discord.Color.blue()
        ).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
        if channel := self.bot.get_channel(PERSONAL_CHANGE):
            await channel.send(content=user.mention, embed=embed_announcement)
        
        await interaction.followup.send(f"✅ Dienstnummer für {user.mention} erfolgreich zu `{result['new_dn']}` geändert.", ephemeral=True)

    @personal_group.command(name="rename", description="Benennt ein Mitglied um.")
    @app_commands.describe(user="Das Mitglied", new_name="Der neue Name")
    @has_permission("personal.rename")
    @log_on_completion
    async def rename(self, interaction: Interaction, user: discord.Member, new_name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        service: PersonalService = self.bot.get_cog("PersonalService")
        
        if not service: 
            return await interaction.followup.send("Fehler: Personal-Service wurde nicht gefunden.", ephemeral=True)

        result = await service.rename_member(user, new_name)
        
        if result.get("success"):
            description=(f"**{user.mention} wurde umbenannt.**\n\n"
                         f"**Alter Name:** `{result.get('old_name', 'N/A')}`\n"
                         f"**Neuer Name:** `{result.get('new_name', 'N/A')}`")

            embed_announcement = discord.Embed(
                title="📛 Namensänderung",
                description=description,
                color=discord.Color.orange()
            ).set_footer(text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources - in Vetretung des Chiefs of Police Tommy Lancaster")
            
            if channel := self.bot.get_channel(PERSONAL_CHANGE):
                await channel.send(content=user.mention, embed=embed_announcement)

            confirm_message = f"✅ {user.mention} wurde erfolgreich in **{new_name}** umbenannt."
            if warning := result.get("warning"):
                confirm_message += f"\n\n⚠️ **Warnung:** {warning}"

            await interaction.followup.send(confirm_message, ephemeral=True)
        else:
            error_message = result.get("error", "Ein unbekannter Fehler ist aufgetreten.")
            await interaction.followup.send(f"❌ **Fehler:** {error_message}", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(PersonalCommands(bot))
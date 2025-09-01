import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_sperre_service import UprankSperreService
    from services.log_service import LogService
    
class UprankSperreCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    sperre_group = app_commands.Group(name="uprank", description="Verwaltet Uprank-Sperren.")

    @sperre_group.command(name="sperre-berechnen", description="Setzt den Uprank-Zeitpunkt basierend auf dem neuen Rang.")
    @app_commands.describe(user="Das Mitglied, dessen Uprank gesetzt wird.", rang_id="Die neue Rang-ID des Mitglieds (1–12)")
    @has_permission("uprank_sperre.berechnen")
    @log_on_completion
    async def upranksperre(self, interaction: discord.Interaction, user: discord.Member, rang_id: int):
        await interaction.response.defer(ephemeral=True)
        
        service: UprankSperreService = self.bot.get_cog("UprankSperreService")
        if not service: return await interaction.followup.send("Fehler: UprankSperre-Service nicht gefunden.", ephemeral=True)
            
        dn = await service.get_dn_by_userid(user.id)
        if not dn:
            return await interaction.followup.send(f"❌ Für {user.mention} wurde keine Dienstnummer gefunden.", ephemeral=True)
        
        await service.setze_sperre(dn, rang_id)
        await interaction.followup.send(f"✅ Uprank-Zeitpunkt für {user.mention} wurde basierend auf Rang-ID {rang_id} gesetzt/aktualisiert.", ephemeral=True)

    @sperre_group.command(name="sperre-setzen", description="Setzt eine manuelle Uprank-Sperre bis zu einem Datum.")
    @app_commands.describe(user="Das Mitglied, das gesperrt werden soll.", datum="Das Enddatum der Sperre im Format DD.MM.YYYY")
    @has_permission("uprank_sperre.setzen")
    @log_on_completion
    async def sperre_setzen(self, interaction: discord.Interaction, user: discord.Member, datum: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            ende_datum = datetime.strptime(datum, "%d.%m.%Y").replace(hour=23, minute=59, second=59)
        except ValueError:
            return await interaction.followup.send("❌ Ungültiges Datumsformat. Bitte benutze `DD.MM.YYYY`.", ephemeral=True)
            
        service: UprankSperreService = self.bot.get_cog("UprankSperreService")
        if not service: return await interaction.followup.send("Fehler: UprankSperre-Service nicht gefunden.", ephemeral=True)

        dn = await service.get_dn_by_userid(user.id)
        if not dn:
            return await interaction.followup.send(f"❌ Für {user.mention} wurde keine Dienstnummer gefunden.", ephemeral=True)

        await service.setze_sperre_mit_datum(dn, ende_datum)
        await interaction.followup.send(f"✅ Uprank-Sperre für {user.mention} wurde manuell bis zum {datum} gesetzt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankSperreCommands(bot))
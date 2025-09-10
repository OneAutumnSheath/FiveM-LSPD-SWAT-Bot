# bot/cogs/sanction_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING, Dict, Any
import yaml

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.sanction_service import SanctionService
    from services.display_service import DisplayService

class SanctionCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/sanctions_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError: 
            return {}

    @app_commands.command(name="sanktion", description="Erstellt eine Sanktion für einen Benutzer.")
    @app_commands.describe(
        user="Das Mitglied",
        strafe="Die Strafe (z.B. 'Verwarnung + 10 Runden ums Army Fort + 124.250$')",
        grund="Der Grund für die Sanktion",
        datum="Zu zahlen bis (Optional, Format: DD.MM.YYYY)"
    )
    @has_permission("sanktion.create")
    @log_on_completion
    async def sanktion(self, interaction: discord.Interaction, user: discord.Member, strafe: str, grund: str, datum: str = None):
        await interaction.response.defer(ephemeral=True)
        
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service: 
            return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)

        # DisplayService für die Anzeige verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            user_display = await display_service.get_display(user)
            executor_display = await display_service.get_display(interaction.user, is_footer=True)
        else:
            user_display = user.mention
            executor_display = interaction.user.display_name

        # Verwarnungen aus der Strafe extrahieren und verarbeiten
        neue_verwarnungen = await service.extract_and_process_warnings(user, strafe)
        
        # Sanktions-Channel holen
        channel = self.bot.get_channel(self._config.get('sanktion_channel_id'))
        if not channel:
            return await interaction.followup.send("❌ Sanktions-Channel nicht in der Config gefunden.", ephemeral=True)

        # Embed erstellen (wie im Screenshot)
        embed = discord.Embed(
            title="Sanktion",
            description="Sehr geehrtes Los Santos Police Department!\n\nIm Zuge eines Vergehens gegen die Dienstvorschrift, wird folgende Sanktion erteilt.",
            color=discord.Color.red()  # Rot wie im Screenshot
        )
        
        # Mitarbeiter-Info mit Deckname falls vorhanden
        unit_service = self.bot.get_cog("UnitListService")
        deckname = ""
        if unit_service:
            user_deckname = await unit_service.get_deckname(user.id)
            if user_deckname:
                deckname = f" [{user_deckname}]"
        
        embed.add_field(
            name="Officer", 
            value=f"{user.mention}{deckname}", 
            inline=True
        )
        embed.add_field(
            name="Strafe", 
            value=strafe, 
            inline=True
        )
        embed.add_field(
            name="Grund", 
            value=grund, 
            inline=True
        )
        
        # Datum automatisch setzen (7 Tage ab heute) oder manuell überschreiben
        if datum:
            zahlungsdatum = datum
        else:
            from datetime import datetime, timedelta
            zahlungsdatum = (datetime.now() + timedelta(days=7)).strftime("%a %b %d %Y")
        
        embed.add_field(
            name="Zu zahlen bis", 
            value=zahlungsdatum, 
            inline=False
        )
        
        # Belehrung hinzufügen
        embed.add_field(
            name="Belehrung",
            value="Sollte diese Sanktion nicht bis zum oben genannten Datum beglichen werden, so wird eine weitere Sanktion im doppelten Wert ausgesprochen.",
            inline=False
        )
        
        # Footer mit Ausführer und HR-Info
        embed.set_footer(
            text=f"Ausgeführt von {executor_display} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster"
        )
        
        # LSPD Logo (falls vorhanden)
        embed.set_thumbnail(url="https://i.imgur.com/your-lspd-logo.png")  # Ersetze mit tatsächlicher URL
        
        # Nachricht senden
        await channel.send(content=user.mention, embed=embed)
        
        # Erfolgsmeldung
        await interaction.followup.send(
            f"✅ Sanktion für {user_display} wurde erfolgreich erstellt.", 
            ephemeral=True
        )

async def setup(bot: "MyBot"):
    await bot.add_cog(SanctionCommands(bot))
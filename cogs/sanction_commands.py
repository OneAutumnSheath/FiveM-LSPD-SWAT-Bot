# bot/cogs/sanction_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import TYPE_CHECKING, Dict, Any
import yaml
from datetime import datetime

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.sanction_service import SanctionService

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
            text=f"Ausgeführt von {interaction.user.display_name} | Ausgeführt von der Human Resources des Departments - in Vertretung für den Chief of Police Tommy Lancaster"
        )
        
        # LSPD Logo (falls vorhanden)
        embed.set_thumbnail(url="https://i.ibb.co/b5F0vJN/lspd.png")  # Ersetze mit tatsächlicher URL
        
        # Nachricht senden
        await channel.send(content=user.mention, embed=embed)
        
        # Sanktion in Datenbank speichern
        await service.save_sanction_to_db(
            user=user,
            strafe=strafe,
            grund=grund,
            zahlungsdatum=zahlungsdatum,
            erstellt_von=interaction.user,
            deckname=deckname.strip(" []") if deckname else None
        )
        
        # Erfolgsmeldung
        await interaction.followup.send(
            f"✅ Sanktion für {user.mention} wurde erfolgreich erstellt und in der Datenbank gespeichert.", 
            ephemeral=True
        )

    @app_commands.command(name="sanktionen-anzeigen", description="Zeigt offene Sanktionen an.")
    @app_commands.describe(
        user="Zeige nur Sanktionen für einen bestimmten User (Optional)",
        alle="Zeige alle Sanktionen (auch erledigte) an"
    )
    @has_permission("sanktion.view")
    async def sanktionen_anzeigen(self, interaction: discord.Interaction, user: discord.Member = None, alle: bool = False):
        await interaction.response.defer(ephemeral=True)
        
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service:
            return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)

        # Sanktionen aus der Datenbank holen
        if alle:
            sanctions = await service.get_all_sanctions(user.id if user else None, limit=20)
            title = f"Alle Sanktionen{' für ' + user.display_name if user else ''}"
        else:
            sanctions = await service.get_open_sanctions(user.id if user else None)
            title = f"Offene Sanktionen{' für ' + user.display_name if user else ''}"

        if not sanctions:
            status = "alle" if alle else "offene"
            user_text = f" für {user.display_name}" if user else ""
            return await interaction.followup.send(f"ℹ️ Keine {status} Sanktionen{user_text} gefunden.", ephemeral=True)

        # Embed erstellen
        embed = discord.Embed(
            title=title,
            color=discord.Color.orange() if not alle else discord.Color.blue()
        )

        # Sanktionen auflisten (max. 10 pro Nachricht)
        sanctions_shown = sanctions[:10]
        
        for sanction in sanctions_shown:
            status_icon = "✅" if sanction['erledigt'] else "⏳"
            erledigt_text = ""
            
            if sanction['erledigt']:
                erledigt_am = sanction['erledigt_am'].strftime("%d.%m.%Y") if sanction['erledigt_am'] else "Unbekannt"
                erledigt_text = f"\n**Erledigt:** {erledigt_am} von {sanction['erledigt_von_name']}"
            
            field_value = (
                f"**Strafe:** {sanction['strafe']}\n"
                f"**Grund:** {sanction['grund']}\n"
                f"**Fällig:** {sanction['zahlungsdatum']}\n"
                f"**Erstellt:** {sanction['erstellt_am'].strftime('%d.%m.%Y')} von {sanction['erstellt_von_name']}"
                f"{erledigt_text}"
            )
            
            # Kürzen falls zu lang
            if len(field_value) > 1024:
                field_value = field_value[:1020] + "..."
            
            embed.add_field(
                name=f"{status_icon} ID {sanction['id']} - {sanction['user_name']}",
                value=field_value,
                inline=False
            )

        # Info falls mehr Sanktionen vorhanden
        if len(sanctions) > 10:
            embed.set_footer(text=f"Zeige {len(sanctions_shown)} von {len(sanctions)} Sanktionen. Verwende Filter für spezifischere Ergebnisse.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="sanktion-erledigt", description="Markiert eine Sanktion als erledigt.")
    @app_commands.describe(
        sanktion_id="Die ID der zu erledigenden Sanktion"
    )
    @has_permission("sanktion.complete")
    @log_on_completion
    async def sanktion_erledigt(self, interaction: discord.Interaction, sanktion_id: int):
        await interaction.response.defer(ephemeral=True)
        
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service:
            return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)

        # Sanktion suchen
        sanction = await service.get_sanction_by_id(sanktion_id)
        if not sanction:
            return await interaction.followup.send(f"❌ Sanktion mit ID {sanktion_id} nicht gefunden.", ephemeral=True)

        if sanction['erledigt']:
            erledigt_am = sanction['erledigt_am'].strftime("%d.%m.%Y %H:%M") if sanction['erledigt_am'] else "Unbekannt"
            return await interaction.followup.send(
                f"ℹ️ Sanktion {sanktion_id} wurde bereits am {erledigt_am} von {sanction['erledigt_von_name']} als erledigt markiert.", 
                ephemeral=True
            )

        # Als erledigt markieren
        success = await service.mark_sanction_as_completed(sanktion_id, interaction.user)
        
        if success:
            # Bestätigungs-Embed
            embed = discord.Embed(
                title="✅ Sanktion erledigt",
                description=f"Sanktion ID {sanktion_id} wurde erfolgreich als erledigt markiert.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Betroffener Officer",
                value=sanction['user_name'],
                inline=True
            )
            embed.add_field(
                name="Strafe",
                value=sanction['strafe'],
                inline=True
            )
            embed.add_field(
                name="Erledigt von",
                value=interaction.user.display_name,
                inline=True
            )
            embed.add_field(
                name="Erledigt am",
                value=datetime.now().strftime("%d.%m.%Y %H:%M"),
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Optional: Log-Channel benachrichtigen
            log_channel = self.bot.get_channel(self._config.get('sanktion_log_channel_id'))
            if log_channel:
                log_embed = discord.Embed(
                    title="📋 Sanktion abgeschlossen",
                    description=f"Sanktion ID {sanktion_id} für {sanction['user_name']} wurde von {interaction.user.mention} als erledigt markiert.",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await log_channel.send(embed=log_embed)
                
        else:
            await interaction.followup.send(f"❌ Fehler beim Markieren der Sanktion {sanktion_id} als erledigt.", ephemeral=True)

    @app_commands.command(name="sanktionen-statistik", description="Zeigt Statistiken über Sanktionen an.")
    @has_permission("sanktion.stats")
    async def sanktionen_statistik(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: SanctionService = self.bot.get_cog("SanctionService")
        if not service:
            return await interaction.followup.send("Fehler: Sanction-Service nicht gefunden.", ephemeral=True)

        # Statistiken sammeln
        alle_sanktionen = await service.get_all_sanctions(limit=1000)
        offene_sanktionen = await service.get_open_sanctions()
        
        if not alle_sanktionen:
            return await interaction.followup.send("ℹ️ Keine Sanktionen in der Datenbank gefunden.", ephemeral=True)

        erledigte_count = len([s for s in alle_sanktionen if s['erledigt']])
        offene_count = len(offene_sanktionen)
        
        # Top 5 bestrafete User
        user_counts = {}
        for sanction in alle_sanktionen:
            user_name = sanction['user_name']
            user_counts[user_name] = user_counts.get(user_name, 0) + 1
        
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        embed = discord.Embed(
            title="📊 Sanktionen-Statistik",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📋 Gesamt",
            value=f"**{len(alle_sanktionen)}** Sanktionen",
            inline=True
        )
        embed.add_field(
            name="⏳ Offen",
            value=f"**{offene_count}** Sanktionen",
            inline=True
        )
        embed.add_field(
            name="✅ Erledigt",
            value=f"**{erledigte_count}** Sanktionen",
            inline=True
        )
        
        if top_users:
            top_list = "\n".join([f"{i+1}. {name}: {count}" for i, (name, count) in enumerate(top_users)])
            embed.add_field(
                name="🏆 Top 5 Officer (meiste Sanktionen)",
                value=top_list,
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(SanctionCommands(bot))
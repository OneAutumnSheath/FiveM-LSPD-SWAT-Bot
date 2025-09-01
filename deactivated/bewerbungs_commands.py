# cogs/bewerbungs_commands.py

import discord
from discord.ext import commands
from discord import app_commands, Interaction
import asyncio
from typing import TYPE_CHECKING
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.bewerbungs_service import BewerbungsService

# --- Cross-Server Konstanten ---
PUBLIC_SERVER_ID = 1097626402540499044         # Öffentlicher Server (Bewerber + Tickets)
INTERNAL_SERVER_ID = 1097625621875675188       # Interner Server (HR/Staff + Einstellungen)

class BewerbungsCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    bewerbung_group = app_commands.Group(name="bewerbung", description="Befehle für das Bewerbungssystem.")

    @bewerbung_group.command(name="status", description="Zeigt den Status deiner Bewerbung an.")
    async def bewerbung_status(self, interaction: Interaction):
        """Zeigt den Bewerbungsstatus an"""
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        bewerbung = await service._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (interaction.user.id,), fetch="one"
        )
        
        if not bewerbung:
            return await interaction.followup.send("❌ Du hast noch keine Bewerbung eingereicht.")
        
        status_colors = {
            "pending": discord.Color.orange(),
            "accepted": discord.Color.green(),
            "rejected": discord.Color.red(),
            "archived": discord.Color.light_grey()
        }
        
        status_texts = {
            "pending": "⏳ In Bearbeitung",
            "accepted": "✅ Angenommen (Einladung zum internen Server versendet)",
            "rejected": "❌ Abgelehnt",
            "archived": "📁 Archiviert"
        }
        
        embed = discord.Embed(
            title="📋 Bewerbungsstatus",
            color=status_colors.get(bewerbung['status'], discord.Color.blue())
        )
        
        embed.add_field(name="📊 Status", value=status_texts.get(bewerbung['status'], bewerbung['status']), inline=True)
        embed.add_field(name="📅 Eingereicht", value=f"<t:{int(bewerbung['created_at'].timestamp())}:R>", inline=True)
        
        if bewerbung['ticket_channel_id']:
            embed.add_field(name="🎫 Ticket", value=f"<#{bewerbung['ticket_channel_id']}>", inline=True)
        
        if bewerbung['processed_at']:
            embed.add_field(name="🔄 Bearbeitet", value=f"<t:{int(bewerbung['processed_at'].timestamp())}:R>", inline=True)
        
        embed.add_field(name="🌐 Server", value="Tickets werden auf dem öffentlichen Server bearbeitet", inline=False)
        
        await interaction.followup.send(embed=embed)

    @bewerbung_group.command(name="liste", description="Zeigt alle offenen Bewerbungen an.")
    @has_permission("bewerbung.verwalten")
    async def bewerbung_liste(self, interaction: Interaction):
        """Zeigt alle offenen Bewerbungen für das Personal"""
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        bewerbungen = await service._execute_query(
            "SELECT * FROM bewerbungen WHERE status = 'pending' ORDER BY created_at ASC",
            fetch="all"
        )
        
        if not bewerbungen:
            return await interaction.followup.send("📋 Keine offenen Bewerbungen vorhanden.")
        
        embed = discord.Embed(
            title="📋 Offene Bewerbungen",
            description=f"Insgesamt {len(bewerbungen)} offene Bewerbung(en)\n🌐 **Tickets auf öffentlichem Server**",
            color=discord.Color.blue()
        )
        
        for i, bewerbung in enumerate(bewerbungen[:10]):  # Maximal 10 anzeigen
            user_mention = f"<@{bewerbung['user_id']}>"
            status = "⏳ Wartet auf Namen" if not bewerbung['real_name'] else ("📝 Wartet auf Bewerbung" if not bewerbung['age'] else "✅ Vollständig")
            
            embed.add_field(
                name=f"#{i+1} - {bewerbung['real_name'] or bewerbung['username']}",
                value=(
                    f"**User:** {user_mention}\n"
                    f"**Status:** {status}\n"
                    f"**Erstellt:** <t:{int(bewerbung['created_at'].timestamp())}:R>\n"
                    f"**Ticket:** <#{bewerbung['ticket_channel_id']}>"
                ),
                inline=True
            )
        
        if len(bewerbungen) > 10:
            embed.set_footer(text=f"... und {len(bewerbungen) - 10} weitere Bewerbungen")
        
        await interaction.followup.send(embed=embed)

    @bewerbung_group.command(name="panel", description="Erstellt das Bewerbungspanel.")
    @has_permission("bewerbung.verwalten")
    @log_on_completion
    async def bewerbung_panel(self, interaction: Interaction, kanal: discord.TextChannel = None):
        """Erstellt ein Bewerbungspanel in einem Kanal (nur auf öffentlichem Server)"""
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob auf öffentlichem Server
        if interaction.guild.id != PUBLIC_SERVER_ID:
            return await interaction.followup.send(
                f"❌ Das Bewerbungspanel kann nur auf dem **öffentlichen Server** erstellt werden.\n"
                f"Aktueller Server: `{interaction.guild.name}` (ID: `{interaction.guild.id}`)",
                ephemeral=True
            )
        
        target_channel = kanal or interaction.channel
        
        embed = discord.Embed(
            title="📝 U.S. ARMY Bewerbung",
            description=(
                "Willkommen bei der U.S. ARMY Discord-Community!\n\n"
                "**Möchtest du Teil unserer Gemeinschaft werden?**\n"
                "Klicke auf den Button unten, um ein Bewerbungsticket zu erstellen.\n\n"
                "📋 **Bewerbungsvoraussetzungen:**\n"
                "• Mindestalter: 16 Jahre\n"
                "• Discord-Account mindestens 30 Tage alt\n"
                "• Respektvoller Umgang\n"
                "• Aktive Teilnahme erwünscht\n\n"
                "🎯 **Was erwartet dich:**\n"
                "• Professionelle Struktur\n"
                "• Trainings und Events\n"
                "• Gemeinschaftsgefühl\n"
                "• Aufstiegsmöglichkeiten\n\n"
                "ℹ️ **Nach der Annahme erhältst du eine Einladung zu unserem internen Server.**"
            ),
            color=discord.Color.blue()
        )
        
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text="U.S. ARMY Recruitment • Cross-Server System")
        
        view = BewerbungsPanelView()
        
        try:
            await target_channel.send(embed=embed, view=view)
            await interaction.followup.send(f"✅ Bewerbungspanel wurde in {target_channel.mention} erstellt.")
        except discord.Forbidden:
            await interaction.followup.send(f"❌ Keine Berechtigung zum Senden in {target_channel.mention}")

    @bewerbung_group.command(name="statistiken", description="Zeigt Bewerbungsstatistiken an.")
    @has_permission("bewerbung.verwalten")
    async def bewerbung_statistiken(self, interaction: Interaction):
        """Zeigt Bewerbungsstatistiken"""
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        # Hole verschiedene Statistiken
        total = await service._execute_query("SELECT COUNT(*) as count FROM bewerbungen", fetch="one")
        pending = await service._execute_query("SELECT COUNT(*) as count FROM bewerbungen WHERE status = 'pending'", fetch="one")
        accepted = await service._execute_query("SELECT COUNT(*) as count FROM bewerbungen WHERE status = 'accepted'", fetch="one")
        rejected = await service._execute_query("SELECT COUNT(*) as count FROM bewerbungen WHERE status = 'rejected'", fetch="one")
        
        # Unvollständige Bewerbungen
        incomplete = await service._execute_query("SELECT COUNT(*) as count FROM bewerbungen WHERE status = 'pending' AND (real_name IS NULL OR age IS NULL)", fetch="one")
        
        # Letzte 30 Tage
        recent = await service._execute_query(
            "SELECT COUNT(*) as count FROM bewerbungen WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)", 
            fetch="one"
        )
        
        # Cross-Server Statistiken
        pending_hires = await service._execute_query("SELECT COUNT(*) as count FROM pending_hires", fetch="one")
        
        embed = discord.Embed(
            title="📊 Cross-Server Bewerbungsstatistiken",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="📋 Gesamt", value=total['count'], inline=True)
        embed.add_field(name="⏳ Offen", value=pending['count'], inline=True)
        embed.add_field(name="✅ Angenommen", value=accepted['count'], inline=True)
        embed.add_field(name="❌ Abgelehnt", value=rejected['count'], inline=True)
        embed.add_field(name="📝 Unvollständig", value=incomplete['count'], inline=True)
        embed.add_field(name="📅 Letzten 30 Tage", value=recent['count'], inline=True)
        embed.add_field(name="⏳ Warten auf Beitritt", value=pending_hires['count'], inline=True)
        
        # Berechne Annahmerate
        if total['count'] > 0:
            acceptance_rate = (accepted['count'] / (accepted['count'] + rejected['count'])) * 100 if (accepted['count'] + rejected['count']) > 0 else 0
            embed.add_field(name="📈 Annahmerate", value=f"{acceptance_rate:.1f}%", inline=True)
        
        # Server-Info
        public_guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        
        embed.add_field(
            name="🌐 Server-Status", 
            value=(
                f"**Öffentlich:** {'✅' if public_guild else '❌'} {public_guild.name if public_guild else 'Nicht verbunden'}\n"
                f"**Intern:** {'✅' if internal_guild else '❌'} {internal_guild.name if internal_guild else 'Nicht verbunden'}"
            ), 
            inline=False
        )
        
        await interaction.followup.send(embed=embed)

    @bewerbung_group.command(name="ticket_schließen", description="Schließt ein Bewerbungsticket.")
    @has_permission("bewerbung.verwalten")
    @log_on_completion
    async def ticket_schliessen(self, interaction: Interaction):
        """Schließt das aktuelle Bewerbungsticket"""
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob auf öffentlichem Server
        if interaction.guild.id != PUBLIC_SERVER_ID:
            return await interaction.followup.send("❌ Tickets können nur auf dem öffentlichen Server verwaltet werden.", ephemeral=True)
        
        if not interaction.channel.name.startswith('ticket-'):
            return await interaction.followup.send("❌ Dies ist kein Bewerbungsticket.")
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        # Update Status in DB
        await service._execute_query(
            "UPDATE bewerbungen SET status = 'archived' WHERE ticket_channel_id = %s",
            (interaction.channel.id,)
        )
        
        # Archiviere das Ticket
        await service.archive_ticket(interaction.channel)
        await interaction.followup.send("✅ Ticket wird archiviert...")

    @bewerbung_group.command(name="force_delete", description="Löscht ein Bewerbungsticket sofort.")
    @has_permission("bewerbung.verwalten")
    @log_on_completion
    async def force_delete_ticket(self, interaction: Interaction):
        """Löscht das aktuelle Bewerbungsticket sofort"""
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob auf öffentlichem Server
        if interaction.guild.id != PUBLIC_SERVER_ID:
            return await interaction.followup.send("❌ Tickets können nur auf dem öffentlichen Server verwaltet werden.", ephemeral=True)
        
        if not interaction.channel.name.startswith('ticket-'):
            return await interaction.followup.send("❌ Dies ist kein Bewerbungsticket.")
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        # Lösche aus DB
        await service._execute_query(
            "DELETE FROM bewerbungen WHERE ticket_channel_id = %s",
            (interaction.channel.id,)
        )
        
        await interaction.followup.send("✅ Ticket wird in 5 Sekunden gelöscht...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket gelöscht von {interaction.user}")

    @bewerbung_group.command(name="cleanup", description="Bereinigt verwaiste Tickets.")
    @has_permission("bewerbung.verwalten")
    @log_on_completion
    async def cleanup_tickets(self, interaction: Interaction):
        """Bereinigt verwaiste oder alte Tickets"""
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        # Finde alle Bewerbungstickets
        bewerbungen = await service._execute_query(
            "SELECT * FROM bewerbungen WHERE status = 'pending' AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY)",
            fetch="all"
        )
        
        cleaned_count = 0
        
        # Prüfe öffentlichen Server
        public_guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        if public_guild:
            for bewerbung in bewerbungen:
                channel = public_guild.get_channel(bewerbung['ticket_channel_id'])
                if not channel:
                    # Kanal existiert nicht mehr, lösche DB-Eintrag
                    await service._execute_query(
                        "DELETE FROM bewerbungen WHERE id = %s",
                        (bewerbung['id'],)
                    )
                    cleaned_count += 1
        
        # Bereinige auch abgelaufene pending_hires
        expired_hires = await service._execute_query(
            "DELETE FROM pending_hires WHERE expires_at < NOW()"
        )
        
        embed = discord.Embed(
            title="🧹 Cross-Server Cleanup abgeschlossen",
            description=f"**{cleaned_count}** verwaiste Ticket-Einträge wurden bereinigt.",
            color=discord.Color.green()
        )
        
        if len(bewerbungen) > cleaned_count:
            remaining = len(bewerbungen) - cleaned_count
            embed.add_field(
                name="⚠️ Alte Tickets", 
                value=f"{remaining} Tickets sind älter als 7 Tage und könnten manuell überprüft werden.",
                inline=False
            )
        
        embed.add_field(
            name="🗑️ Abgelaufene Einladungen",
            value="Abgelaufene Einladungen wurden automatisch bereinigt.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)

    @bewerbung_group.command(name="info", description="Zeigt Informationen über ein Bewerbungsticket.")
    @has_permission("bewerbung.verwalten")
    async def bewerbung_info(self, interaction: Interaction, user: discord.User = None):
        """Zeigt detaillierte Informationen über eine Bewerbung"""
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = self.bot.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.")
        
        # Bestimme User (entweder Parameter oder aus Ticket-Kanal)
        target_user = user
        if not target_user and interaction.channel.name.startswith('ticket-'):
            # Versuche User aus Ticket zu finden
            bewerbung = await service._execute_query(
                "SELECT user_id FROM bewerbungen WHERE ticket_channel_id = %s",
                (interaction.channel.id,), fetch="one"
            )
            if bewerbung:
                try:
                    target_user = await self.bot.fetch_user(bewerbung['user_id'])
                except:
                    pass
        
        if not target_user:
            return await interaction.followup.send("❌ Kein User angegeben und nicht in einem Ticket-Kanal.")
        
        # Hole Bewerbungsdaten
        bewerbung = await service._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (target_user.id,), fetch="one"
        )
        
        if not bewerbung:
            return await interaction.followup.send(f"❌ Keine Bewerbung für {target_user.mention} gefunden.")
        
        # Hole pending hire info
        pending_hire = await service._execute_query(
            "SELECT * FROM pending_hires WHERE user_id = %s",
            (target_user.id,), fetch="one"
        )
        
        embed = discord.Embed(
            title="📋 Cross-Server Bewerbungsinformationen",
            description=f"**Bewerber:** {target_user.mention}",
            color=discord.Color.blue()
        )
        
        # Grunddaten
        embed.add_field(name="👤 Name", value=bewerbung.get('real_name') or "Noch nicht angegeben", inline=True)
        embed.add_field(name="🎂 Alter", value=str(bewerbung['age']) if bewerbung['age'] else "Noch nicht angegeben", inline=True)
        embed.add_field(name="📊 Status", value=bewerbung['status'].upper(), inline=True)
        
        # Zeiten
        embed.add_field(name="📅 Eingereicht", value=f"<t:{int(bewerbung['created_at'].timestamp())}:F>", inline=False)
        if bewerbung['processed_at']:
            embed.add_field(name="🔄 Bearbeitet", value=f"<t:{int(bewerbung['processed_at'].timestamp())}:F>", inline=False)
        
        # Bearbeiter
        if bewerbung['processed_by']:
            try:
                processor = await self.bot.fetch_user(bewerbung['processed_by'])
                embed.add_field(name="👨‍💼 Bearbeitet von", value=processor.mention, inline=True)
            except:
                embed.add_field(name="👨‍💼 Bearbeitet von", value=f"<@{bewerbung['processed_by']}>", inline=True)
        
        # Ticket-Link (öffentlicher Server)
        if bewerbung['ticket_channel_id']:
            embed.add_field(name="🎫 Ticket (Öffentlich)", value=f"<#{bewerbung['ticket_channel_id']}>", inline=True)
        
        # Cross-Server Info
        if pending_hire:
            embed.add_field(
                name="⏳ Wartet auf Beitritt", 
                value=f"Einladung läuft ab: <t:{int(pending_hire['expires_at'].timestamp())}:R>", 
                inline=True
            )
            embed.add_field(name="💬 Annahmegrund", value=pending_hire.get('acceptance_reason', 'Nicht angegeben'), inline=False)
        
        # Server-Status
        public_guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        
        # Prüfe ob User auf den Servern ist
        public_member = public_guild.get_member(target_user.id) if public_guild else None
        internal_member = internal_guild.get_member(target_user.id) if internal_guild else None
        
        embed.add_field(
            name="🌐 Server-Mitgliedschaft",
            value=(
                f"**Öffentlich:** {'✅' if public_member else '❌'}\n"
                f"**Intern:** {'✅' if internal_member else '❌'}"
            ),
            inline=True
        )
        
        # Bewerbungsdetails (falls vorhanden)
        if bewerbung.get('motivation'):
            embed.add_field(name="💭 Motivation", value=bewerbung['motivation'][:1000] + ("..." if len(bewerbung['motivation']) > 1000 else ""), inline=False)
        
        if bewerbung.get('experience'):
            embed.add_field(name="🎮 Erfahrung", value=bewerbung['experience'][:500] + ("..." if len(bewerbung['experience']) > 500 else ""), inline=False)
        
        if bewerbung.get('availability'):
            embed.add_field(name="📅 Verfügbarkeit", value=bewerbung['availability'], inline=True)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Cross-Server System • User ID: {target_user.id}")
        
        await interaction.followup.send(embed=embed)

    @bewerbung_group.command(name="debug_cross_server", description="Debug: Cross-Server Konfiguration testen")
    @has_permission("bewerbung.verwalten")
    async def debug_cross_server(self, interaction: Interaction):
        """Testet die Cross-Server Konfiguration"""
        await interaction.response.defer(ephemeral=True)
        
        debug_info = []
        
        # 1. Server-Verbindungen testen
        public_guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        
        debug_info.append(f"**🌐 Server-Verbindungen:**")
        debug_info.append(f"Öffentlicher Server: {'✅' if public_guild else '❌'} {public_guild.name if public_guild else 'Nicht gefunden'} (ID: `{PUBLIC_SERVER_ID}`)")
        debug_info.append(f"Interner Server: {'✅' if internal_guild else '❌'} {internal_guild.name if internal_guild else 'Nicht gefunden'} (ID: `{INTERNAL_SERVER_ID}`)")
        
        # 2. Aktueller Server
        debug_info.append(f"\n**📍 Aktueller Server:**")
        debug_info.append(f"Name: `{interaction.guild.name}`")
        debug_info.append(f"ID: `{interaction.guild.id}`")
        debug_info.append(f"Typ: {'🌐 Öffentlich' if interaction.guild.id == PUBLIC_SERVER_ID else ('🔒 Intern' if interaction.guild.id == INTERNAL_SERVER_ID else '❓ Unbekannt')}")
        
        # 3. Kategorien/Kanäle testen (falls auf öffentlichem Server)
        if public_guild and interaction.guild.id == PUBLIC_SERVER_ID:
            from services.bewerbungs_service import BEWERBUNGS_KANAL_ID, ARCHIVE_KATEGORIE_ID
            
            debug_info.append(f"\n**📁 Öffentlicher Server - Kanäle:**")
            bewerbungs_kat = public_guild.get_channel(BEWERBUNGS_KANAL_ID)
            archiv_kat = public_guild.get_channel(ARCHIVE_KATEGORIE_ID)
            
            debug_info.append(f"Bewerbungs-Kategorie: {'✅' if bewerbungs_kat else '❌'} {bewerbungs_kat.name if bewerbungs_kat else 'Nicht gefunden'}")
            debug_info.append(f"Archiv-Kategorie: {'✅' if archiv_kat else '❌'} {archiv_kat.name if archiv_kat else 'Nicht gefunden'}")
        
        # 4. Rollen testen
        if internal_guild:
            from services.bewerbungs_service import STANDARD_RANG_ROLE_ID
            
            debug_info.append(f"\n**🎖️ Interner Server - Rollen:**")
            standard_role = internal_guild.get_role(STANDARD_RANG_ROLE_ID)
            debug_info.append(f"Standard-Rang: {'✅' if standard_role else '❌'} {standard_role.name if standard_role else 'Nicht gefunden'}")
        
        # 5. Bot-Berechtigungen
        debug_info.append(f"\n**🤖 Bot-Berechtigungen:**")
        if public_guild:
            public_perms = public_guild.me.guild_permissions
            debug_info.append(f"Öffentlich - Administrator: {'✅' if public_perms.administrator else '❌'}")
            debug_info.append(f"Öffentlich - Kanäle verwalten: {'✅' if public_perms.manage_channels else '❌'}")
            debug_info.append(f"Öffentlich - Einladungen erstellen: {'✅' if public_perms.create_instant_invite else '❌'}")
        
        if internal_guild:
            internal_perms = internal_guild.me.guild_permissions
            debug_info.append(f"Intern - Administrator: {'✅' if internal_perms.administrator else '❌'}")
            debug_info.append(f"Intern - Einladungen erstellen: {'✅' if internal_perms.create_instant_invite else '❌'}")
            debug_info.append(f"Intern - Rollen verwalten: {'✅' if internal_perms.manage_roles else '❌'}")
        
        embed = discord.Embed(
            title="🔍 Cross-Server Debug-Informationen",
            description="\n".join(debug_info),
            color=discord.Color.blue()
        )
        
        await interaction.followup.send(embed=embed)


# --- UI Klassen ---
class BewerbungsPanelView(discord.ui.View):
    """Persistente View für das Bewerbungspanel"""
    
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Bewerbungsticket erstellen", style=discord.ButtonStyle.primary, custom_id="create_bewerbungsticket")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Prüfe ob auf öffentlichem Server
        if interaction.guild.id != PUBLIC_SERVER_ID:
            return await interaction.followup.send(
                "❌ Bewerbungen können nur auf dem öffentlichen Server eingereicht werden.",
                ephemeral=True
            )
        
        # Prüfe Account-Alter
        account_age = (discord.utils.utcnow() - interaction.user.created_at).days
        if account_age < 30:
            return await interaction.followup.send(
                f"❌ Dein Discord-Account ist erst {account_age} Tage alt. "
                "Du musst mindestens 30 Tage Mitglied bei Discord sein, um dich zu bewerben.",
                ephemeral=True
            )
        
        # Prüfe ob bereits Mitglied auf internem Server
        internal_guild = interaction.client.get_guild(INTERNAL_SERVER_ID)
        if internal_guild:
            internal_member = internal_guild.get_member(interaction.user.id)
            if internal_member:
                return await interaction.followup.send(
                    "❌ Du bist bereits Mitglied auf unserem internen Server!",
                    ephemeral=True
                )
        
        # Prüfe auf bereits existierendes Ticket
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if service:
            existing = await service._execute_query(
                "SELECT id FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
                (interaction.user.id,), fetch="one"
            )
            
            if existing:
                return await interaction.followup.send(
                    "❌ Du hast bereits ein offenes Bewerbungsticket! Bitte verwende dein bestehendes Ticket.",
                    ephemeral=True
                )
        
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.", ephemeral=True)
        
        # Erstelle Ticket
        result = await service.create_ticket(interaction.user)
        
        if result.get("success"):
            embed = discord.Embed(
                title="✅ Ticket erstellt!",
                description=(
                    f"Dein Bewerbungsticket wurde erfolgreich erstellt!\n\n"
                    f"🎫 **Ticket:** {result['ticket_channel'].mention}\n\n"
                    "📋 **Nächste Schritte:**\n"
                    "1️⃣ Gib deinen vollständigen Namen im Ticket an\n"
                    "2️⃣ Fülle deine Bewerbung aus\n"
                    "3️⃣ Warte auf die Bearbeitung durch unser HR-Team\n\n"
                    "🎯 **Bei Annahme:** Du erhältst eine Einladung zu unserem internen Server\n\n"
                    "💡 Gehe jetzt in dein Ticket und folge den Anweisungen!"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)


async def setup(bot: "MyBot"):
    # Registriere persistente Views
    bot.add_view(BewerbungsPanelView())
    
    # Registriere auch die Views aus dem Service
    from services.bewerbungs_service import BewerbungsView, BewerbungsFormularView, AcceptModal
    bot.add_view(BewerbungsView(0))  # Mit Dummy-ID für Persistenz
    
    await bot.add_cog(BewerbungsCommands(bot))
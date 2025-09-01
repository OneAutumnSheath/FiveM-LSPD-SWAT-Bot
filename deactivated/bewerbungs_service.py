
import discord
from discord.ext import commands
import aiomysql
import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any, Optional

if TYPE_CHECKING:
    from main import MyBot
    from services.personal_service import PersonalService

# --- Cross-Server Konstanten ---
PUBLIC_SERVER_ID = 1097626402540499044         # Öffentlicher Server (Bewerber + Tickets)
INTERNAL_SERVER_ID = 1097625621875675188       # Interner Server (HR/Staff + Einstellungen)

# Öffentlicher Server - Ticket-Verwaltung
BEWERBUNGS_KANAL_ID = 1097628377592115212      # Kategorie für Tickets
ARCHIVE_KATEGORIE_ID = 1409273663148261599     # Archiv-Kategorie
HR_ROLE_ID = 1097628354296954950               # HR-Rolle auf öffentlichem Server

# Interner Server - Einstellungen
STANDARD_RANG_ROLE_ID = 1097625924104626198    # Private-Rolle auf INTERNEM Server
INTERNAL_EINSTELLUNGS_CHANNEL_ID = 1097655800673095801  # Einstellungsbenachrichtigungen
INTERNAL_PERSONAL_CHANNEL_ID = 1097625981671448698      # Personal-Channel auf internem Server

class BewerbungsService(commands.Cog):
    """
    Service für die Verwaltung von Bewerbungstickets
    """
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "BewerbungsService"

    async def cog_load(self):
        """Initialisierung beim Laden des Cogs"""
        await self._ensure_table_exists()

    async def _ensure_table_exists(self):
        """Erstellt die Tabelle für Bewerbungen falls sie nicht existiert"""
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bewerbungen (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255) NOT NULL,
                        real_name VARCHAR(255) NULL,
                        age INT NULL,
                        motivation TEXT NULL,
                        experience TEXT,
                        availability TEXT,
                        ticket_channel_id BIGINT,
                        status ENUM('pending', 'accepted', 'rejected', 'archived') DEFAULT 'pending',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processed_by BIGINT NULL,
                        processed_at DATETIME NULL
                    )
                """)

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        """Hilfsfunktion für Datenbankabfragen"""
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one":
                    return await cursor.fetchone()
                elif fetch == "all":
                    return await cursor.fetchall()

    async def create_ticket(self, user: discord.User) -> Dict[str, Any]:
        """
        Erstellt ein neues Bewerbungsticket auf dem ÖFFENTLICHEN Server
        """
        # Prüfe ob bereits ein offenes Ticket existiert
        existing = await self._execute_query(
            "SELECT id FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
            (user.id,), fetch="one"
        )
        
        if existing:
            return {"success": False, "error": "Du hast bereits ein offenes Bewerbungsticket!"}

        # Hole ÖFFENTLICHEN Server
        guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        if not guild:
            return {"success": False, "error": "Öffentlicher Server nicht gefunden"}

        # Erstelle Ticket-Kanal
        kategorie = guild.get_channel(BEWERBUNGS_KANAL_ID)
        if not kategorie or not isinstance(kategorie, discord.CategoryChannel):
            return {"success": False, "error": "Bewerbungskategorie nicht gefunden"}

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }

        # Füge HR-Berechtigungen hinzu
        if hr_role := guild.get_role(HR_ROLE_ID):
            overwrites[hr_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_channel = await guild.create_text_channel(
                f"ticket-{user.name}",
                category=kategorie,
                overwrites=overwrites,
                reason=f"Bewerbungsticket für {user.name}"
            )
        except discord.HTTPException as e:
            return {"success": False, "error": f"Konnte Ticket-Kanal nicht erstellen: {e}"}

        # Erstelle grundlegenden DB-Eintrag (ohne Bewerbungsdaten)
        try:
            await self._execute_query("""
                INSERT INTO bewerbungen (user_id, username, ticket_channel_id, status)
                VALUES (%s, %s, %s, 'pending')
            """, (user.id, user.name, ticket_channel.id))
        except Exception as e:
            # Lösche Kanal falls DB-Eintrag fehlschlägt
            await ticket_channel.delete(reason="DB-Fehler bei Ticket-Erstellung")
            return {"success": False, "error": f"Datenbankfehler: {e}"}

        # Sende initiale Nachrichten
        await self._send_initial_ticket_message(ticket_channel, user)
        
        return {"success": True, "ticket_channel": ticket_channel}

    async def _send_initial_ticket_message(self, channel: discord.TextChannel, user: discord.User):
        """Sendet die initiale Nachricht im Ticket mit Name-Abfrage"""
        
        # Willkommensnachricht für den Bewerber
        welcome_embed = discord.Embed(
            title="🎖️ Willkommen bei der U.S. ARMY!",
            description=(
                f"Hallo {user.mention}!\n\n"
                "Vielen Dank für dein Interesse an unserer Community. "
                "Wir freuen uns auf deine Bewerbung!\n\n"
                "**📋 Nächste Schritte:**\n"
                "1️⃣ Teile uns zunächst deinen **vollständigen Namen** mit\n"
                "2️⃣ Fülle anschließend deine Bewerbung aus\n"
                "3️⃣ Warte auf die Bearbeitung durch unser HR-Team\n\n"
                "💡 **Tipp:** Schreibe einfach deinen Namen in den Chat!"
            ),
            color=discord.Color.blue()
        )
        welcome_embed.set_thumbnail(url=user.display_avatar.url)
        
        await channel.send(f"👋 {user.mention}", embed=welcome_embed)
        
        # Nachricht für das Personal
        hr_embed = discord.Embed(
            title="🆕 Neues Bewerbungsticket",
            description=f"**Bewerber:** {user.mention}\n**User ID:** `{user.id}`\n**Account erstellt:** <t:{int(user.created_at.timestamp())}:R>",
            color=discord.Color.orange()
        )
        hr_embed.add_field(
            name="⏳ Status", 
            value="Wartet auf Namensangabe", 
            inline=False
        )
        
        await channel.send(embed=hr_embed)

    async def update_bewerbung_with_name(self, user_id: int, real_name: str) -> Dict[str, Any]:
        """
        Aktualisiert die Bewerbung mit dem Namen und sendet das Bewerbungsformular
        """
        # Finde das Ticket
        bewerbung = await self._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s AND status = 'pending' AND real_name IS NULL",
            (user_id,), fetch="one"
        )
        
        if not bewerbung:
            return {"success": False, "error": "Kein offenes Ticket gefunden"}
        
        # Update mit Namen
        await self._execute_query(
            "UPDATE bewerbungen SET real_name = %s WHERE user_id = %s",
            (real_name, user_id)
        )
        
        return {"success": True, "ticket_channel_id": bewerbung['ticket_channel_id']}

    async def complete_bewerbung(self, user_id: int, bewerbung_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Vervollständigt die Bewerbung mit allen Daten und leitet an HR weiter
        """
        # Update Bewerbung mit vollständigen Daten
        try:
            await self._execute_query("""
                UPDATE bewerbungen 
                SET age = %s, motivation = %s, experience = %s, availability = %s, status = 'pending'
                WHERE user_id = %s AND status = 'pending'
            """, (
                bewerbung_data["age"],
                bewerbung_data["motivation"],
                bewerbung_data.get("experience", ""),
                bewerbung_data.get("availability", ""),
                user_id
            ))
        except Exception as e:
            return {"success": False, "error": f"Datenbankfehler: {e}"}

        # Hole aktualisierte Bewerbung
        bewerbung = await self._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
            (user_id,), fetch="one"
        )
        
        if not bewerbung:
            return {"success": False, "error": "Bewerbung nicht gefunden"}

        # Hole Ticket-Kanal vom ÖFFENTLICHEN Server
        guild = self.bot.get_guild(PUBLIC_SERVER_ID)
        if not guild:
            return {"success": False, "error": "Öffentlicher Server nicht gefunden"}
            
        ticket_channel = guild.get_channel(bewerbung['ticket_channel_id'])
        if not ticket_channel:
            return {"success": False, "error": "Ticket-Kanal nicht gefunden"}

        # Sende Bewerbungs-Embed mit Aktionsbuttons an HR
        user = await self.bot.fetch_user(user_id)
        await self._send_bewerbung_embed(ticket_channel, user, bewerbung)
        
        return {"success": True, "ticket_channel": ticket_channel}

    async def _send_hr_review_embed(self, channel: discord.TextChannel, user: discord.User, bewerbung: dict):
        """Sendet das HR-Review-Embed direkt nach der Namensangabe"""
        embed = discord.Embed(
            title="📝 Bewerbung zur Prüfung",
            description=f"**Bewerbung von {user.mention}**\n*Bereit zur Bearbeitung durch HR*",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👤 Name", value=bewerbung["real_name"], inline=True)
        embed.add_field(name="📅 Account erstellt", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="📊 Status", value="Wartet auf HR-Entscheidung", inline=True)
        
        # Zusätzliche Infos
        embed.add_field(name="🆔 User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="📱 Username", value=f"`{user.name}`", inline=True)
        embed.add_field(name="📅 Eingereicht", value=f"<t:{int(bewerbung['created_at'].timestamp())}:R>", inline=True)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Schnell-Bewerbung • User ID: {user.id}")

        # HR kann direkt entscheiden
        embed.add_field(
            name="ℹ️ Hinweis", 
            value="Dies ist eine Schnell-Bewerbung. HR kann direkt basierend auf dem Namen und Profil entscheiden.", 
            inline=False
        )

        # Erstelle View mit HR-Buttons
        view = BewerbungsView(user.id)
        
        # Trennlinie für HR-Bereich
        await channel.send("─" * 50)
        await channel.send(f"📋 **SCHNELL-BEWERBUNG ZUR BEARBEITUNG**\n<@&1097648080020574260>", embed=embed, view=view)
        """Sendet das finale Bewerbungs-Embed mit Aktionsbuttons für HR"""
        embed = discord.Embed(
            title="📝 Bewerbung zur Prüfung",
            description=f"**Vollständige Bewerbung von {user.mention}**",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👤 Name", value=bewerbung["real_name"], inline=True)
        embed.add_field(name="🎂 Alter", value=str(bewerbung["age"]), inline=True)
        embed.add_field(name="📅 Verfügbarkeit", value=bewerbung.get("availability") or "Nicht angegeben", inline=True)
        embed.add_field(name="💭 Motivation", value=bewerbung["motivation"], inline=False)
        
        if bewerbung.get("experience"):
            embed.add_field(name="🎮 Erfahrung", value=bewerbung["experience"], inline=False)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Bewerbung • User ID: {user.id}")

    async def _send_bewerbung_embed(self, channel: discord.TextChannel, user: discord.User, bewerbung: dict):
        """Sendet das finale Bewerbungs-Embed mit Aktionsbuttons für HR (für komplette Bewerbungen)"""
        embed = discord.Embed(
            title="📝 Vollständige Bewerbung zur Prüfung",
            description=f"**Vollständige Bewerbung von {user.mention}**",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👤 Name", value=bewerbung["real_name"], inline=True)
        embed.add_field(name="🎂 Alter", value=str(bewerbung["age"]), inline=True)
        embed.add_field(name="📅 Verfügbarkeit", value=bewerbung.get("availability") or "Nicht angegeben", inline=True)
        embed.add_field(name="💭 Motivation", value=bewerbung["motivation"], inline=False)
        
        if bewerbung.get("experience"):
            embed.add_field(name="🎮 Erfahrung", value=bewerbung["experience"], inline=False)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Vollständige Bewerbung • User ID: {user.id}")

        # Erstelle View mit Buttons für HR
        view = BewerbungsView(user.id)
        
        # Trennlinie für HR-Bereich
        await channel.send("─" * 50)
        await channel.send(f"📋 **VOLLSTÄNDIGE BEWERBUNG ZUR BEARBEITUNG**\n<@&1097648080020574260>", embed=embed, view=view)

    async def accept_bewerbung(self, interaction: discord.Interaction, applicant_id: int, reason: str) -> Dict[str, Any]:
        """
        Akzeptiert eine Bewerbung und lädt zum INTERNEN Server ein
        """
        # Hole Bewerbungsdaten
        bewerbung = await self._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
            (applicant_id,), fetch="one"
        )
        
        if not bewerbung:
            return {"success": False, "error": "Bewerbung nicht gefunden oder bereits bearbeitet"}

        # Hole den User
        try:
            user = await self.bot.fetch_user(applicant_id)
        except discord.NotFound:
            return {"success": False, "error": "Benutzer nicht gefunden"}

        # Hole INTERNEN Server für Einladung
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        if not internal_guild:
            return {"success": False, "error": "Interner Server nicht gefunden"}
        
        # Hole Standard-Rang vom INTERNEN Server
        standard_rank_role = internal_guild.get_role(STANDARD_RANG_ROLE_ID)
        if not standard_rank_role:
            return {"success": False, "error": "Standard-Rang auf internem Server nicht gefunden"}

        # Erstelle Einladung für INTERNEN Server
        try:
            # Verwende einen Kanal vom internen Server für die Einladung
            invite_channel = internal_guild.system_channel or internal_guild.text_channels[0]
            invite = await invite_channel.create_invite(
                max_uses=1,
                max_age=86400,  # 24 Stunden
                unique=True,
                reason=f"Einladung für akzeptierte Bewerbung von {user.name}"
            )
        except discord.Forbidden:
            return {"success": False, "error": "Keine Berechtigung zum Erstellen von Einladungen auf internem Server"}

        # Sende DM mit Einladung zum INTERNEN Server
        try:
            dm_embed = discord.Embed(
                title="🎉 Bewerbung angenommen!",
                description=(
                    f"Herzlichen Glückwunsch {user.name}!\n\n"
                    "Deine Bewerbung wurde **angenommen**! "
                    "Verwende den untenstehenden Link, um unserem internen Discord-Server beizutreten.\n\n"
                    "📋 **Nach dem Beitritt wirst du automatisch eingestellt:**\n"
                    f"• Rang: {standard_rank_role.name}\n"
                    f"• Name: {bewerbung['real_name']}\n\n"
                    "Willkommen im Team! 🇺🇸"
                ),
                color=discord.Color.green()
            )
            
            dm_embed.add_field(
                name="🔗 Einladungslink (Interner Server)",
                value=f"[Hier klicken zum Beitreten]({invite.url})",
                inline=False
            )
            dm_embed.set_footer(text="Dieser Link ist nur einmal verwendbar und 24h gültig!")
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            # Falls DM nicht möglich ist, zeige Link im Ticket
            return {
                "success": True, 
                "invite_url": invite.url,
                "dm_failed": True,
                "message": "Bewerbung angenommen, aber DM konnte nicht gesendet werden"
            }

        # Aktualisiere Bewerbungsstatus
        await self._execute_query("""
            UPDATE bewerbungen 
            SET status = 'accepted', processed_by = %s, processed_at = NOW() 
            WHERE user_id = %s
        """, (interaction.user.id, applicant_id))

        # Speichere Einladung für spätere Verarbeitung (für INTERNEN Server)
        await self._execute_query("""
            INSERT INTO pending_hires (user_id, real_name, invite_code, rank_role_id, invited_by, acceptance_reason, target_server_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL 24 HOUR))
            ON DUPLICATE KEY UPDATE 
            real_name = VALUES(real_name), 
            invite_code = VALUES(invite_code),
            rank_role_id = VALUES(rank_role_id),
            invited_by = VALUES(invited_by),
            acceptance_reason = VALUES(acceptance_reason),
            target_server_id = VALUES(target_server_id),
            expires_at = VALUES(expires_at)
        """, (applicant_id, bewerbung['real_name'], invite.code, STANDARD_RANG_ROLE_ID, interaction.user.id, reason, INTERNAL_SERVER_ID))

        return {"success": True, "invite_sent": True, "reason": reason}

    async def reject_bewerbung(self, interaction: discord.Interaction, applicant_id: int, reason: str = None) -> Dict[str, Any]:
        """
        Lehnt eine Bewerbung ab
        """
        bewerbung = await self._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
            (applicant_id,), fetch="one"
        )
        
        if not bewerbung:
            return {"success": False, "error": "Bewerbung nicht gefunden oder bereits bearbeitet"}

        try:
            user = await self.bot.fetch_user(applicant_id)
            
            # Sende Ablehnungs-DM
            dm_embed = discord.Embed(
                title="📋 Bewerbung bearbeitet",
                description=(
                    f"Hallo {user.name},\n\n"
                    "leider müssen wir dir mitteilen, dass deine Bewerbung "
                    "zu diesem Zeitpunkt nicht angenommen werden konnte.\n\n"
                    "Du kannst dich gerne zu einem späteren Zeitpunkt erneut bewerben.\n\n"
                    "Vielen Dank für dein Interesse!"
                ),
                color=discord.Color.red()
            )
            
            if reason:
                dm_embed.add_field(name="📝 Begründung", value=reason, inline=False)
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # DM konnte nicht gesendet werden

        # Aktualisiere Status
        await self._execute_query("""
            UPDATE bewerbungen 
            SET status = 'rejected', processed_by = %s, processed_at = NOW() 
            WHERE user_id = %s
        """, (interaction.user.id, applicant_id))

        return {"success": True}

    async def archive_ticket(self, channel: discord.TextChannel):
        """
        Archiviert ein Bewerbungsticket
        """
        guild = channel.guild
        archive_category = guild.get_channel(ARCHIVE_KATEGORIE_ID)
        
        if archive_category and isinstance(archive_category, discord.CategoryChannel):
            await channel.edit(category=archive_category, reason="Bewerbung archiviert")
        
        # Entferne Berechtigungen für den Bewerber
        overwrites = channel.overwrites
        for target, overwrite in overwrites.items():
            if isinstance(target, discord.Member):
                overwrite.read_messages = False
                overwrite.send_messages = False
                await channel.set_permissions(target, overwrite=overwrite)

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Überwacht Nachrichten für Namen-Eingabe in Bewerbungstickets
        """
        # Ignoriere Bot-Nachrichten
        if message.author.bot:
            return
            
        # Prüfe ob es ein Bewerbungsticket ist
        if not message.channel.name.startswith('ticket-'):
            return
            
        # Prüfe ob User auf Namenseingabe wartet
        bewerbung = await self._execute_query(
            "SELECT * FROM bewerbungen WHERE user_id = %s AND ticket_channel_id = %s AND status = 'pending' AND real_name IS NULL",
            (message.author.id, message.channel.id), fetch="one"
        )
        
        if not bewerbung:
            return
            
        # Validiere den Namen (nur Buchstaben und Leerzeichen)
        import re
        name = message.content.strip()
        if not re.match(r'^[a-zA-ZäöüÄÖÜß\s]{2,50}$', name):
            embed = discord.Embed(
                title="❌ Ungültiger Name",
                description=(
                    "Bitte gib einen gültigen Namen ein:\n"
                    "• Nur Buchstaben und Leerzeichen\n"
                    "• 2-50 Zeichen lang\n"
                    "• Beispiel: `Max Mustermann`"
                ),
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
            return
            
        # Namen in DB speichern
        result = await self.update_bewerbung_with_name(message.author.id, name)
        
        if result.get("success"):
            # Bestätige Namen
            confirm_embed = discord.Embed(
                title="✅ Name gespeichert",
                description=f"Danke **{name}**! Deine Bewerbung wird nun an unser HR-Team weitergeleitet.",
                color=discord.Color.green()
            )
            await message.channel.send(embed=confirm_embed)
            
            # Direkt an HR weiterleiten - Hole User und erstelle HR-Embed
            user = message.author
            
            # Hole aktuelle Bewerbung mit Namen
            bewerbung = await self._execute_query(
                "SELECT * FROM bewerbungen WHERE user_id = %s AND status = 'pending'",
                (user.id,), fetch="one"
            )
            
            if bewerbung:
                # Erstelle vereinfachtes HR-Embed (nur mit Namen)
                await self._send_hr_review_embed(message.channel, user, bewerbung)
        else:
            error_embed = discord.Embed(
                title="❌ Fehler",
                description=f"Es gab einen Fehler: {result.get('error', 'Unbekannt')}",
                color=discord.Color.red()
            )
            await message.channel.send(embed=error_embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Behandelt neue Mitglieder und prüft auf ausstehende Einstellungen
        Reagiert nur auf Beitritte zum INTERNEN Server
        """
        print(f"[BewerbungsService] Member join detected: {member.name} on server {member.guild.name} (ID: {member.guild.id})")
        
        # Prüfe nur Beitritte zum INTERNEN Server
        if member.guild.id != INTERNAL_SERVER_ID:
            print(f"[BewerbungsService] Ignoring join - not internal server (Expected: {INTERNAL_SERVER_ID}, Got: {member.guild.id})")
            return
            
        print(f"[BewerbungsService] Processing internal server join for {member.name}")
            
        # Prüfe auf ausstehende Einstellung
        pending = await self._execute_query("""
            SELECT ph.*, b.real_name FROM pending_hires ph
            LEFT JOIN bewerbungen b ON ph.user_id = b.user_id
            WHERE ph.user_id = %s AND ph.target_server_id = %s AND ph.expires_at > NOW()
        """, (member.id, INTERNAL_SERVER_ID), fetch="one")
        
        if not pending:
            print(f"[BewerbungsService] No pending hire found for {member.name}")
            return

        print(f"[BewerbungsService] Found pending hire for {member.name}: {pending}")

        # Hole PersonalService
        personal_service: PersonalService = self.bot.get_cog("PersonalService")
        if not personal_service:
            print(f"[BewerbungsService] PersonalService nicht verfügbar für automatische Einstellung von {member.name}")
            return

        print(f"[BewerbungsService] PersonalService found: {personal_service}")

        # Hole Rang-Rolle vom INTERNEN Server
        rank_role = member.guild.get_role(pending['rank_role_id'])
        if not rank_role:
            print(f"[BewerbungsService] Rang-Rolle {pending['rank_role_id']} nicht gefunden auf internem Server")
            return

        print(f"[BewerbungsService] Rank role found: {rank_role.name}")

        # Stelle automatisch ein (auf INTERNEM Server)
        einstellungsgrund = f"Automatische Einstellung nach akzeptierter Bewerbung - {pending.get('acceptance_reason', 'Grund nicht angegeben')}"
        
        print(f"[BewerbungsService] Attempting to hire {member.name} with reason: {einstellungsgrund}")
        
        try:
            result = await personal_service.hire_member(
                member.guild,  # Interner Server
                member,
                pending['real_name'] or member.name,
                rank_role,
                einstellungsgrund
            )
            
            print(f"[BewerbungsService] Hire result: {result}")

            if result.get("success"):
                # Sende Einstellungsbenachrichtigung (auf INTERNEM Server)
                await self._send_einstellungs_notification(member, pending, result)
                
                # Lösche pending hire
                await self._execute_query("DELETE FROM pending_hires WHERE user_id = %s", (member.id,))
                
                # Update Bewerbungsstatus
                await self._execute_query("""
                    UPDATE bewerbungen SET status = 'accepted' WHERE user_id = %s
                """, (member.id,))
                
                print(f"[BewerbungsService] {member.name} wurde automatisch auf internem Server eingestellt")
                
                # Sende Bestätigung an HR auf öffentlichem Server
                if invited_by_id := pending.get('invited_by'):
                    try:
                        invited_by = await self.bot.fetch_user(invited_by_id)
                        await invited_by.send(f"✅ {member.name} ist dem internen Server beigetreten und wurde automatisch eingestellt!")
                    except Exception as e:
                        print(f"[BewerbungsService] Konnte Bestätigung nicht senden: {e}")
            else:
                print(f"[BewerbungsService] Automatische Einstellung fehlgeschlagen für {member.name}: {result.get('error', 'Unbekannter Fehler')}")
                
        except Exception as e:
            print(f"[BewerbungsService] Exception during hire process: {e}")
            import traceback
            traceback.print_exc()

    async def _send_einstellungs_notification(self, member: discord.Member, pending_data: dict, hire_result: dict):
        """
        Sendet eine Benachrichtigung über die erfolgreiche Einstellung (nur auf INTERNEM Server)
        """
        # Hole display_service für konsistente Namen
        display_service = self.bot.get_cog("DisplayService")
        if display_service:
            display_name = await display_service.get_display(member)
        else:
            display_name = member.mention
        
        # Hole den HR-User der die Bewerbung angenommen hat
        invited_by_user = None
        try:
            if pending_data.get('invited_by'):
                invited_by_user = await self.bot.fetch_user(pending_data['invited_by'])
        except:
            pass
        
        # Erstelle Einstellungs-Embed
        embed = discord.Embed(
            title="🆕 Neues Mitglied eingestellt",
            description=f"**{display_name} wurde erfolgreich als {hire_result['rank_role'].mention} eingestellt.**",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="👤 Name", value=pending_data['real_name'], inline=True)
        embed.add_field(name="🏷️ Dienstnummer", value=f"`{hire_result['dn']}`", inline=True)
        embed.add_field(name="📂 Division", value=f"<@&{hire_result['division_id']}>", inline=True)
        
        if pending_data.get('acceptance_reason'):
            embed.add_field(name="💬 Annahmegrund", value=pending_data['acceptance_reason'], inline=False)
        
        if invited_by_user:
            embed.add_field(name="👨‍💼 Angenommen von", value=invited_by_user.mention, inline=True)
        
        embed.add_field(name="📋 Quelle", value="Bewerbung über Ticketsystem (Öffentlicher Server)", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"U.S. ARMY Recruitment • User ID: {member.id}")
        
        # Sende Benachrichtigungen auf INTERNEM Server
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        if not internal_guild:
            return
            
        channels_to_notify = []
        
        # Einstellungskanal (falls konfiguriert)
        if einstellungs_channel := internal_guild.get_channel(INTERNAL_EINSTELLUNGS_CHANNEL_ID):
            channels_to_notify.append(einstellungs_channel)
        
        # Personal-Kanal auf internem Server
        if personal_channel := internal_guild.get_channel(INTERNAL_PERSONAL_CHANNEL_ID):
            channels_to_notify.append(personal_channel)
        
        for channel in channels_to_notify:
            try:
                await channel.send(content=display_name, embed=embed)
            except Exception as e:
                print(f"[BewerbungsService] Konnte Einstellungsbenachrichtigung nicht senden: {e}")
        embed.set_footer(text=f"U.S. ARMY Recruitment • User ID: {member.id}")
        
        # Sende Benachrichtigungen auf INTERNEM Server
        internal_guild = self.bot.get_guild(INTERNAL_SERVER_ID)
        if not internal_guild:
            return
            
        channels_to_notify = []
        
        # Einstellungskanal (falls konfiguriert)
        if einstellungs_channel := internal_guild.get_channel(INTERNAL_EINSTELLUNGS_CHANNEL_ID):
            channels_to_notify.append(einstellungs_channel)
        
        # Personal-Kanal auf internem Server
        if personal_channel := internal_guild.get_channel(INTERNAL_PERSONAL_CHANNEL_ID):
            channels_to_notify.append(personal_channel)
        
        for channel in channels_to_notify:
            try:
                await channel.send(content=display_name, embed=embed)
            except Exception as e:
                print(f"[BewerbungsService] Konnte Einstellungsbenachrichtigung nicht senden: {e}")


# --- UI Views ---
class BewerbungsView(discord.ui.View):
    """View mit Buttons für Bewerbungsbearbeitung"""
    
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    @discord.ui.button(label="✅ Annehmen", style=discord.ButtonStyle.success, custom_id="accept_application")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prüfe HR-Berechtigung
        if not self._has_hr_permission(interaction.user):
            return await interaction.response.send_message("❌ Du hast keine Berechtigung, Bewerbungen zu bearbeiten.", ephemeral=True)
        
        # Sende Modal für Grund-Eingabe
        await interaction.response.send_modal(AcceptModal(self.applicant_id))

    @discord.ui.button(label="❌ Ablehnen", style=discord.ButtonStyle.danger, custom_id="reject_application")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prüfe HR-Berechtigung
        if not self._has_hr_permission(interaction.user):
            return await interaction.response.send_message("❌ Du hast keine Berechtigung, Bewerbungen zu bearbeiten.", ephemeral=True)
            
        await interaction.response.send_modal(RejectModal(self.applicant_id))

    @discord.ui.button(label="📁 Archivieren", style=discord.ButtonStyle.secondary, custom_id="archive_application")
    async def archive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prüfe HR-Berechtigung
        if not self._has_hr_permission(interaction.user):
            return await interaction.response.send_message("❌ Du hast keine Berechtigung, Bewerbungen zu bearbeiten.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        # Update Embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.light_grey()
        embed.title = "📁 Bewerbung archiviert"
        embed.add_field(name="📋 Status", value=f"Archiviert von {interaction.user.mention}", inline=False)
        
        # Deaktiviere Buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("📁 Bewerbung archiviert", ephemeral=True)
        
        # Archiviere Ticket
        await service.archive_ticket(interaction.channel)
    
    def _has_hr_permission(self, user: discord.Member) -> bool:
        """Prüft ob User HR-Berechtigung hat"""
        # Prüfe auf Administrator
        if user.guild_permissions.administrator:
            return True
            
        # Prüfe auf HR-Rolle
        hr_role_id = HR_ROLE_ID  # Management Role ID
        if any(role.id == hr_role_id for role in user.roles):
            return True
            
        # Prüfe auf bewerbung.verwalten Permission (falls PermissionService vorhanden)
        try:
            from services.permission_service import PermissionService
            bot = user._state._get_client()  # Hacky way to get bot
            permission_service = bot.get_cog("PermissionService")
            if permission_service and permission_service.has_permission(user, "bewerbung.verwalten"):
                return True
        except:
            pass
            
        return False


class AcceptModal(discord.ui.Modal, title="Bewerbung annehmen"):
    """Modal für Annahmegrund"""
    
    reason = discord.ui.TextInput(
        label="Grund der Annahme",
        style=discord.TextStyle.paragraph,
        placeholder="Warum wird diese Bewerbung angenommen? (z.B. 'Sehr gute Motivation und Erfahrung')",
        required=True,
        max_length=500
    )
    
    def __init__(self, applicant_id: int):
        super().__init__()
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        result = await service.accept_bewerbung(interaction, self.applicant_id, self.reason.value)
        
        if result.get("success"):
            # Update Embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ Bewerbung angenommen"
            embed.add_field(name="📋 Status", value=f"Angenommen von {interaction.user.mention}", inline=False)
            embed.add_field(name="💬 Grund", value=self.reason.value, inline=False)
            embed.add_field(name="🔗 Einladung", value="Einladung zum internen Server versendet", inline=False)
            
            # Deaktiviere Buttons
            view = BewerbungsView(self.applicant_id)
            for item in view.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=view)
            
            if result.get("dm_failed"):
                await interaction.followup.send(
                    f"✅ Bewerbung angenommen!\n"
                    f"⚠️ DM konnte nicht gesendet werden. Einladungslink zum internen Server: {result['invite_url']}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send("✅ Bewerbung angenommen und Einladung zum internen Server versendet!", ephemeral=True)
                
            # Archiviere Ticket nach kurzer Verzögerung
            await asyncio.sleep(5)
            await service.archive_ticket(interaction.channel)
            
        else:
            await interaction.followup.send(f"❌ Fehler: {result['error']}", ephemeral=True)


class RejectModal(discord.ui.Modal, title="Bewerbung ablehnen"):
    """Modal für Ablehnungsgrund"""
    
    reason = discord.ui.TextInput(
        label="Grund (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Begründung für die Ablehnung...",
        required=False,
        max_length=1000
    )
    
    def __init__(self, applicant_id: int):
        super().__init__()
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        result = await service.reject_bewerbung(interaction, self.applicant_id, self.reason.value)
        
        if result.get("success"):
            # Update Embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "❌ Bewerbung abgelehnt"
            embed.add_field(name="📋 Status", value=f"Abgelehnt von {interaction.user.mention}", inline=False)
            
            if self.reason.value:
                embed.add_field(name="📝 Grund", value=self.reason.value, inline=False)
            
            # Deaktiviere Buttons
            view = BewerbungsView(self.applicant_id)
            for item in view.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send("❌ Bewerbung abgelehnt", ephemeral=True)
            
            # Archiviere Ticket nach kurzer Verzögerung
            await asyncio.sleep(5)
            await service.archive_ticket(interaction.channel)
        else:
            await interaction.followup.send(f"❌ Fehler: {result['error']}", ephemeral=True)


async def setup(bot: "MyBot"):
    # Erstelle die pending_hires Tabelle mit target_server_id
    pool: aiomysql.Pool = bot.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_hires (
                    user_id BIGINT PRIMARY KEY,
                    real_name VARCHAR(255) NOT NULL,
                    invite_code VARCHAR(50) NOT NULL,
                    rank_role_id BIGINT NOT NULL,
                    invited_by BIGINT NOT NULL,
                    acceptance_reason TEXT,
                    target_server_id BIGINT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL
                )
            """)
    
    await bot.add_cog(BewerbungsService(bot))


# --- UI Views ---
class BewerbungsFormularView(discord.ui.View):
    """View mit Button zum Ausfüllen der Bewerbung"""
    
    def __init__(self, user_id: int):
        super().__init__(timeout=300)  # 5 Minuten Timeout
        self.user_id = user_id

    @discord.ui.button(label="📝 Bewerbung ausfüllen", style=discord.ButtonStyle.primary)
    async def fill_application_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Das ist nicht dein Bewerbungsticket.", ephemeral=True)
            
        await interaction.response.send_modal(BewerbungsModal(self.user_id))

    async def on_timeout(self):
        """Deaktiviere Button nach Timeout"""
        for item in self.children:
            item.disabled = True


class BewerbungsView(discord.ui.View):
    """View mit Buttons für Bewerbungsbearbeitung"""
    
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    @discord.ui.button(label="✅ Annehmen", style=discord.ButtonStyle.success, custom_id="accept_application")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Sende Modal für Grund-Eingabe
        await interaction.response.send_modal(AcceptModal(self.applicant_id))

    @discord.ui.button(label="❌ Ablehnen", style=discord.ButtonStyle.danger, custom_id="reject_application")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RejectModal(self.applicant_id))

    @discord.ui.button(label="📁 Archivieren", style=discord.ButtonStyle.secondary, custom_id="archive_application")
    async def archive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        # Update Embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.light_grey()
        embed.title = "📁 Bewerbung archiviert"
        embed.add_field(name="📋 Status", value=f"Archiviert von {interaction.user.mention}", inline=False)
        
        # Deaktiviere Buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("📁 Bewerbung archiviert", ephemeral=True)
        
        # Archiviere Ticket
        await service.archive_ticket(interaction.channel)


class AcceptModal(discord.ui.Modal, title="Bewerbung annehmen"):
    """Modal für Annahmegrund"""
    
    reason = discord.ui.TextInput(
        label="Grund der Annahme",
        style=discord.TextStyle.paragraph,
        placeholder="Warum wird diese Bewerbung angenommen? (z.B. 'Sehr gute Motivation und Erfahrung')",
        required=True,
        max_length=500
    )
    
    def __init__(self, applicant_id: int):
        super().__init__()
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        result = await service.accept_bewerbung(interaction, self.applicant_id, self.reason.value)
        
        if result.get("success"):
            # Update Embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ Bewerbung angenommen"
            embed.add_field(name="📋 Status", value=f"Angenommen von {interaction.user.mention}", inline=False)
            embed.add_field(name="💬 Grund", value=self.reason.value, inline=False)
            
            # Deaktiviere Buttons
            view = BewerbungsView(self.applicant_id)
            for item in view.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=view)
            
            if result.get("dm_failed"):
                await interaction.followup.send(
                    f"✅ Bewerbung angenommen!\n"
                    f"⚠️ DM konnte nicht gesendet werden. Einladungslink: {result['invite_url']}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send("✅ Bewerbung angenommen und Einladung versendet!", ephemeral=True)
                
            # Archiviere Ticket nach kurzer Verzögerung
            await asyncio.sleep(5)
            await service.archive_ticket(interaction.channel)
            
        else:
            await interaction.followup.send(f"❌ Fehler: {result['error']}", ephemeral=True)


class RejectModal(discord.ui.Modal, title="Bewerbung ablehnen"):
    """Modal für Ablehnungsgrund"""
    
    reason = discord.ui.TextInput(
        label="Grund (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Begründung für die Ablehnung...",
        required=False,
        max_length=1000
    )
    
    def __init__(self, applicant_id: int):
        super().__init__()
        self.applicant_id = applicant_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ BewerbungsService nicht verfügbar", ephemeral=True)
        
        result = await service.reject_bewerbung(interaction, self.applicant_id, self.reason.value)
        
        if result.get("success"):
            # Update Embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "❌ Bewerbung abgelehnt"
            embed.add_field(name="📋 Status", value=f"Abgelehnt von {interaction.user.mention}", inline=False)
            
            if self.reason.value:
                embed.add_field(name="📝 Grund", value=self.reason.value, inline=False)
            
            # Deaktiviere Buttons
            view = BewerbungsView(self.applicant_id)
            for item in view.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send("❌ Bewerbung abgelehnt", ephemeral=True)
            
            # Archiviere Ticket nach kurzer Verzögerung
            await asyncio.sleep(5)
            await service.archive_ticket(interaction.channel)
        else:
            await interaction.followup.send(f"❌ Fehler: {result['error']}", ephemeral=True)


class BewerbungsModal(discord.ui.Modal, title="U.S. ARMY Bewerbung"):
    """Modal für die Bewerbungseingabe"""
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
    
    age = discord.ui.TextInput(
        label="Alter",
        style=discord.TextStyle.short,
        placeholder="Dein Alter in Jahren...",
        required=True,
        max_length=3
    )
    
    motivation = discord.ui.TextInput(
        label="Motivation",
        style=discord.TextStyle.paragraph,
        placeholder="Warum möchtest du der U.S. ARMY beitreten? Was motiviert dich?",
        required=True,
        max_length=1000
    )
    
    experience = discord.ui.TextInput(
        label="Erfahrung (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Hast du bereits Erfahrung in ähnlichen Communities/Gaming/Roleplay?",
        required=False,
        max_length=500
    )
    
    availability = discord.ui.TextInput(
        label="Verfügbarkeit",
        style=discord.TextStyle.short,
        placeholder="Wann bist du normalerweise online? (z.B. Wochenende, Abends...)",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Validiere Alter
        try:
            age_int = int(self.age.value)
            if age_int < 16 or age_int > 100:
                return await interaction.followup.send("❌ Bitte gib ein gültiges Alter zwischen 16 und 100 Jahren an.", ephemeral=True)
        except ValueError:
            return await interaction.followup.send("❌ Bitte gib dein Alter als Zahl an.", ephemeral=True)
        
        service: BewerbungsService = interaction.client.get_cog("BewerbungsService")
        if not service:
            return await interaction.followup.send("❌ Bewerbungsservice nicht verfügbar.", ephemeral=True)
        
        bewerbung_data = {
            "age": age_int,
            "motivation": self.motivation.value.strip(),
            "experience": self.experience.value.strip() if self.experience.value else "",
            "availability": self.availability.value.strip()
        }
        
        result = await service.complete_bewerbung(self.user_id, bewerbung_data)
        
        if result.get("success"):
            # Deaktiviere den Button
            view = discord.ui.View()
            button = discord.ui.Button(label="📝 Bewerbung eingereicht", style=discord.ButtonStyle.success, disabled=True)
            view.add_item(button)
            
            try:
                await interaction.message.edit(view=view)
            except:
                pass
            
            embed = discord.Embed(
                title="✅ Bewerbung vollständig!",
                description=(
                    "Deine Bewerbung wurde erfolgreich eingereicht und ist nun vollständig!\n\n"
                    "📋 **Nächste Schritte:**\n"
                    "• Deine Bewerbung wird vom HR-Team geprüft\n"
                    "• Du erhältst eine Benachrichtigung über die Entscheidung\n"
                    "• Bei Fragen kannst du hier im Ticket schreiben\n\n"
                    "⏰ **Bearbeitungszeit:** In der Regel 1-2 Werktage"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Bestätigungsnachricht für alle
            confirm_embed = discord.Embed(
                title="📝 Bewerbung eingereicht",
                description=f"{interaction.user.mention} hat die Bewerbung vollständig ausgefüllt!",
                color=discord.Color.blue()
            )
            await interaction.channel.send(embed=confirm_embed)
            
        else:
            await interaction.followup.send(f"❌ **Fehler:** {result.get('error', 'Unbekannter Fehler')}", ephemeral=True)


async def setup(bot: "MyBot"):
    # Erstelle auch die pending_hires Tabelle mit acceptance_reason
    pool: aiomysql.Pool = bot.db_pool
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_hires (
                    user_id BIGINT PRIMARY KEY,
                    real_name VARCHAR(255) NOT NULL,
                    invite_code VARCHAR(50) NOT NULL,
                    rank_role_id BIGINT NOT NULL,
                    invited_by BIGINT NOT NULL,
                    acceptance_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL
                )
            """)
    
    await bot.add_cog(BewerbungsService(bot))
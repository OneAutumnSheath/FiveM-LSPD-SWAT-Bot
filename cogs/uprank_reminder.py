import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
import asyncio
from utils.decorators import has_permission, log_on_completion

class UprankReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Konfiguration - Diese Werte anpassen!
        # Format: Channel ID : Rollen ID (OHNE Division 1 - die bekommt keine Uprank-Fristen)
        self.channel_role_pairs = {
            1306741664127258644: 1269229762400878675, # Airforce
            1306741178321997846: 1289716541658497055, # MP
            1306740612556525650: 1187756956425920645, # Infantry
            1306741410455752805: 1136062113908019250, # Marine
            1306739715826782340: 1097625910242447422, # HR
            1306741836567679036: 1125174901989445693, # SEALS
            1306740165242392619: 1097648131367248016, # EDUCATION
            1335699215405420544: 1339523576159666218 # SOC
            # Weitere Channel:Rolle Paare hier hinzufügen (Division 1 NICHT hier eintragen!)
        }
        
        # Leitungsebene (Division 1) Konfiguration - separate Behandlung
        self.division1_channel_id = 1097626041083756604  # Channel ID für Division 1
        self.division1_role_id = 1097650390230630580     # Division 1 Rolle ID
        
        # Task starten, wenn der Bot bereit ist
        self.uprank_reminder_task.start()
    
    def cog_unload(self):
        """Stoppt den Task beim Entladen des Cogs"""
        self.uprank_reminder_task.cancel()
    
    @tasks.loop(hours=24)
    async def uprank_reminder_task(self):
        """Läuft täglich und prüft, ob es Freitag 12:00 oder Sonntag 12:00 ist"""
        now = datetime.now(timezone.utc)
        
        # Prüfen ob es Freitag 12:00 ist (4 = Freitag in Python)
        if now.weekday() == 4 and now.hour == 12:
            await self.send_uprank_reminders()
            await self.send_division1_voting_reminder()
        
        # Prüfen ob es Sonntag 12:00 ist (6 = Sonntag in Python)
        elif now.weekday() == 6 and now.hour == 12:
            await self.send_sunday_reminders()
            await self.send_division1_sunday_reminder()
    
    @uprank_reminder_task.before_loop
    async def before_uprank_reminder_task(self):
        """Wartet bis der Bot bereit ist"""
        await self.bot.wait_until_ready()
    
    async def send_uprank_reminders(self):
        """Sendet die Uprank-Erinnerungen in die konfigurierten Channels (OHNE Division 1)"""
        # Berechne nächsten Sonntag 17:00 UTC
        now = datetime.now(timezone.utc)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 17:
            # Falls es bereits Sonntag nach 17:00 ist, nächsten Sonntag nehmen
            days_until_sunday = 7
        
        next_sunday = now + timedelta(days=days_until_sunday)
        deadline = next_sunday.replace(hour=17, minute=0, second=0, microsecond=0)
        
        # Timestamp für Discord erstellen
        timestamp = int(deadline.timestamp())
        
        # Nachrichten für jeden Channel mit der entsprechenden Rolle senden (Division 1 ausgeschlossen)
        for channel_id, role_id in self.channel_role_pairs.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                message = f"<@&{role_id}> | Die Uprank-Frist endet <t:{timestamp}:R>."
                
                try:
                    await channel.send(message)
                    print(f"Uprank-Erinnerung gesendet in Channel: {channel.name} für Rolle: {role_id}")
                except discord.Forbidden:
                    print(f"Keine Berechtigung zum Senden in Channel: {channel.name}")
                except Exception as e:
                    print(f"Fehler beim Senden der Nachricht in {channel.name}: {e}")
            else:
                print(f"Channel mit ID {channel_id} nicht gefunden")
    
    async def send_division1_voting_reminder(self):
        """Sendet die Abstimmungs-Erinnerung für Division 1 (Freitag 12:00)"""
        channel = self.bot.get_channel(self.division1_channel_id)
        if channel:
            message = f"<@&{self.division1_role_id}> | ABSTIMMEN NICHT VERGESSEN"
            
            try:
                await channel.send(message)
                print(f"Division 1 Abstimmungs-Erinnerung gesendet in Channel: {channel.name}")
            except discord.Forbidden:
                print(f"Keine Berechtigung zum Senden in Channel: {channel.name}")
            except Exception as e:
                print(f"Fehler beim Senden der Division 1 Abstimmungs-Nachricht: {e}")
        else:
            print(f"Division 1 Channel mit ID {self.division1_channel_id} nicht gefunden")
    
    async def send_sunday_reminders(self):
        """Sendet die Sonntag-Reminder für alle Rollen (Sonntag 12:00)"""
        for channel_id, role_id in self.channel_role_pairs.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                message = f"<@&{role_id}> | REMINDER!"
                
                try:
                    await channel.send(message)
                    print(f"Sonntag-Reminder gesendet in Channel: {channel.name} für Rolle: {role_id}")
                except discord.Forbidden:
                    print(f"Keine Berechtigung zum Senden in Channel: {channel.name}")
                except Exception as e:
                    print(f"Fehler beim Senden des Sonntag-Reminders in {channel.name}: {e}")
            else:
                print(f"Channel mit ID {channel_id} nicht gefunden")
    
    async def send_division1_sunday_reminder(self):
        """Sendet den Sonntag-Reminder für Division 1 (Sonntag 12:00)"""
        channel = self.bot.get_channel(self.division1_channel_id)
        if channel:
            message = f"<@&{self.division1_role_id}> | REMINDER!"
            
            try:
                await channel.send(message)
                print(f"Division 1 Sonntag-Reminder gesendet in Channel: {channel.name}")
            except discord.Forbidden:
                print(f"Keine Berechtigung zum Senden in Channel: {channel.name}")
            except Exception as e:
                print(f"Fehler beim Senden des Division 1 Sonntag-Reminders: {e}")
        else:
            print(f"Division 1 Channel mit ID {self.division1_channel_id} nicht gefunden")
    
    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================
    
    @app_commands.command(name="test-uprank", description="Testet alle Freitag-Nachrichten")
    @app_commands.describe()
    @has_permission('uprankreminder.test')
    @log_on_completion
    async def test_uprank_reminder(self, interaction: discord.Interaction):
        """Testbefehl um alle Freitag-Nachrichten sofort zu senden"""
        await interaction.response.defer(ephemeral=True)
        
        await self.send_uprank_reminders()  # Nur normale Rollen, NICHT Division 1
        await self.send_division1_voting_reminder()  # Nur Abstimmungs-Erinnerung für Division 1
        
        await interaction.followup.send("✅ Freitag-Test durchgeführt: Uprank-Fristen für normale Rollen + Abstimmungs-Erinnerung für Division 1!", ephemeral=True)
    
    @app_commands.command(name="test-sunday", description="Testet alle Sonntag-Reminder")
    @app_commands.describe()
    @has_permission('uprankreminder.test')
    @log_on_completion
    async def test_sunday_reminder(self, interaction: discord.Interaction):
        """Testbefehl um alle Sonntag-Reminder sofort zu senden"""
        await interaction.response.defer(ephemeral=True)
        
        await self.send_sunday_reminders()
        await self.send_division1_sunday_reminder()
        
        await interaction.followup.send("✅ Sonntag-Reminder Test durchgeführt!", ephemeral=True)
    
    @app_commands.command(name="next-uprank", description="Zeigt die nächste Uprank-Frist an")
    @app_commands.describe()
    @log_on_completion
    async def next_uprank_deadline(self, interaction: discord.Interaction):
        """Zeigt an, wann die nächste Uprank-Frist ist"""
        now = datetime.now(timezone.utc)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 17:
            days_until_sunday = 7
        
        next_sunday = now + timedelta(days=days_until_sunday)
        deadline = next_sunday.replace(hour=17, minute=0, second=0, microsecond=0)
        timestamp = int(deadline.timestamp())
        
        await interaction.response.send_message(f"📅 Die nächste Uprank-Frist endet <t:{timestamp}:R>.", ephemeral=True)

async def setup(bot):
    """Setup-Funktion für das Cog"""
    await bot.add_cog(UprankReminder(bot))
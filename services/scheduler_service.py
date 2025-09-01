# bot/services/scheduler_service.py

import discord
from discord.ext import commands, tasks
import yaml
from datetime import datetime, time
from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from main import MyBot

class SchedulerService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "SchedulerService"
        self.config = self._load_config()
        # Verhindert, dass eine Nachricht mehrmals am selben Tag gesendet wird
        self.last_sent_dates = {}

    def _load_config(self) -> List[Dict[str, Any]]:
        try:
            with open('config/scheduler_config.yaml', 'r', encoding='utf-8') as f:
                # Wir wollen nur die Liste der Nachrichten
                return yaml.safe_load(f).get('scheduled_messages', [])
        except FileNotFoundError:
            print("FATAL: config/scheduler_config.yaml nicht gefunden.")
            return []

    def cog_load(self):
        self.message_scheduler_task.start()
        print("Scheduler-Service geladen und Task gestartet.")

    def cog_unload(self):
        self.message_scheduler_task.cancel()

    @tasks.loop(minutes=1)
    async def message_scheduler_task(self):
        """Überprüft jede Minute, ob eine Nachricht gesendet werden soll."""
        now = datetime.now()
        today = now.date()

        for task in self.config:
            if not task.get('enabled', False):
                continue

            task_name = task.get('name')
            scheduled_day = task.get('day_of_week')
            
            try:
                # Konvertiere die Zeitangabe aus der Config in ein time-Objekt
                scheduled_time_obj = datetime.strptime(task.get('time'), '%H:%M').time()
            except (ValueError, TypeError):
                print(f"FEHLER im Scheduler: Ungültiges Zeitformat für Task '{task_name}'. Erwarte 'HH:MM'.")
                continue

            # Prüfe, ob heute der richtige Wochentag und die richtige Uhrzeit ist
            is_correct_day = now.weekday() == scheduled_day
            is_correct_time = now.hour == scheduled_time_obj.hour and now.minute == scheduled_time_obj.minute
            
            # Prüfe, ob für diesen Task heute schon gesendet wurde
            already_sent_today = self.last_sent_dates.get(task_name) == today

            if is_correct_day and is_correct_time and not already_sent_today:
                print(f"Sende geplante Nachricht für Task: '{task_name}'")
                channel_id = task.get('channel_id')
                message_content = task.get('message')
                
                if not channel_id or not message_content:
                    print(f"FEHLER im Scheduler: channel_id oder message für Task '{task_name}' fehlt.")
                    continue

                if channel := self.bot.get_channel(channel_id):
                    try:
                        await channel.send(message_content)
                        # Markiere, dass für heute gesendet wurde
                        self.last_sent_dates[task_name] = today
                    except discord.Forbidden:
                        print(f"FEHLER im Scheduler: Keine Berechtigung, in Kanal {channel_id} zu senden.")
                    except Exception as e:
                        print(f"FEHLER im Scheduler: Unerwarteter Fehler beim Senden: {e}")
                else:
                    print(f"FEHLER im Scheduler: Kanal {channel_id} für Task '{task_name}' nicht gefunden.")

    @message_scheduler_task.before_loop
    async def before_task(self):
        pass # Kein wait_until_ready, wie besprochen

async def setup(bot: "MyBot"):
    await bot.add_cog(SchedulerService(bot))
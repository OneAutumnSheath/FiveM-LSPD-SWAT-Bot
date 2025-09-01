import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import json
import aiomysql
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from main import MyBot
    from services.week_separation_service import WeekSeparationService

class TimerService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "TimerService"

    async def cog_load(self):
        await self._ensure_table_exists()
        self.check_timers_task.start()

    def cog_unload(self):
        self.check_timers_task.cancel()

    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": return await cursor.fetchone()
                if fetch == "all": return await cursor.fetchall()
    
    async def _ensure_table_exists(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                execute_at DATETIME NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                action_data JSON NOT NULL,
                created_by BIGINT NOT NULL,
                created_at DATETIME NOT NULL,
                guild_id BIGINT NOT NULL
            );
        """)

    async def schedule_task(self, execute_at: datetime, action_type: str, action_data: dict, creator: discord.User, guild: discord.Guild) -> int:
        query = "INSERT INTO scheduled_tasks (execute_at, action_type, action_data, created_by, created_at, guild_id) VALUES (%s, %s, %s, %s, %s, %s)"
        args = (execute_at, action_type, json.dumps(action_data), creator.id, datetime.now(timezone.utc), guild.id)
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                return cursor.lastrowid

    async def get_tasks_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        return await self._execute_query("SELECT * FROM scheduled_tasks WHERE created_by = %s AND execute_at > NOW() ORDER BY execute_at ASC", (user_id,), fetch="all")

    async def delete_task(self, task_id: int, user_id: int) -> bool:
        cursor = await self._execute_query("DELETE FROM scheduled_tasks WHERE id = %s AND created_by = %s", (task_id, user_id))
        return cursor is not None

    @tasks.loop(minutes=1)
    async def check_timers_task(self):
        due_tasks = await self._execute_query("SELECT * FROM scheduled_tasks WHERE execute_at <= NOW()", fetch="all")
        if not due_tasks: return

        ids_to_delete = []
        for task in due_tasks:
            ids_to_delete.append(task['id'])
            print(f"Führe geplante Aufgabe #{task['id']} aus: {task['action_type']}")
            try:
                if task['action_type'] == 'send_message':
                    await self._execute_send_message(task)
                elif task['action_type'] == 'wochentrennung':
                    await self._execute_wochentrennung(task)
            except Exception as e:
                print(f"Fehler bei der Ausführung von Aufgabe #{task['id']}: {e}")

        if ids_to_delete:
            format_strings = ','.join(['%s'] * len(ids_to_delete))
            await self._execute_query(f"DELETE FROM scheduled_tasks WHERE id IN ({format_strings})", tuple(ids_to_delete))

    @check_timers_task.before_loop
    async def before_check_timers(self):
        await self.bot.wait_until_ready()

    async def _execute_send_message(self, task: Dict[str, Any]):
        data = json.loads(task['action_data'])
        if channel := self.bot.get_channel(data.get('channel_id')):
            await channel.send(data.get('content'))
            
    async def _execute_wochentrennung(self, task: Dict[str, Any]):
        week_separation_service: WeekSeparationService = self.bot.get_cog("WeekSeparationService")
        if week_separation_service:
            data = json.loads(task['action_data'])
            target_channel_id = data.get('channel_id')
            target_channel = self.bot.get_channel(target_channel_id) if target_channel_id else None
            await week_separation_service.send_separation_message(target_channel=target_channel)
        else:
            print("[Timer] FEHLER: WeekSeparationService nicht gefunden.")

async def setup(bot: "MyBot"):
    await bot.add_cog(TimerService(bot))
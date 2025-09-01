import discord
from discord.ext import commands
from discord import app_commands, Interaction
from datetime import datetime
import json
from typing import TYPE_CHECKING, Optional
from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.timer_service import TimerService

class TimerCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    timer_group = app_commands.Group(name="timer", description="Verwaltet zeitgesteuerte Aktionen.")

    @timer_group.command(name="create", description="Plant eine zeitgesteuerte Aktion.")
    @app_commands.describe(
        wann="Zeitpunkt im Format TT.MM.JJJJ HH:MM",
        aktion="Die auszuführende Aktion",
        kanal="[Optional] Der Zielkanal für die Aktion",
        nachricht="[Nur für Nachricht] Der Text der Nachricht"
    )
    @app_commands.choices(aktion=[
        app_commands.Choice(name="Nachricht senden", value="send_message"),
        app_commands.Choice(name="Wochentrennung ausführen", value="wochentrennung"),
    ])
    @has_permission("timer.create")
    @log_on_completion
    async def create(self, interaction: Interaction, wann: str, aktion: app_commands.Choice[str], 
                     kanal: Optional[discord.TextChannel] = None, nachricht: str = None):
        await interaction.response.defer(ephemeral=True)
        
        try:
            execute_at = datetime.strptime(wann, "%d.%m.%Y %H:%M")
            if execute_at < datetime.now():
                return await interaction.followup.send("❌ Der Zeitpunkt muss in der Zukunft liegen.", ephemeral=True)
        except ValueError:
            return await interaction.followup.send("❌ Ungültiges Datumsformat. Bitte `TT.MM.JJJJ HH:MM` verwenden.", ephemeral=True)

        service: TimerService = self.bot.get_cog("TimerService")
        if not service: return await interaction.followup.send("Fehler: Timer-Service nicht gefunden.", ephemeral=True)
        
        action_data = {}
        if aktion.value == "send_message":
            if not kanal or not nachricht:
                return await interaction.followup.send("❌ Für 'Nachricht senden' musst du einen Kanal und eine Nachricht angeben.", ephemeral=True)
            action_data = {"channel_id": kanal.id, "content": nachricht}
        
        elif aktion.value == "wochentrennung":
            if kanal:
                action_data = {"channel_id": kanal.id}

        task_id = await service.schedule_task(execute_at, aktion.value, action_data, interaction.user, interaction.guild)
        
        await interaction.followup.send(f"✅ Aufgabe #{task_id} (`{aktion.name}`) erfolgreich geplant für den {wann} Uhr.", ephemeral=True)
    
    @timer_group.command(name="list", description="Listet deine geplanten Aktionen auf.")
    @has_permission("timer.list")
    @log_on_completion
    async def list_tasks(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        service: TimerService = self.bot.get_cog("TimerService")
        if not service: return await interaction.followup.send("Fehler: Timer-Service nicht gefunden.", ephemeral=True)

        tasks = await service.get_tasks_by_user(interaction.user.id)
        if not tasks:
            return await interaction.followup.send("Du hast keine anstehenden Aufgaben.", ephemeral=True)
        
        embed = discord.Embed(title="Deine geplanten Aufgaben", color=discord.Color.blue())
        desc = []
        for task in tasks:
            timestamp = int(task['execute_at'].timestamp())
            details = ""
            data = json.loads(task['action_data'])
            if task['action_type'] == 'send_message':
                details = f"Kanal: <#{data.get('channel_id')}>"
            elif task['action_type'] == 'wochentrennung':
                if channel_id := data.get('channel_id'):
                    details = f"Kanal: <#{channel_id}>"
                else:
                    details = "Kanäle: Standardliste"
            desc.append(f"**ID: {task['id']}** | <t:{timestamp}:F> | Aktion: `{task['action_type']}` | {details}")
        
        embed.description = "\n".join(desc)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @timer_group.command(name="delete", description="Löscht eine deiner geplanten Aktionen.")
    @app_commands.describe(task_id="Die ID der zu löschenden Aufgabe (siehe /timer list)")
    @has_permission("timer.delete")
    @log_on_completion
    async def delete_task(self, interaction: Interaction, task_id: int):
        await interaction.response.defer(ephemeral=True)
        service: TimerService = self.bot.get_cog("TimerService")
        if not service: return await interaction.followup.send("Fehler: Timer-Service nicht gefunden.", ephemeral=True)

        success = await service.delete_task(task_id, interaction.user.id)
        if success:
            await interaction.followup.send(f"✅ Aufgabe #{task_id} wurde erfolgreich gelöscht.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Aufgabe nicht gefunden oder du bist nicht der Ersteller.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(TimerCommands(bot))
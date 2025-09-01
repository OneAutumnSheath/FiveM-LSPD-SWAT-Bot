import discord
from discord import app_commands, Interaction
from typing import TYPE_CHECKING
import functools # <-- NEU: Import für den Wraps-Decorator

if TYPE_CHECKING:
    from main import MyBot
    from services.permission_service import PermissionService
    from services.log_service import LogService

# =========================================================================
# BERECHTIGUNGS-DECORATOR
# =========================================================================
def has_permission(permission_node: str):
    """
    Ein Check, der prüft, ob ein User die benötigte Berechtigung hat.
    """
    async def predicate(interaction: Interaction) -> bool:
        bot: MyBot = interaction.client
        permission_service: PermissionService = bot.get_cog("PermissionService")
        
        if not permission_service:
            print(f"WARNUNG: PermissionService nicht geladen. Berechtigung '{permission_node}' konnte nicht geprüft werden.")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Interner Fehler (PermissionService nicht gefunden).", ephemeral=True)
            return False

        if not permission_service.has_permission(interaction.user, permission_node):
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Du hast keine Berechtigung (`{permission_node}`), diesen Befehl auszuführen.", ephemeral=True)
            return False
            
        return True
    
    return app_commands.check(predicate)

# =========================================================================
# LOGGING-DECORATOR
# =========================================================================
def log_on_completion(func):
    """
    Ein Decorator, der nach erfolgreicher Ausführung eines Befehls
    automatisch den LogService aufruft.
    """
    @functools.wraps(func) # <-- NEU: Stellt sicher, dass die Befehls-Signatur erhalten bleibt
    async def wrapper(cog_instance, interaction: Interaction, *args, **kwargs):
        # Führe den eigentlichen Befehl aus
        await func(cog_instance, interaction, *args, **kwargs)

        # Hole den LogService und logge den Befehl nach erfolgreicher Ausführung
        log_service: LogService = cog_instance.bot.get_cog("LogService")
        if log_service:
            cog_instance.bot.loop.create_task(log_service.log_command(interaction))

    return wrapper
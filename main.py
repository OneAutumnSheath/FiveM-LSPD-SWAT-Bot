# main.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import os
import yaml
import asyncio
import aiomysql
from dotenv import load_dotenv
import traceback
import logging
from logging.handlers import RotatingFileHandler

# ===================================================
# LOGGING-SETUP
# ===================================================

TEMP_LOG_FILE = '/var/www/logs/bot_session.log'
LOG_DIR = os.path.dirname(TEMP_LOG_FILE)
os.makedirs(LOG_DIR, exist_ok=True)
try:
    os.chmod(LOG_DIR, 0o755)
except OSError as e:
    print(f"Warnung: Konnte Verzeichnisberechtigungen für '{LOG_DIR}' nicht setzen: {e}")
with open(TEMP_LOG_FILE, 'w', encoding='utf-8') as f:
    f.write(f"--- Neue Bot-Sitzung gestartet um {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
try:
    os.chmod(TEMP_LOG_FILE, 0o644)
except OSError as e:
    print(f"Warnung: Konnte Dateiberechtigungen für '{TEMP_LOG_FILE}' nicht setzen: {e}")

PERSISTENT_LOG_FILE = '/var/www/logs/bot_persistent.log'
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
persistent_handler = RotatingFileHandler(PERSISTENT_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
persistent_handler.setFormatter(log_formatter)
persistent_logger = logging.getLogger('MyBotPersistentLogger')
persistent_logger.setLevel(logging.INFO)
persistent_logger.addHandler(persistent_handler)

class Colors:
    RESET = '\033[0m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'

# ===================================================
# CONFIG-HANDLING
# ===================================================
config_dir = './config'
config_file = f'{config_dir}/config.yaml'

default_config = {
    'verbose': True,
    'maintenance_mode': False,
    'maintenance_whitelist': [],
    'disabled_commands': []
}

def load_config():
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            yaml.dump(default_config, f)
        print(f"Config-Datei nicht gefunden. Erstelle Standard-Config unter {config_file}")
        return default_config
    with open(config_file, 'r') as f:
        loaded = yaml.safe_load(f)
        for key, value in default_config.items():
            if key not in loaded:
                loaded[key] = value
        return loaded

def save_config(data):
    with open(config_file, 'w') as f:
        yaml.dump(data, f, indent=4)

# ===================================================
# EIGENE FEHLERKLASSE
# ===================================================
class MaintenanceModeActive(app_commands.CheckFailure):
    def __init__(self, message="Der Bot befindet sich aktuell in Wartungsarbeiten. Bitte versuche es später erneut."):
        super().__init__(message)

# ===================================================
# DIE ZENTRALE BOT-KLASSE
# ===================================================
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.config = load_config()
        self.verbose_logging = self.config.get('verbose', True)
        self.maintenance_mode = self.config.get('maintenance_mode', False)
        self.maintenance_whitelist = set(self.config.get('maintenance_whitelist', []))
        self.owner_id = 303698430998347777

        self.db_pool: aiomysql.Pool | None = None
        
        self.tree.interaction_check = self.global_interaction_check
        self.tree.add_command(wartung_group)
        self.tree.add_command(sperre_group) # Hinzugefügt
        self.tree.on_error = self.on_app_command_error

    def log(self, message, color=Colors.RESET, level='info'):
        """Erweiterte Log-Funktion, die in Konsole, temporäre und persistente Datei schreibt."""
        timestamp = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
        log_prefix = "[VERBOSE] " if self.verbose_logging else ""
        
        if self.verbose_logging:
            print(f"{color}{timestamp} {log_prefix}{message}{Colors.RESET}")

        try:
            clean_message = ''.join(char for char in message if 32 <= ord(char) <= 126 or char in '\n\r\t')
            final_log_line = f"{timestamp} {log_prefix}{clean_message}\n"
            with open(TEMP_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(final_log_line)
        except Exception as e:
            print(f"{Colors.RED}Konnte nicht in temporären Log schreiben: {e}{Colors.RESET}")

        if level == 'info':
            persistent_logger.info(message)
        elif level == 'warning':
            persistent_logger.warning(message)
        elif level == 'error':
            persistent_logger.error(message)

    async def setup_hook(self):
        self.log("setup_hook wird ausgeführt...", Colors.YELLOW)
        try:
            load_dotenv()
            self.db_pool = await aiomysql.create_pool(
                host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT")),
                user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                db=os.getenv("DB_NAME"), autocommit=True
            )
            self.log("Datenbank-Verbindungspool erfolgreich erstellt.", Colors.GREEN)
        except Exception as e:
            self.log(f"FATAL: Fehler beim Erstellen des DB-Pools: {e}", Colors.RED, level='error')
            await self.close()
            return

        self.log("Lade Cogs...", Colors.YELLOW)
        cog_folders_in_order = ['./services', './cogs']
        for folder in cog_folders_in_order:
            if not os.path.isdir(folder): continue
            for root, dirs, files in os.walk(folder):
                # --- START: NEUE AUSNAHME HINZUGEFÜGT ---
                # Überspringe den 'modules'-Ordner innerhalb von 'masscommands'
                if 'masscommands' in root and 'modules' in root.split(os.sep):
                    continue
                # --- ENDE: NEUE AUSNAHME HINZUGEFÜGT ---
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        rel_path = os.path.splitext(os.path.relpath(os.path.join(root, file), './'))[0]
                        module_path = rel_path.replace(os.sep, '.')
                        try:
                            await self.load_extension(module_path)
                            self.log(f"Cog '{module_path}' erfolgreich geladen.")
                        except Exception:
                            full_traceback = traceback.format_exc()
                            self.log(f"FEHLER beim Laden von '{module_path}':\n{full_traceback}", Colors.RED, level='error')
                            if folder == './prio_cogs':
                                self.log(f"FATAL: Kritischer Prio-Cog '{module_path}' konnte nicht geladen werden.", Colors.RED, level='error')
                                await self.close()
                                return
        try:
            await self.tree.sync()
            self.log("Globale Slash-Befehle erfolgreich synchronisiert!", Colors.GREEN)
        except Exception as e:
            self.log(f"Fehler bei der globalen Synchronisierung: {e}", Colors.RED, level='error')

    async def close(self):
        await super().close()
        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()
            self.log("Datenbank-Verbindungspool sauber geschlossen.", Colors.BLUE)
            
    async def on_ready(self):
        print(f"{Colors.GREEN}{'='*40}{Colors.RESET}")
        print(f"{Colors.GREEN}Bot ist bereit! Eingeloggt als {self.user} (ID: {self.user.id}){Colors.RESET}")
        status_color = Colors.RED if self.maintenance_mode else Colors.GREEN
        print(f"{status_color}Status: {'Wartungsmodus AKTIV' if self.maintenance_mode else 'Normalbetrieb'}{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*40}{Colors.RESET}")

    async def global_interaction_check(self, interaction: discord.Interaction) -> bool:
        """Globaler Check für jede Interaktion (Wartung & Befehlssperren)."""
        user_is_exempt = interaction.user.id == self.owner_id or interaction.user.id in self.maintenance_whitelist
        if self.maintenance_mode and not user_is_exempt:
            raise MaintenanceModeActive()

        if interaction.command is not None and not user_is_exempt:
            command_name = interaction.command.qualified_name
            if command_name in self.config['disabled_commands'] or \
               (interaction.command.parent is not None and interaction.command.parent.name in self.config['disabled_commands']):
                error_message = f"❌ Der Befehl `{command_name}` ist aktuell deaktiviert."
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_message, ephemeral=True)
                return False
        return True

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, MaintenanceModeActive):
            if not interaction.response.is_done():
                await interaction.response.send_message(str(error), ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nur der Bot-Inhaber darf diesen Befehl verwenden.", ephemeral=True)
        else:
            full_traceback = traceback.format_exc()
            self.log(f"Ein unbehandelter AppCommand-Fehler ist aufgetreten:\n{full_traceback}", Colors.RED, level='error')
            if not interaction.response.is_done():
                await interaction.response.send_message("Ein unerwarteter Fehler ist aufgetreten.", ephemeral=True)

# ===================================================
# WARTUNGSBEFEHLE
# ===================================================
wartung_group = app_commands.Group(name="wartung", description="Befehle zur Steuerung des Wartungsmodus.")
OWNER_ID_STATIC = 303698430998347777

@wartung_group.command(name="status", description="Schaltet den Wartungsmodus an oder aus.")
@app_commands.choices(modus=[app_commands.Choice(name="an", value="on"), app_commands.Choice(name="aus", value="off")])
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def wartung_status(interaction: discord.Interaction, modus: app_commands.Choice[str]):
    bot: MyBot = interaction.client
    new_status = (modus.value == "on")
    bot.maintenance_mode = new_status
    bot.config['maintenance_mode'] = new_status
    save_config(bot.config)
    await interaction.response.send_message(f"🔧 **Wartungsmodus wurde {'aktiviert' if new_status else 'deaktiviert'}.**", ephemeral=True)

@wartung_group.command(name="add", description="Fügt einen Nutzer zur Wartungs-Whitelist hinzu.")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def wartung_add(interaction: discord.Interaction, nutzer: discord.User):
    bot: MyBot = interaction.client
    if nutzer.id == bot.owner_id:
        await interaction.response.send_message("Du bist als Inhaber bereits permanent berechtigt.", ephemeral=True)
        return
    bot.maintenance_whitelist.add(nutzer.id)
    bot.config['maintenance_whitelist'] = list(bot.maintenance_whitelist)
    save_config(bot.config)
    await interaction.response.send_message(f"✅ {nutzer.mention} wurde zur Wartungs-Whitelist hinzugefügt.", ephemeral=True)

@wartung_group.command(name="remove", description="Entfernt einen Nutzer von der Wartungs-Whitelist.")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def wartung_remove(interaction: discord.Interaction, nutzer: discord.User):
    bot: MyBot = interaction.client
    if nutzer.id in bot.maintenance_whitelist:
        bot.maintenance_whitelist.remove(nutzer.id)
        bot.config['maintenance_whitelist'] = list(bot.maintenance_whitelist)
        save_config(bot.config)
        await interaction.response.send_message(f"🗑️ {nutzer.mention} wurde von der Wartungs-Whitelist entfernt.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Der Nutzer {nutzer.mention} ist nicht auf der Whitelist.", ephemeral=True)

@wartung_group.command(name="list", description="Zeigt alle Nutzer auf der Wartungs-Whitelist.")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def wartung_list(interaction: discord.Interaction):
    bot: MyBot = interaction.client
    description = f"**Bot-Inhaber (permanent):** <@{bot.owner_id}>\n\n"
    if not bot.maintenance_whitelist:
        description += "**Temporäre Helfer:**\n*Niemand*"
    else:
        description += "**Temporäre Helfer:**\n" + "\n".join([f"<@{user_id}>" for user_id in bot.maintenance_whitelist])
    embed = discord.Embed(title="🔧 Wartungs-Berechtigungen", description=description, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===================================================
# BEFEHLSSPERREN-BEFEHLE
# ===================================================
sperre_group = app_commands.Group(name="sperre", description="Befehle zum Deaktivieren von Befehlen oder Gruppen.")

@sperre_group.command(name="add", description="Sperrt einen Befehl oder eine Befehlsgruppe.")
@app_commands.describe(command_name="Der genaue Name des Befehls oder der Gruppe (z.B. 'unit-eintritt' oder 'wartung').")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def sperre_add(interaction: discord.Interaction, command_name: str):
    bot: MyBot = interaction.client
    if command_name not in bot.config['disabled_commands']:
        bot.config['disabled_commands'].append(command_name)
        save_config(bot.config)
        await interaction.response.send_message(f"🔒 **Befehl/Gruppe `{command_name}` wurde gesperrt.**", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ Der Befehl/Gruppe `{command_name}` ist bereits gesperrt.", ephemeral=True)

@sperre_group.command(name="remove", description="Entsperrt einen Befehl oder eine Befehlsgruppe.")
@app_commands.describe(command_name="Der genaue Name des Befehls oder der Gruppe.")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def sperre_remove(interaction: discord.Interaction, command_name: str):
    bot: MyBot = interaction.client
    if command_name in bot.config['disabled_commands']:
        bot.config['disabled_commands'].remove(command_name)
        save_config(bot.config)
        await interaction.response.send_message(f"🔓 **Befehl/Gruppe `{command_name}` wurde entsperrt.**", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Der Befehl/Gruppe `{command_name}` war nicht gesperrt.", ephemeral=True)

@sperre_group.command(name="list", description="Zeigt alle gesperrten Befehle und Gruppen an.")
@app_commands.check(lambda i: i.user.id == OWNER_ID_STATIC)
async def sperre_list(interaction: discord.Interaction):
    bot: MyBot = interaction.client
    if not bot.config['disabled_commands']:
        await interaction.response.send_message("ℹ️ Aktuell sind keine Befehle gesperrt.", ephemeral=True)
        return
    description = "Die folgenden Befehle und Gruppen sind derzeit deaktiviert:\n\n" + "\n".join([f"- `{cmd}`" for cmd in bot.config['disabled_commands']])
    embed = discord.Embed(title="🔒 Gesperrte Befehle", description=description, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===================================================
# BOT START
# ===================================================
async def main():
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError("Kein DISCORD_TOKEN in der .env Datei gefunden.")

    intents = discord.Intents.all() # Einfachheit halber alle Intents aktivieren
    
    bot = MyBot(command_prefix="!#####!", intents=intents)
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Bot wird heruntergefahren.{Colors.RESET}")
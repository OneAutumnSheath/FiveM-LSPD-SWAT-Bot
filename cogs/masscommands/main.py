import discord
from discord import app_commands, Interaction
from discord.ext import commands
import os
import importlib
import shlex
import sys
from typing import TYPE_CHECKING

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot

class MassCommandsCog(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "MassCommands"
        self.command_modules = {}
        self.load_mass_command_modules()

    def load_mass_command_modules(self):
        """Lädt alle Massen-Befehlsmodule aus dem 'modules'-Unterordner."""
        self.command_modules.clear()
        folder = os.path.join(os.path.dirname(__file__), "modules")
        if not os.path.isdir(folder):
            print(f"[WARNUNG] MassCommands: Modul-Ordner '{folder}' nicht gefunden.")
            return
            
        for filename in os.listdir(folder):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                full_mod_path = f"cogs.masscommands.modules.{module_name}"
                try:
                    # Korrekte Lade-Logik für normale Python-Module
                    if full_mod_path in sys.modules:
                        mod = importlib.reload(sys.modules[full_mod_path])
                    else:
                        mod = importlib.import_module(full_mod_path)
                    
                    cmd_name = getattr(mod, "COMMAND_NAME", None)
                    friendly_name = getattr(mod, "FRIENDLY_NAME", cmd_name)
                    syntax = getattr(mod, "SYNTAX", "Keine Syntax definiert.")
                    found_class = next((c for c in mod.__dict__.values() if isinstance(c, type) and hasattr(c, "handle")), None)
                    
                    if cmd_name and found_class:
                        self.command_modules[cmd_name.lower()] = {
                            "instance": found_class(self.bot),
                            "friendly_name": friendly_name,
                            "syntax": syntax.strip()
                        }
                    else:
                        print(f"[WARNUNG] MassCommands-Modul {filename} unvollständig.")
                except Exception as e:
                    print(f"[FEHLER] Fehler beim Laden des MassCommand-Moduls {filename}: {e}")

    # --- Befehlsgruppe ---
    mass_group = app_commands.Group(name="masscommands", description="Massen-Befehle ausführen oder deren Format anzeigen.")

    @mass_group.command(name="execute", description="Führe Massenbefehle aus einer hochgeladenen .txt-Datei aus")
    @app_commands.describe(file="Die .txt-Datei, die verarbeitet werden soll")
    @has_permission("masscommands.execute")
    @log_on_completion
    async def mass_execute(self, interaction: Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not file.filename.endswith(".txt"):
            return await interaction.followup.send("❌ Bitte lade eine .txt-Datei hoch!", ephemeral=True)

        try:
            data_str = (await file.read()).decode("utf-8")
        except UnicodeDecodeError:
            return await interaction.followup.send("❌ Datei muss UTF-8-kodiert sein!", ephemeral=True)

        errors, successes = [], []
        lines = data_str.splitlines()

        for i, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line: continue
            
            try:
                tokens = shlex.split(line)
                if not tokens: continue

                cmd = tokens[0].lower()
                module_data = self.command_modules.get(cmd)
                if not module_data:
                    errors.append((i, raw_line, f"Unbekannter Befehl '{cmd}'"))
                    continue

                module_instance = module_data["instance"]
                await module_instance.handle(interaction, tokens, raw_line, i, errors, successes)
            except Exception as e:
                errors.append((i, raw_line, f"Unerwarteter Fehler bei Ausführung: {e}"))

        # --- Abschlussbericht ---
        report_parts = [f"### ✅ Verarbeitung abgeschlossen\n**Erfolgreich:** {len(successes)}"]
        if successes:
             success_details = "\n".join([f"Zeile {ln}: {msg}" for ln, msg in successes[:10]])
             report_parts.append(f"\n**Erfolgsdetails (max. 10):**\n{success_details}")
        if errors:
            report_parts.append(f"**Fehlgeschlagen:** {len(errors)}")
            error_details = "\n".join([f"Zeile {ln}: `{line}` -> {err}" for ln, line, err in errors[:10]])
            report_parts.append(f"\n**Fehlerdetails (max. 10):**\n{error_details}")
        
        full_report = "\n".join(report_parts)
        if len(full_report) > 1900:
            full_report = full_report[:1900] + "\n..."

        await interaction.followup.send(full_report, ephemeral=True)

    @mass_group.command(name="format", description="Zeigt das Format aller MassCommands-Module.")
    @has_permission("masscommands.format")
    @log_on_completion
    async def mass_format(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        self.load_mass_command_modules() # Lade Module neu, um Änderungen zu erfassen

        if not self.command_modules:
            return await interaction.followup.send("Keine Mass-Command-Module geladen.", ephemeral=True)

        help_text_parts = ["**MassCommands - Übersicht aller geladenen Module**\n"]
        
        for cmd_name, module_data in self.command_modules.items():
            friendly_name = module_data['friendly_name']
            syntax = module_data['syntax']
            
            help_text_parts.append(f"__**{friendly_name} (`{cmd_name}`)**__")
            help_text_parts.append(f"```\n{syntax}\n```")
        
        help_text_parts.append("*Lade eine .txt-Datei per `/masscommands execute file:...` hoch, in der jede Zeile einem dieser Formate entspricht.*")
        
        await interaction.followup.send("\n".join(help_text_parts), ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(MassCommandsCog(bot))
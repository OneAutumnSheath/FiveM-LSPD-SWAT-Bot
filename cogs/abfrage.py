import discord
from discord.ext import commands
from discord import app_commands
import csv
import os

# Definiert die Cog-Klasse für den Mitgliederexport.
# Eine Cog ist eine Sammlung von Befehlen, Listenern und Zuständen für einen Bot.
class MemberExportCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Mapping von der internen Rang-Nummer zur Discord-Rollen-ID.
        # Dies dient als zentrale Konfiguration für die Ränge.
        self.RANK_ID_TO_ROLE_ID = {
            1: 935015868444868658, 2: 1294946672941465652, 3: 935015801445056592, 4: 1387536697536811058, 
            5: 1387536786716098590, 6: 935015740438880286, 7: 1131339674267435008, 8: 1387537827545481410, 
            9: 1387537817529487592, 10: 937126775010504735, 11: 1387538125060051034, 12: 962360526388727878,
            13: 1293917052511453224, 14: 935011460998893648, 15: 1293916581784584202, 16: 1361644874293837824, 
            17: 935010817580089404
        }
        # Wir kehren das Mapping um, um von einer Rollen-ID schnell auf eine Rang-Nummer zugreifen zu können.
        # Dies optimiert die Suche erheblich.
        self.ROLE_ID_TO_RANK_ID = {v: k for k, v in self.RANK_ID_TO_ROLE_ID.items()}

    # Definition des Slash-Befehls zum Exportieren der Mitgliederdaten.
    # Nur für Benutzer mit Administratorrechten sichtbar und nutzbar.
    @app_commands.command(name="exportmembers", description="Exportiert Mitglieder mit bestimmten Rängen in eine CSV-Datei.")
    #@app_commands.default_permissions(administrator=True)
    async def export_members(self, interaction: discord.Interaction):
        # Stellt sicher, dass der Befehl in einem Server (Guild) und nicht in einer DM ausgeführt wird.
        if not interaction.guild:
            await interaction.response.send_message("Dieser Befehl kann nur auf einem Server verwendet werden.", ephemeral=True)
            return

        # Die Antwort wird verzögert, da das Sammeln der Daten einen Moment dauern kann.
        # 'ephemeral=True' sorgt dafür, dass die Antwort nur für den ausführenden Benutzer sichtbar ist.
        await interaction.response.defer(ephemeral=True)

        # Liste zum Speichern der zu exportierenden Mitgliederdaten.
        members_data = []
        
        # Iteration durch alle Mitglieder des Servers.
        for member in interaction.guild.members:
            highest_rank_id = 0 # Initialisiert mit 0 (kein Rang).

            # Iteration durch die Rollen des aktuellen Mitglieds, um den höchsten Rang zu finden.
            for role in member.roles:
                if role.id in self.ROLE_ID_TO_RANK_ID:
                    current_rank_id = self.ROLE_ID_TO_RANK_ID[role.id]
                    if current_rank_id > highest_rank_id:
                        highest_rank_id = current_rank_id
            
            # Wenn ein relevanter Rang für das Mitglied gefunden wurde (d.h. > 0),
            # werden die Daten dem Export hinzugefügt.
            if highest_rank_id > 0:
                members_data.append({
                    "Nickname": member.display_name,
                    "DiscordID": member.id,
                    "RankID": highest_rank_id
                })

        # Überprüfen, ob überhaupt Mitglieder mit den definierten Rängen gefunden wurden.
        if not members_data:
            await interaction.followup.send("Es wurden keine Mitglieder mit den angegebenen Rängen gefunden.", ephemeral=True)
            return

        # Definition des Dateipfads. Die Datei wird im Root-Verzeichnis des Bots gespeichert.
        file_path = "member_export.csv"
        
        try:
            # Schreiben der gesammelten Daten in die CSV-Datei.
            with open(file_path, mode='w', newline='', encoding='utf-8') as csv_file:
                # Definiert die Spaltenüberschriften für die CSV-Datei.
                fieldnames = ["Nickname", "DiscordID", "RankID"]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                # Schreibt die Kopfzeile in die Datei.
                writer.writeheader()
                # Schreibt die Daten für jedes gefundene Mitglied.
                writer.writerows(members_data)
            
            # Erfolgsmeldung an den Benutzer senden.
            await interaction.followup.send(
                f"Export erfolgreich! {len(members_data)} Mitglieder wurden in `{file_path}` gespeichert.",
                ephemeral=True
            )
        except IOError as e:
            # Fehlermeldung, falls die Datei aus irgendeinem Grund nicht geschrieben werden konnte.
            print(f"Fehler beim Schreiben der CSV-Datei: {e}")
            await interaction.followup.send(
                "Ein Fehler ist aufgetreten. Die CSV-Datei konnte nicht erstellt werden. Überprüfe die Konsole des Bots für mehr Details.",
                ephemeral=True
            )

# Asynchrone Setup-Funktion, die vom Bot aufgerufen wird, um die Cog zu laden.
# Dies ist der Standard-Einstiegspunkt für jede Cog-Datei.
async def setup(bot: commands.Bot):
    await bot.add_cog(MemberExportCog(bot))


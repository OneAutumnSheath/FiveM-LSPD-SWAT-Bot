import discord
from discord.ext import commands
import json
import io
import os
from datetime import datetime
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
STATS_FILE = "einsatz_statistik.json"
DOKUMENTATIONS_CHANNEL_ID = 1213679610718322758

class RaubService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.stats = self._load_stats()
        self.__cog_name__ = "RaubService"

    # --- Statistik-Logik ---

    def _load_stats(self) -> dict:
        """Lädt die Statistik aus der JSON-Datei."""
        if not os.path.exists(STATS_FILE):
            with open(STATS_FILE, "w") as f:
                json.dump({"einsatzleitung": {}, "verhandlungsfuehrung": {}}, f)
            return {"einsatzleitung": {}, "verhandlungsfuehrung": {}}
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"einsatzleitung": {}, "verhandlungsfuehrung": {}}

    def _save_stats(self):
        """Speichert die aktuelle Statistik in der JSON-Datei."""
        with open(STATS_FILE, "w") as f:
            json.dump(self.stats, f, indent=4)

    def _increment_stat(self, user: discord.User, role: str):
        """Erhöht den Zähler für einen Benutzer in einer bestimmten Rolle."""
        user_id = str(user.id)
        self.stats.setdefault(role, {})[user_id] = self.stats[role].get(user_id, 0) + 1
        self._save_stats()

    def reset_stats(self) -> Tuple[bool, str]:
        """Setzt die Statistik zurück und speichert den leeren Zustand."""
        self.stats = {"einsatzleitung": {}, "verhandlungsfuehrung": {}}
        self._save_stats()
        return True, "Die gesamte Einsatz-Statistik wurde erfolgreich zurückgesetzt."

    # --- Hauptlogik für die Dokumentation ---

    async def create_raub_dokumentation(
        self,
        ersteller: discord.Member,
        einsatzleitung: discord.User,
        verhandlungsfuehrung: discord.User,
        beweisbild: discord.Attachment
    ) -> Tuple[bool, str]:
        """Erstellt und sendet die Raub-Dokumentation und gibt eine Erfolgsnachricht zurück."""
        dokumentations_channel = self.bot.get_channel(DOKUMENTATIONS_CHANNEL_ID)
        if not dokumentations_channel:
            return False, "Interner Fehler: Dokumentations-Channel nicht gefunden."

        if not beweisbild.content_type or not beweisbild.content_type.startswith('image/'):
            return False, "Das Beweisbild muss eine gültige Bilddatei sein."

        try:
            # Statistik aktualisieren
            self._increment_stat(einsatzleitung, "einsatzleitung")
            self._increment_stat(verhandlungsfuehrung, "verhandlungsfuehrung")

            # Embed erstellen
            jetzt = datetime.now()
            embed = discord.Embed(
                title="🚨 Neue Dokumentation zu einem Raub",
                description="Anhand der Dokumentation erfolgt die Entscheidung einer Beförderung zum Sonntag.",
                color=0x00ff00,
                timestamp=jetzt
            )
            embed.add_field(name="👮 Einsatzleitung (EL)", value=f"{einsatzleitung.mention}", inline=True)
            embed.add_field(name="🗣️ Verhandlungsführung (VF)", value=f"{verhandlungsfuehrung.mention}", inline=True)
            embed.add_field(name="📝 Dokumentiert von", value=f"{ersteller.mention}", inline=False)
            embed.set_footer(text=f"Ausgeführt von {ersteller.display_name}", icon_url=ersteller.display_avatar.url)
            embed.set_image(url="attachment://beweisbild.png")

            image_file = discord.File(io.BytesIO(await beweisbild.read()), filename="beweisbild.png")

            await dokumentations_channel.send(embed=embed, file=image_file)
            return True, f"Raub wurde erfolgreich in {dokumentations_channel.mention} dokumentiert."

        except Exception as e:
            print(f"Fehler bei der Raub-Dokumentation: {e}")
            return False, "Ein unerwarteter interner Fehler ist aufgetreten."

    async def get_stats_embed(self) -> discord.Embed:
        """Erstellt und gibt ein Embed mit der aktuellen Statistik zurück."""
        self.stats = self._load_stats()  # Immer frische Daten laden
        embed = discord.Embed(
            title="📊 Einsatz-Statistik",
            description="Übersicht der geleiteten Einsätze.",
            color=0x0099ff
        )

        async def format_leaderboard(role: str) -> str:
            sorted_stats = sorted(self.stats.get(role, {}).items(), key=lambda item: item[1], reverse=True)
            if not sorted_stats:
                return "Noch keine Daten vorhanden."
            leaderboard_text = ""
            for i, (user_id, count) in enumerate(sorted_stats[:10], 1): # Top 10
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    leaderboard_text += f"{i}. {user.mention}: **{count}** Einsätze\n"
                except discord.NotFound:
                    leaderboard_text += f"{i}. *Unbek. User ({user_id})*: **{count}** Einsätze\n"
            return leaderboard_text

        embed.add_field(name="👮 Einsatzleitung (EL)", value=await format_leaderboard("einsatzleitung"), inline=False)
        embed.add_field(name="🗣️ Verhandlungsführung (VF)", value=await format_leaderboard("verhandlungsfuehrung"), inline=False)
        return embed

async def setup(bot: "MyBot"):
    await bot.add_cog(RaubService(bot))

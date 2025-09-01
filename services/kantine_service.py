import discord
from discord.ext import commands
from datetime import datetime, timezone
import json
import os
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
STATUS_FILE = "./config/kantine_status.json"
CHANNEL_ID = 1353348248823136270  # Ziel-Channel für die Logs

class KantineService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "KantineService"
        self._status = "Geschlossen"
        self._write_lock = asyncio.Lock()
        self.bot.loop.create_task(self._load_status())

    async def _load_status(self):
        """Lädt den Status einmalig beim Start."""
        async with self._write_lock:
            if not os.path.exists(STATUS_FILE): return
            try:
                with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._status = data.get("status", "Geschlossen")
                print(f"Kantinen-Status geladen: {self._status}")
            except (IOError, json.JSONDecodeError):
                self._status = "Geschlossen"

    async def _save_status(self):
        """Speichert den aktuellen Status in die Datei."""
        async with self._write_lock:
            os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
            with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"status": self._status}, f, indent=4)

    # --- Öffentliche API-Methoden ---

    def get_status(self) -> str:
        """Gibt den aktuellen Status zurück."""
        return self._status

    async def open_canteen(self, user: discord.Member, zusatzpersonal: str) -> bool:
        """Öffnet die Kantine, speichert den Status und sendet die Log-Nachricht."""
        if self._status == "Geöffnet":
            return False 

        self._status = "Geöffnet"
        await self._save_status()

        if channel := self.bot.get_channel(CHANNEL_ID):
            embed = discord.Embed(
                title="✅ Öffnung protokolliert",
                description=f"{user.mention} hat die Kantine geöffnet.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
            if zusatzpersonal:
                embed.add_field(name="Zusatzpersonal", value=zusatzpersonal, inline=False)
            await channel.send(embed=embed)
        
        return True
        
    async def close_canteen(self, user: discord.Member) -> bool:
        """Schließt die Kantine, speichert den Status und sendet die Log-Nachricht."""
        if self._status == "Geschlossen":
            return False

        self._status = "Geschlossen"
        await self._save_status()
        
        if channel := self.bot.get_channel(CHANNEL_ID):
            embed = discord.Embed(
                title="❌ Schließung protokolliert",
                description=f"{user.mention} hat die Kantine geschlossen.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
            await channel.send(embed=embed)
            
        return True

async def setup(bot: "MyBot"):
    await bot.add_cog(KantineService(bot))
# bot/services/livestream_service.py

import discord
import aiohttp
import aiomysql
from discord.ext import commands, tasks
import os
from typing import TYPE_CHECKING, Dict, Any, List, Tuple

if TYPE_CHECKING:
    from main import MyBot

# --- Konstanten ---
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

DISCORD_NOTIFICATION_CHANNEL_ID = 1180993957191221338

class LiveStreamService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "LiveStreamService"
        self.twitch_oauth_token = None

    async def cog_load(self):
        """Initialisiert die DB-Tabelle und startet den Hintergrund-Task."""
        await self._create_tables_async()
        self.check_stream_status.start()
        print("LiveStream-Service geladen und Task gestartet.")

    def cog_unload(self):
        """Stoppt den Hintergrund-Task sauber."""
        self.check_stream_status.cancel()

    # --- Datenbank-Helfer ---
    async def _execute_query(self, query: str, args: tuple = None, fetch: str = None):
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                if fetch == "one": result = await cursor.fetchone()
                elif fetch == "all": result = await cursor.fetchall()
                else: result = None
                await conn.commit()
                return result

    async def _create_tables_async(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS streamers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                platform VARCHAR(10) NOT NULL,
                channel_id VARCHAR(255) NOT NULL,
                user_id BIGINT NOT NULL,
                is_live BOOLEAN DEFAULT FALSE,
                UNIQUE KEY (platform, channel_id)
            )
        """)

    # --- Öffentliche API des Services ---
    async def add_streamer(self, platform: str, channel_id: str, user_id: int) -> Dict[str, Any]:
        query = "INSERT IGNORE INTO streamers (platform, channel_id, user_id) VALUES (%s, %s, %s)"
        await self._execute_query(query, (platform.lower(), channel_id, user_id))
        return {"success": True}

    async def remove_streamer(self, platform: str, channel_id: str) -> Dict[str, Any]:
        query = "DELETE FROM streamers WHERE platform = %s AND channel_id = %s"
        await self._execute_query(query, (platform.lower(), channel_id))
        return {"success": True}

    async def trigger_check(self):
        """Löst eine manuelle Überprüfung aller Streams aus."""
        print("Manuelle Überprüfung der Streams ausgelöst...")
        await self.check_stream_status()

    # --- API-Aufrufe (Twitch & YouTube) ---
    async def _get_twitch_token(self):
        url = "https://id.twitch.tv/oauth2/token"
        params = {"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET, "grant_type": "client_credentials"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.twitch_oauth_token = data.get("access_token")
                else:
                    print(f"Fehler beim Abrufen des Twitch-Tokens: {resp.status}")
                    self.twitch_oauth_token = None

    async def _check_twitch_stream(self, streamer_login: str) -> bool:
        if not self.twitch_oauth_token:
            await self._get_twitch_token()
        if not self.twitch_oauth_token: return False
        
        url = f"https://api.twitch.tv/helix/streams?user_login={streamer_login}"
        headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {self.twitch_oauth_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    await self._get_twitch_token()
                    headers["Authorization"] = f"Bearer {self.twitch_oauth_token}"
                    async with session.get(url, headers=headers) as resp2:
                        data = await resp2.json()
                else:
                    data = await resp.json()
                return len(data.get("data", [])) > 0

    async def _check_youtube_live(self, channel_id: str) -> bool:
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return "items" in data and len(data["items"]) > 0

    async def _get_user_data(self, platform: str, channel_id: str) -> Tuple[str | None, int]:
        """Holt Profilbild und Farbe für das Embed."""
        if platform == "twitch":
            url = f"https://api.twitch.tv/helix/users?login={channel_id}"
            headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {self.twitch_oauth_token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()
                    pfp = data["data"][0]["profile_image_url"] if data.get("data") else None
                    return pfp, 0x9146FF
        elif platform == "youtube":
            url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={channel_id}&key={YOUTUBE_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    pfp = data["items"][0]["snippet"]["thumbnails"]["high"]["url"] if data.get("items") else None
                    return pfp, 0xFF0000
        return None, discord.Color.default().value

    # --- Hintergrund-Task ---
    @tasks.loop(minutes=5)
    async def check_stream_status(self):
        streamers = await self._execute_query("SELECT platform, channel_id, user_id, is_live FROM streamers", fetch="all")
        if not streamers: return

        channel = self.bot.get_channel(DISCORD_NOTIFICATION_CHANNEL_ID)
        if not channel:
            print("Stream-Benachrichtigungskanal nicht gefunden.")
            return

        for streamer in streamers:
            platform, channel_id, user_id, is_live = streamer.values()
            try:
                if platform == "twitch":
                    currently_live = await self._check_twitch_stream(channel_id)
                    stream_url = f"https://twitch.tv/{channel_id}"
                elif platform == "youtube":
                    currently_live = await self._check_youtube_live(channel_id)
                    stream_url = f"https://www.youtube.com/channel/{channel_id}/live"
                else:
                    continue

                if currently_live and not is_live:
                    await self._execute_query("UPDATE streamers SET is_live = %s WHERE channel_id = %s", (True, channel_id))
                    user = self.bot.get_user(user_id) or f"User-ID: {user_id}"
                    user_mention = user.mention if isinstance(user, discord.User) else user
                    
                    pfp_url, color = await self._get_user_data(platform, channel_id)
                    
                    embed = discord.Embed(
                        title=f"{platform.capitalize()} Stream ist LIVE!",
                        description=f"{user_mention} ist jetzt live! Schaut doch mal vorbei:\n**[Hier zum Stream]({stream_url})**",
                        color=color
                    )
                    if pfp_url:
                        embed.set_thumbnail(url=pfp_url)
                    await channel.send(embed=embed)

                elif not currently_live and is_live:
                    await self._execute_query("UPDATE streamers SET is_live = %s WHERE channel_id = %s", (False, channel_id))
            except Exception as e:
                print(f"Fehler beim Überprüfen von Streamer {channel_id} ({platform}): {e}")

    @check_stream_status.before_loop
    async def before_check_stream_status(self):
        await self.bot.wait_until_ready()

async def setup(bot: "MyBot"):
    await bot.add_cog(LiveStreamService(bot))
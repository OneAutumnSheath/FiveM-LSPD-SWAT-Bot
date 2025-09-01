import discord
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot
    from services.permission_service import PermissionService

class UprankAntragService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UprankAntragService"

        # Key: Quell-Channel, Value: Ziel-Channel für den Antrag
        self.channel_map = {
            1306741178321997846: 1097626041083756604,
            1306741664127258644: 1097626041083756604,
            1306740612556525650: 1097626041083756604,
            1306741410455752805: 1097626041083756604,
            1306739470929756274: 1097626041083756604,
            1306739715826782340: 1097626041083756604,
            1306741836567679036: 1097626041083756604,
            1306740165242392619: 1097626041083756604,
            1335699215405420544: 1097626041083756604
        }
        # Key: Quell-Channel, Value: Name der Unit für das Embed
        self.unit_map = {
            1306741178321997846: "Military Police Corps",
            1306741664127258644: "Airforce",
            1306740612556525650: "Infantry",
            1306741410455752805: "Navy",
            1306739470929756274: "Management",
            1306739715826782340: "Human Resources",
            1306741836567679036: "Navy Seals",
            1306740165242392619: "Education Department",
            1335699215405420544: "S.O.C."
        }

    async def create_uprank_request(self, message: discord.Message):
        """Erstellt ein Embed für einen Uprank-Antrag und sendet es."""
        source_channel_id = message.channel.id
        target_channel_id = self.channel_map.get(source_channel_id)
        if not target_channel_id: return

        target_channel = self.bot.get_channel(target_channel_id)
        if not target_channel: return

        embed = discord.Embed(
            title="Neuer Beförderungsantrag",
            description=message.content or "*[Keine Begründung angegeben]*",
            color=discord.Color.blue(),
            timestamp=message.created_at
        )
        if unit_name := self.unit_map.get(source_channel_id):
            embed.set_author(name=f"Antrag aus: {unit_name}")
        
        embed.set_footer(
            text=f"Antrag für {message.author.display_name}",
            icon_url=message.author.display_avatar.url if message.author.display_avatar else None
        )

        try:
            sent_message = await target_channel.send(embed=embed)
            await sent_message.add_reaction("❌")
            await sent_message.add_reaction("✅")
        except Exception as e:
            print(f"[UprankAntragService] Fehler beim Senden des Antrags: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id not in self.channel_map:
            return
        try:
            await message.add_reaction("📬") # Reaktion, um einen Antrag zu erstellen
        except Exception: pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "📬" or payload.channel_id not in self.channel_map:
            return

        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or not permission_service: return
        
        member = guild.get_member(payload.user_id)
        if not member or member.bot: return

        # Prüft, ob der Reagierende die Berechtigung hat, einen Antrag zu erstellen
        if not permission_service.has_permission(member, "uprank.antrag.create"):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel: return
        try:
            message = await channel.fetch_message(payload.message_id)
            await self.create_uprank_request(message)
        except Exception: pass

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankAntragService(bot))
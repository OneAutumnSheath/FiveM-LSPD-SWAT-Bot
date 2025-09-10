# bot/services/sanction_service.py

import discord
from discord import Interaction
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import aiomysql
import yaml
import re
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from main import MyBot
    from services.display_service import DisplayService

class SanctionService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "SanctionService"
        self.config = self._load_config()

    async def cog_load(self):
        await self._ensure_table_exists()
        self.verwarnung_cleanup_task.start()

    def cog_unload(self):
        self.verwarnung_cleanup_task.cancel()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/sanctions_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/sanctions_config.yaml nicht gefunden.")
            return {}

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

    async def _ensure_table_exists(self):
        await self._execute_query("""
            CREATE TABLE IF NOT EXISTS verwarnungen (
                id INT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL, granted_at DATETIME NOT NULL, KEY user_id_idx (user_id)
            );
        """)

    async def get_member_by_dn(self, dn: str) -> Dict[str, Any] | None:
        return await self._execute_query("SELECT discord_id, name FROM members WHERE dn = %s", (dn,), fetch="one")

    async def count_warnings_from_db(self, user_id: int) -> int:
        """Zählt aktive Verwarnungen für einen User aus der Datenbank."""
        result = await self._execute_query("SELECT COUNT(*) as count FROM verwarnungen WHERE user_id = %s", (user_id,), fetch="one")
        return result['count'] if result else 0

    async def create_sanction_proposal(self, interaction: Interaction, dn: str, sanktionsmass: str, paragraphen: str, sachverhalt: str, zeugen: str | None) -> Dict[str, Any]:
        """Bereitet einen Sanktionsantrag vor."""
        member_data = await self.get_member_by_dn(dn)
        if not member_data:
            return {"success": False, "error": f"Dienstnummer `{dn}` nicht gefunden."}
        
        member = interaction.guild.get_member(member_data['discord_id'])
        if not member:
            return {"success": False, "error": f"Mitglied mit DN `{dn}` nicht auf diesem Server."}

        vorhandene = await self.count_warnings_from_db(member.id)
        matches = re.findall(r"(\d+)\s*Verwarn", sanktionsmass, re.IGNORECASE)
        neue = sum(int(m) for m in matches)
        gesamt = vorhandene + neue

        # DisplayService für die Anzeige verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            member_display = await display_service.get_display(member)
            requester_display = await display_service.get_display(interaction.user, is_footer=True)
        else:
            member_display = member.mention
            requester_display = interaction.user.display_name

        embed = discord.Embed(title="📄 Neuer Sanktionsantrag", color=discord.Color.orange())
        embed.add_field(name="Zielperson", value=f"{member_display} (`{dn}`)", inline=False)
        embed.add_field(name="Sanktionsmaß", value=sanktionsmass, inline=False)
        embed.add_field(name="Rechtsgrundlage", value=paragraphen, inline=False)
        embed.add_field(name="Sachverhalt", value=sachverhalt, inline=False)
        if zeugen:
            embed.add_field(name="Zeugen", value=zeugen, inline=False)
        embed.add_field(name="Verwarnung (neu)", value=str(neue), inline=True)
        embed.add_field(name="Verwarnung (bisher)", value=str(vorhandene), inline=True)
        embed.add_field(name="Verwarnung (gesamt)", value=str(gesamt), inline=True)
        embed.set_footer(text=f"Eingereicht von {requester_display}")

        return {"success": True, "embed": embed, "member": member, "neue_verwarnungen": neue, "sanktionsmass": sanktionsmass}

    async def approve_sanction(self, member: discord.Member, neue_verwarnungen: int, sanktionsmass: str) -> int:
        aktuelle_verwarnungen = await self.count_warnings_from_db(member.id)
        gesamt = aktuelle_verwarnungen + neue_verwarnungen
        
        rollen_config = [(1, self.config.get('verwarnung_1_role_id')), (2, self.config.get('verwarnung_2_role_id'))]
        
        for stufe, rollen_id in rollen_config:
            if gesamt >= stufe:
                rolle = member.guild.get_role(rollen_id)
                if rolle and rolle not in member.roles:
                    await member.add_roles(rolle, reason="Sanktion genehmigt")
                    await self._execute_query("INSERT INTO verwarnungen (user_id, role_id, granted_at) VALUES (%s, %s, %s)", (member.id, rolle.id, datetime.now(timezone.utc)))
        
        # DisplayService für die Eskalationsnachricht verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            member_display = await display_service.get_display(member)
        else:
            member_display = member.mention
            
        if gesamt >= 3:
            if channel := self.bot.get_channel(self.config.get('eskalations_channel_id')):
                await channel.send(f"⚠️ {member_display} hat insgesamt {gesamt} Verwarnungen und somit die Eskalationsstufe erreicht!")

        if mgmt_channel := self.bot.get_channel(self.config.get('management_channel_id')):
            await mgmt_channel.send(f"<@&{self.config.get('management_ping_role_id')}>")
            embed = discord.Embed(title="📢 Management: Sanktion genehmigt", color=discord.Color.blurple())
            embed.add_field(name="Zielperson", value=member_display, inline=False)
            embed.add_field(name="Sanktionsmaß", value=sanktionsmass, inline=False)
            await mgmt_channel.send(embed=embed)
            
        return gesamt

    async def create_simple_sanction(self, user: discord.Member, sanktionsmass: str, grund: str, interaction: Interaction):
        channel = self.bot.get_channel(self.config.get('sanktion_channel_id'))
        if not channel: return False
        
        # DisplayService für die Anzeige verwenden
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if display_service:
            user_display = await display_service.get_display(user)
            executor_display = await display_service.get_display(interaction.user, is_footer=True)
        else:
            user_display = user.mention
            executor_display = interaction.user.display_name
        
        embed = discord.Embed(title="Sanktion verhängt", description=f"Hiermit erhält {user_display} eine Sanktion.", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Sanktionsmaß", value=sanktionsmass, inline=False)
        embed.add_field(name="Grund", value=grund, inline=False)
        embed.add_field(name="Benachrichtigung an", value="<@&1289716541658497055>\n<@&1097648080020574260>", inline=False)
        embed.set_footer(text=f"LSPD Management | ausgeführt von {executor_display}")
        
        # Content mit DisplayService formatieren
        await channel.send(content=user_display if display_service else user.mention, embed=embed)
        return True

    @tasks.loop(hours=1)
    async def verwarnung_cleanup_task(self):
        guild = self.bot.get_guild(self.config.get('guild_id'))
        if not guild: return

        fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)
        abgelaufene = await self._execute_query("SELECT * FROM verwarnungen WHERE granted_at < %s", (fourteen_days_ago,), fetch="all")
        if not abgelaufene: return

        ids_to_delete = [eintrag["id"] for eintrag in abgelaufene]
        
        for eintrag in abgelaufene:
            try:
                member = await guild.fetch_member(eintrag["user_id"])
                rolle = guild.get_role(eintrag["role_id"])
                if member and rolle and rolle in member.roles:
                    await member.remove_roles(rolle, reason="Verwarnung abgelaufen")
            except discord.NotFound:
                continue # Mitglied ist nicht mehr auf dem Server
            except Exception as e:
                print(f"Fehler beim Entfernen abgelaufener Verwarnungs-Rolle: {e}")

        if ids_to_delete:
            format_strings = ','.join(['%s'] * len(ids_to_delete))
            await self._execute_query(f"DELETE FROM verwarnungen WHERE id IN ({format_strings})", tuple(ids_to_delete))

    @verwarnung_cleanup_task.before_loop
    async def before_cleanup_loop(self):
        pass

async def setup(bot: "MyBot"):
    await bot.add_cog(SanctionService(bot))
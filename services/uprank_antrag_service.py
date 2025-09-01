# bot/services/uprank_antrag_service.py

import discord
from discord.ext import commands
import aiomysql
import yaml
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Dict, Any, Optional, List

if TYPE_CHECKING:
    from main import MyBot
    from services.personal_service import PersonalService
    from services.uprank_sperre_service import UprankSperreService
    from services.log_service import LogService
    from cogs.uprank_antrag_commands import UprankAntragCommands

class UprankAntragService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UprankAntragService"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open('config/uprank_antrag_config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print("FATAL: config/uprank_antrag_config.yaml nicht gefunden.")
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

    def get_week_identifier(self, for_datetime: datetime) -> str:
        is_sunday = for_datetime.isoweekday() == 7
        after_cutoff = for_datetime.time() >= time(17, 0)
        target_date = for_datetime + timedelta(days=1) if is_sunday and after_cutoff else for_datetime
        year, week, _ = target_date.isocalendar()
        return f"{year}-W{week:02d}"

    async def get_member_by_dn(self, dn: str) -> Optional[Dict[str, Any]]:
        query = "SELECT discord_id, name, rank FROM members WHERE dn = %s"
        return await self._execute_query(query, (dn,), fetch="one")

    async def create_uprank_request(
        self,
        interaction: discord.Interaction,
        commands_cog: "UprankAntragCommands",
        target_dn: str,
        new_rank_key: int,
        reason: str,
        unit_name: str,
    ) -> Dict[str, Any]:
        requester = interaction.user
        personal_service: "PersonalService" = self.bot.get_cog("PersonalService")
        uprank_sperre_service: "UprankSperreService" = self.bot.get_cog("UprankSperreService")

        target_member_data = await self.get_member_by_dn(target_dn)
        if not target_member_data: return {"success": False, "error": f"Kein Soldat mit der Dienstnummer `{target_dn}` gefunden."}
        db_rank = target_member_data.get('rank')
        if db_rank is None: return {"success": False, "error": f"Der Soldat mit der DN `{target_dn}` hat keinen Rang in der Datenbank."}
        try: current_rank_id = int(db_rank)
        except (ValueError, TypeError): return {"success": False, "error": f"Der Rang (`{db_rank}`) des Soldaten konnte nicht in eine Zahl umgewandelt werden."}

        target_user_id = target_member_data['discord_id']
        target_name = target_member_data['name']
        target_user = requester.guild.get_member(target_user_id)
        if not target_user: return {"success": False, "error": f"Soldat mit der DN `{target_dn}` ist nicht mehr auf dem Server."}
        if not personal_service or new_rank_key not in personal_service.RANK_MAPPING: return {"success": False, "error": f"Der angegebene Rank-Key `{new_rank_key}` ist ungültig."}
        
        if new_rank_key == current_rank_id: return {"success": False, "error": "Der neue Rang darf nicht mit dem aktuellen Rang identisch sein."}
        
        if new_rank_key > current_rank_id:
            if not uprank_sperre_service: return {"success": False, "error": "UprankSperre-Service nicht gefunden."}
            is_locked, lock_end_date = await uprank_sperre_service.check_sperre(target_dn)
            if is_locked:
                timestamp = int(lock_end_date.timestamp())
                return {"success": False, "error": f"{target_user.mention} hat bereits eine Uprank-Sperre, die <t:{timestamp}:R> endet."}

        proposal_channel_id = self.config.get('proposal_channel_id')
        if not proposal_channel_id: return {"success": False, "error": "Proposal-Channel ist nicht in der Konfiguration festgelegt."}
        proposal_channel = self.bot.get_channel(proposal_channel_id)
        if not proposal_channel: return {"success": False, "error": "Proposal-Channel konnte nicht gefunden werden."}

        current_rank_role = requester.guild.get_role(personal_service.RANK_MAPPING.get(current_rank_id))
        new_rank_role = requester.guild.get_role(personal_service.RANK_MAPPING.get(new_rank_key))
        
        action_title = "Beförderungsantrag" if new_rank_key > current_rank_id else "Degradierungsantrag"
        
        proposal_embed = discord.Embed(title=f"{action_title} für {target_name}", description=f"**Grund:**\n{reason}", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        proposal_embed.set_author(name=f"Eingereicht von {requester.display_name}", icon_url=requester.display_avatar.url)
        proposal_embed.add_field(name="Soldat", value=f"{target_user.mention} (`{target_dn}`)", inline=True)
        proposal_embed.add_field(name="Einheit", value=unit_name, inline=True)
        proposal_embed.add_field(name="Rangänderung", value=f"{current_rank_role.mention if current_rank_role else 'Unbekannt'} -> {new_rank_role.mention if new_rank_role else 'Unbekannt'}", inline=False)
        proposal_embed.set_footer(text=f"Antragsteller-ID: {requester.id} | Ziel-ID: {target_user_id}")

        try:
            proposal_message = await proposal_channel.send(embed=proposal_embed)
            await proposal_message.add_reaction("✅")
            await proposal_message.add_reaction("❌")
            await proposal_message.add_reaction("🗑️")
        except discord.HTTPException as e:
            return {"success": False, "error": f"Nachricht konnte nicht gesendet werden: {e}"}

        original_message_id = None
        if interaction.channel.id != proposal_channel_id:
            try:
                unit_copy_embed = proposal_embed.copy()
                unit_copy_embed.title = f"Kopie: {action_title} für {target_name}"
                unit_copy_embed.color = discord.Color.light_grey()
                unit_copy_embed.set_footer(text=f"Dies ist eine Kopie. Die Abstimmung findet im Vorschlags-Kanal statt: {proposal_message.jump_url}")
                unit_copy_message = await interaction.channel.send(embed=unit_copy_embed)
                original_message_id = unit_copy_message.id
            except discord.HTTPException: pass
        
        week_id = self.get_week_identifier(datetime.now(timezone.utc))
        query_requests = "INSERT INTO uprank_requests (requester_id, target_user_id, target_dn, unit_name, reason, new_rank_key, status, week_identifier, proposal_message_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        args_requests = (requester.id, target_user_id, target_dn, unit_name, reason, new_rank_key, 'pending', week_id, proposal_message.id, datetime.now(timezone.utc))
        await self._execute_query(query_requests, args_requests)
        if original_message_id:
            query_proposals = "INSERT INTO uprank_proposals (original_message_id, original_channel_id, proposal_message_id, proposal_channel_id) VALUES (%s, %s, %s, %s)"
            args_proposals = (original_message_id, interaction.channel_id, proposal_message.id, proposal_channel_id)
            await self._execute_query(query_proposals, args_proposals)
        
        await commands_cog._deploy_panel_to_channel(interaction.channel)
        div1_channel_id_from_config = self.config.get('division_1_channel_id')
        if div1_channel_id_from_config:
            if int(div1_channel_id_from_config) != interaction.channel.id:
                div1_channel = self.bot.get_channel(int(div1_channel_id_from_config))
                if div1_channel:
                    await commands_cog._deploy_panel_to_channel(div1_channel)
        
        log_service: "LogService" = self.bot.get_cog("LogService")
        if log_service: await log_service.log_event('uprank', f"Rangänderungsantrag für {target_name} (DN: {target_dn}) von {requester.name} erstellt.")
        return {"success": True, "message": "Dein Rangänderungsantrag wurde erfolgreich erstellt und zur Abstimmung freigegeben."}

    async def delete_uprank_request(self, message_id: int, requester: discord.Member) -> Dict[str, Any]:
        request_data = await self._execute_query("SELECT * FROM uprank_requests WHERE proposal_message_id = %s", (message_id,), fetch="one")
        if not request_data: return {"success": False, "error": "Kein passender Antrag in der Datenbank gefunden."}
        await self._execute_query("UPDATE uprank_requests SET status = 'deleted' WHERE proposal_message_id = %s", (message_id,))
        proposal_link = await self._execute_query("SELECT * FROM uprank_proposals WHERE proposal_message_id = %s", (message_id,), fetch="one")
        proposal_channel_id = self.config.get('proposal_channel_id')
        if proposal_channel_id:
            try:
                channel = self.bot.get_channel(proposal_channel_id)
                if channel: await (await channel.fetch_message(message_id)).delete()
            except discord.Forbidden: return {"success": False, "error": f"Löschen fehlgeschlagen. Dem Bot fehlt 'Nachrichten verwalten' in <#{proposal_channel_id}>."}
            except discord.NotFound: pass
            except Exception as e:
                print(f"Unerwarteter Fehler beim Löschen der Haupt-Nachricht: {e}")
                return {"success": False, "error": "Ein unerwarteter Fehler ist beim Löschen der Haupt-Nachricht aufgetreten."}
        if proposal_link:
            try:
                channel = self.bot.get_channel(proposal_link['original_channel_id'])
                if channel: await (await channel.fetch_message(proposal_link['original_message_id'])).delete()
            except discord.Forbidden: return {"success": False, "error": f"Löschen der Kopie fehlgeschlagen. Dem Bot fehlt 'Nachrichten verwalten' in <#{proposal_link['original_channel_id']}>."}
            except discord.NotFound: pass
            except Exception as e:
                print(f"Unerwarteter Fehler beim Löschen der Kopie: {e}")
                return {"success": False, "error": "Ein unerwarteter Fehler ist beim Löschen der Kopie aufgetreten."}
        log_service: "LogService" = self.bot.get_cog("LogService")
        if log_service:
            log_message = f"Uprank-Antrag (Message ID: {message_id}) wurde von {requester.name} gelöscht."
            await log_service.log_event('uprank', log_message)
        return {"success": True, "message": "Der Antrag wurde gelöscht."}

    async def get_uprank_history_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        query = "SELECT * FROM uprank_requests WHERE target_user_id = %s ORDER BY created_at DESC"
        return await self._execute_query(query, (user_id,), fetch="all")

    async def get_uprank_history_for_week(self, week_identifier: str) -> List[Dict[str, Any]]:
        query = "SELECT * FROM uprank_requests WHERE week_identifier = %s ORDER BY created_at DESC"
        return await self._execute_query(query, (week_identifier,), fetch="all")

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankAntragService(bot))
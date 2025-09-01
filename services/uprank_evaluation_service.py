# bot/services/uprank_evaluation_service.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timezone, timedelta
import aiomysql
from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_antrag_service import UprankAntragService
    from services.personal_service import PersonalService

LAST_EVAL_KEY = "last_uprank_evaluation_week_id"

class UprankEvaluationService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "UprankEvaluationService"
        self.weekly_evaluation_task.start()

    def cog_unload(self):
        self.weekly_evaluation_task.cancel()

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

    async def get_last_evaluated_week(self) -> str | None:
        row = await self._execute_query("SELECT config_value FROM bot_config WHERE config_key = %s", (LAST_EVAL_KEY,), fetch="one")
        return row['config_value'] if row else None

    async def set_last_evaluated_week(self, week_identifier: str):
        query = "INSERT INTO bot_config (config_key, config_value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)"
        await self._execute_query(query, (LAST_EVAL_KEY, week_identifier))
        print(f"Letzter Auswertungs-Wochen-ID auf {week_identifier} gesetzt.")

    def _add_proposals_to_embed(self, embed: discord.Embed, proposals: List[str], title: str):
        """Hilfsfunktion, um eine Liste von Anträgen auf mehrere Felder aufzuteilen."""
        if not proposals:
            embed.add_field(name=title, value="Keine", inline=False)
            return

        field_content = ""
        part = 1
        base_title = title
        numbered_title = f"{base_title} (Teil {part})"

        for line in proposals:
            if len(field_content) + len(line) + 1 > 1024:
                embed.add_field(name=numbered_title, value=field_content, inline=False)
                field_content = line
                part += 1
                numbered_title = f"{base_title} (Teil {part})"
            else:
                field_content += f"\n{line}"
        
        final_title = numbered_title if part > 1 else base_title
        embed.add_field(name=final_title, value=field_content.strip(), inline=False)


    async def get_preview_for_week(self, week_identifier: str) -> Tuple[discord.Embed, int]:
        """Erstellt eine reine Vorschau der Auswertung, OHNE die Datenbank zu verändern."""
        antrag_service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        proposal_channel_id = antrag_service.config.get('proposal_channel_id')
        proposal_channel = self.bot.get_channel(proposal_channel_id) if proposal_channel_id else None
        if not proposal_channel:
            embed = discord.Embed(title="Fehler bei der Vorschau", description="Der `proposal_channel_id` ist nicht konfiguriert.", color=discord.Color.red())
            return embed, 0
        pending_proposals = await self._execute_query("SELECT * FROM uprank_requests WHERE week_identifier = %s AND status = 'pending'", (week_identifier,), fetch="all")
        if not pending_proposals:
            embed = discord.Embed(title=f"Vorschau für {week_identifier}", description="Keine ausstehenden Anträge für diese Woche gefunden.", color=discord.Color.orange())
            return embed, 0
        approved_list, rejected_list = [], []
        for proposal in pending_proposals:
            try:
                message = await proposal_channel.fetch_message(proposal['proposal_message_id'])
                ja_stimmen = next((r.count - 1 for r in message.reactions if str(r.emoji) == '✅'), 0)
                nein_stimmen = next((r.count - 1 for r in message.reactions if str(r.emoji) == '❌'), 0)
                is_approved = ja_stimmen > nein_stimmen
                line = f"`DN: {proposal['target_dn']:<4}` <@{proposal['target_user_id']}> (👍{ja_stimmen}|👎{nein_stimmen})"
                if is_approved: approved_list.append(line)
                else: rejected_list.append(line)
            except (discord.NotFound, discord.Forbidden): pass
            except Exception as e: print(f"Fehler bei der Vorschau von Antrag {proposal['id']}: {e}")
        
        summary_embed = discord.Embed(title=f"📋 Vorschau der Auswertung für {week_identifier}", timestamp=datetime.now(timezone.utc), color=discord.Color.blue())
        self._add_proposals_to_embed(summary_embed, approved_list, "✅ Voraussichtlich Genehmigt")
        self._add_proposals_to_embed(summary_embed, rejected_list, "❌ Voraussichtlich Abgelehnt")
        
        return summary_embed, len(approved_list)

    async def evaluate_proposals_for_week(self, week_identifier: str) -> Tuple[discord.Embed, int]:
        """Sammelt und wertet die Anträge aus und aktualisiert die Datenbank."""
        antrag_service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        personal_service: "PersonalService" = self.bot.get_cog("PersonalService")
        proposal_channel_id = antrag_service.config.get('proposal_channel_id')
        proposal_channel = self.bot.get_channel(proposal_channel_id) if proposal_channel_id else None
        if not proposal_channel or not personal_service:
            embed = discord.Embed(title="Fehler bei der Auswertung", description="Einer der benötigten Services oder der `proposal_channel_id` ist nicht konfiguriert.", color=discord.Color.red())
            return embed, 0

        pending_proposals = await self._execute_query("SELECT * FROM uprank_requests WHERE week_identifier = %s AND status = 'pending'", (week_identifier,), fetch="all")
        if not pending_proposals:
            embed = discord.Embed(title=f"Auswertung für {week_identifier}", description="Keine ausstehenden Anträge für diese Woche gefunden.", color=discord.Color.orange())
            return embed, 0

        grouped_upranks = {}
        grouped_deranks = {}
        approved_count = 0

        for proposal in pending_proposals:
            try:
                message = await proposal_channel.fetch_message(proposal['proposal_message_id'])
                ja_stimmen = next((r.count - 1 for r in message.reactions if str(r.emoji) == '✅'), 0)
                nein_stimmen = next((r.count - 1 for r in message.reactions if str(r.emoji) == '❌'), 0)
                new_status = 'approved' if ja_stimmen > nein_stimmen else 'rejected'
                await self._execute_query("UPDATE uprank_requests SET status = %s WHERE id = %s", (new_status, proposal['id']))

                if new_status == 'approved':
                    approved_count += 1
                    member_details = await personal_service.get_member_details(proposal['target_user_id'])
                    if not member_details: continue
                    
                    old_rank_id = int(member_details['rank'])
                    new_rank_id = proposal['new_rank_key']
                    
                    promo_key = (old_rank_id, new_rank_id)
                    name = member_details['name']
                    member_mention = f"- <@{proposal['target_user_id']}> ({name})"
                    
                    if new_rank_id > old_rank_id:
                        if promo_key not in grouped_upranks: grouped_upranks[promo_key] = []
                        grouped_upranks[promo_key].append(member_mention)
                    else:
                        if promo_key not in grouped_deranks: grouped_deranks[promo_key] = []
                        grouped_deranks[promo_key].append(member_mention)

            except discord.NotFound:
                await self._execute_query("UPDATE uprank_requests SET status = 'deleted' WHERE id = %s", (proposal['id'],))
            except Exception as e:
                print(f"Fehler bei der Auswertung von Antrag {proposal['id']}: {e}")

        summary_embed = discord.Embed(title=f"📋 Wochenauswertung für {week_identifier}", timestamp=datetime.now(timezone.utc), color=discord.Color.green())
        
        if not grouped_upranks and not grouped_deranks:
            summary_embed.description = "In dieser Woche wurden keine Anträge genehmigt."
        
        def add_rank_change_fields(group_title, promotions_dict, is_sorted_desc=False):
            if promotions_dict:
                summary_embed.add_field(name=group_title, value="\u200b", inline=False)
                sorted_promos = sorted(promotions_dict.items(), key=lambda item: item[0][0], reverse=is_sorted_desc)
                for (old_rank, new_rank), members in sorted_promos:
                    old_rank_role_id = personal_service.RANK_MAPPING.get(old_rank)
                    new_rank_role_id = personal_service.RANK_MAPPING.get(new_rank)
                    if not old_rank_role_id or not new_rank_role_id: continue
                    
                    field_title = f"**Rang {old_rank}** ➡ **Rang {new_rank}**"
                    field_value = f"<@&{old_rank_role_id}> ➡ <@&{new_rank_role_id}>\n" + "\n".join(members)
                    
                    summary_embed.add_field(name=field_title, value=field_value, inline=False)
        
        add_rank_change_fields("⏫ Upranks", grouped_upranks)
        add_rank_change_fields("⏬ Deranks", grouped_deranks, is_sorted_desc=True)
        
        return summary_embed, approved_count

    @tasks.loop(time=time(17, 30, tzinfo=timezone.utc))
    async def weekly_evaluation_task(self):
        if datetime.now(timezone.utc).weekday() != 6: return
        antrag_service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        if not antrag_service: return
        evaluation_date = datetime.now(timezone.utc) - timedelta(days=1)
        current_week_id = antrag_service.get_week_identifier(evaluation_date)
        last_evaluated_week = await self.get_last_evaluated_week()
        if last_evaluated_week == current_week_id:
            print(f"Wöchentliche Auswertung für {current_week_id} wird übersprungen, da bereits ausgeführt.")
            return
        print(f"Führe wöchentliche Uprank-Auswertung für {current_week_id} aus...")
        summary_embed, _ = await self.evaluate_proposals_for_week(current_week_id)
        proposal_channel_id = antrag_service.config.get('proposal_channel_id')
        if channel := self.bot.get_channel(proposal_channel_id):
            await channel.send(embed=summary_embed)
            await channel.send("# " + "-"*70 + " Wochenauswertung Abgeschlossen " + "-"*70)
        await self.set_last_evaluated_week(current_week_id)

    @weekly_evaluation_task.before_loop
    async def before_weekly_task(self):
        pass

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankEvaluationService(bot))
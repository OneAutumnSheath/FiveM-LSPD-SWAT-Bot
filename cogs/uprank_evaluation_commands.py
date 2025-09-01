# bot/cogs/uprank_evaluation_commands.py

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from utils.decorators import has_permission, log_on_completion

if TYPE_CHECKING:
    from main import MyBot
    from services.uprank_evaluation_service import UprankEvaluationService
    from services.uprank_antrag_service import UprankAntragService

class UprankEvaluationCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    evaluation_group = app_commands.Group(name="uprank-evaluation", description="Manuelle Auswertung von Beförderungsanträgen.")

    @evaluation_group.command(name="auswertung", description="Führt die wöchentliche Auswertung manuell aus und postet sie öffentlich.")
    @has_permission("uprank.evaluate.public")
    @log_on_completion
    async def evaluate_public(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        eval_service: "UprankEvaluationService" = self.bot.get_cog("UprankEvaluationService")
        antrag_service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        if not eval_service or not antrag_service:
            return await interaction.followup.send("❌ Fehler: Einer der benötigten Services wurde nicht gefunden.", ephemeral=True)
            
        current_week_id = antrag_service.get_week_identifier(datetime.now(timezone.utc))
        
        summary_embed, count = await eval_service.evaluate_proposals_for_week(current_week_id)
        
        proposal_channel_id = antrag_service.config.get('proposal_channel_id')
        if channel := self.bot.get_channel(proposal_channel_id):
            await channel.send(embed=summary_embed)
            if count > 0:
                await channel.send("# " + "-"*70 + " Wochenauswertung Abgeschlossen " + "-"*70)
        
        await eval_service.set_last_evaluated_week(current_week_id)
        
        await interaction.followup.send(f"✅ Manuelle Auswertung für {current_week_id} abgeschlossen und in {channel.mention} gepostet.", ephemeral=True)

    @evaluation_group.command(name="zwischenstand", description="Zeigt eine private Vorschau der aktuellen Auswertung an.")
    @has_permission("uprank.evaluate.private")
    @log_on_completion
    async def evaluate_private(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        eval_service: "UprankEvaluationService" = self.bot.get_cog("UprankEvaluationService")
        antrag_service: "UprankAntragService" = self.bot.get_cog("UprankAntragService")
        if not eval_service or not antrag_service:
            return await interaction.followup.send("❌ Fehler: Einer der benötigten Services wurde nicht gefunden.", ephemeral=True)

        current_week_id = antrag_service.get_week_identifier(datetime.now(timezone.utc))
        
        # Stellt sicher, dass die schreibgeschützte Methode aufgerufen wird
        summary_embed, _ = await eval_service.get_preview_for_week(current_week_id)
        
        await interaction.followup.send(embed=summary_embed, ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(UprankEvaluationCommands(bot))
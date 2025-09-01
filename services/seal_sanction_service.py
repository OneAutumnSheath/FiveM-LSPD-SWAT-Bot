# services/seal_sanction_service.py

import discord
import re
import json
import os
import aiomysql
from discord.ext import commands
from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from main import MyBot

# ### HIER ANPASSEN ###
# Trage hier die IDs für deinen Server und die entsprechenden Rollen ein.
GUILD_ID = 1097625621875675188  # Die ID des Servers, auf dem das System läuft
VERWARNUNG_1_ROLE_ID = 1395430402109214773 # Rollen-ID für die 1. Verwarnung
VERWARNUNG_2_ROLE_ID = 1395430476310777938 # Rollen-ID für die 2. Verwarnung
# ### ENDE ANPASSEN ###

SANCTION_DATA_FILE = "./config/seals-sanctions.json"

class SealSanctionService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "SealSanctionService"
        self.sanctions_data = self._load_sanctions()

    def _load_sanctions(self) -> Dict[str, Any]:
        try:
            if os.path.exists(SANCTION_DATA_FILE):
                with open(SANCTION_DATA_FILE, "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
        return {}

    def _save_sanctions(self):
        with open(SANCTION_DATA_FILE, "w") as f:
            json.dump(self.sanctions_data, f, indent=4)

    async def _get_user_id_by_deckname(self, deckname: str) -> int | None:
        pool: aiomysql.Pool = self.bot.db_pool
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT user_id FROM seals_decknamen WHERE deckname = %s", (deckname,))
                result = await cursor.fetchone()
                return int(result[0]) if result else None

    async def has_remove_permission(self, interaction: discord.Interaction, allowed_role_ids: List[int]) -> bool:
        # Prüfung nur auf dem Haupt-Server
        if not interaction.user: return False
        if interaction.user.guild_permissions.administrator: return True
        return any(role.id in allowed_role_ids for role in interaction.user.roles)

    async def submit_sanction(self, interaction: discord.Interaction, deckname: str, sanktionsmass: str, paragraphen: str, sachverhalt: str, zeugen: str) -> Dict[str, Any]:
        user_id = await self._get_user_id_by_deckname(deckname)
        if not user_id:
            return {"success": False, "error": "Deckname nicht in der Datenbank gefunden."}

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return {"success": False, "error": "Konfigurierter Server nicht gefunden."}
        
        member = guild.get_member(user_id)
        if not member:
            return {"success": False, "error": "Mitglied mit diesem Decknamen wurde auf dem Server nicht gefunden."}

        rolle1 = guild.get_role(VERWARNUNG_1_ROLE_ID)
        rolle2 = guild.get_role(VERWARNUNG_2_ROLE_ID)
        
        pattern = re.compile(r".*([12]).*Verwarnung|Verwarnung.*([12]).*", re.IGNORECASE)
        matches = pattern.findall(sanktionsmass)
        verwarnung_level = int(matches[0][0] or matches[0][1]) if matches and (matches[0][0] or matches[0][1]) in ['1','2'] else 0

        if verwarnung_level > 0 and (not rolle1 or not rolle2):
            return {"success": False, "error": "Konnte die konfigurierten Verwarnungsrollen nicht finden. Bitte Admin kontaktieren."}

        hat_rolle1 = rolle1 in member.roles if rolle1 else False
        rolle_zu_vergeben = None
        meldung = None

        if verwarnung_level == 1:
            rolle_zu_vergeben = rolle2 if hat_rolle1 else rolle1
        elif verwarnung_level == 2:
            if not hat_rolle1:
                await member.add_roles(rolle1, reason="Automatische 1. Verwarnung bei direkter 2.")
            rolle_zu_vergeben = rolle2

        if rolle_zu_vergeben and rolle_zu_vergeben in member.roles:
            meldung = f"⚠️ {member.mention} hat bereits die höchste Verwarnungsstufe erreicht. Eskalation!"
            rolle_zu_vergeben = None
        
        if rolle_zu_vergeben:
            await member.add_roles(rolle_zu_vergeben, reason="Sanktion via Bot")

        if rolle_zu_vergeben:
            self.sanctions_data[str(user_id)] = {"role_id": rolle_zu_vergeben.id}
            self._save_sanctions()

        return {
            "success": True, 
            "member": member,
            "meldung": meldung,
            "removable_role_id": rolle_zu_vergeben.id if rolle_zu_vergeben else VERWARNUNG_1_ROLE_ID
        }

    async def remove_sanction(self, member_id: int) -> Dict[str, Any]:
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return {"success": False, "error": "Konfigurierter Server nicht gefunden."}

        try:
            member = await guild.fetch_member(member_id)
            role1 = guild.get_role(VERWARNUNG_1_ROLE_ID)
            role2 = guild.get_role(VERWARNUNG_2_ROLE_ID)
            
            roles_to_remove = [r for r in [role1, role2] if r and r in member.roles]

            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Sanktion entfernt")

        except discord.NotFound:
            pass # Mitglied nicht auf dem Server, nichts zu tun
        except Exception as e:
            print(f"Fehler beim Entfernen der Sanktionsrollen für {member_id}: {e}")
        
        self.sanctions_data.pop(str(member_id), None)
        self._save_sanctions()
        return {"success": True, "member_id": member_id}

async def setup(bot: "MyBot"):
    await bot.add_cog(SealSanctionService(bot))
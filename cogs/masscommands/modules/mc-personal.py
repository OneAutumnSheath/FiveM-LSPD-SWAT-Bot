import discord
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MyBot
    from services.personal_service import PersonalService
    from services.permission_service import PermissionService

# --- Modul-Konfiguration & Konstanten ---
COMMAND_NAME = "personal"
FRIENDLY_NAME = "Personalverwaltung"
SYNTAX = """
personal einstellen <user_id> "<name>" <rang_id> "<grund>"
personal kuendigen <dn_oder_id> "<grund>"
personal uprank <dn_oder_id> <neue_rang_id> "<grund>"
personal derank <dn_oder_id> <neue_rang_id> "<grund>"
personal neuedn <alte_dn> <neue_dn>
personal rename <dn_oder_id> "<neuer_name>"
"""
PERSONAL_CHANNEL_ID = 1097625981671448698
MGMT_ID = 1097648080020574260

class MC_PersonalModule:
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.personal_service: PersonalService = self.bot.get_cog("PersonalService")

    async def _resolve_user(self, guild: discord.Guild, identifier: str) -> discord.Member | None:
        """Findet ein Mitglied auf dem Haupt-Server anhand von DN oder ID."""
        if not self.personal_service: return None
        
        user_id = None
        if identifier.isdigit() and len(identifier) > 15:
            user_id = int(identifier)
        else:
            details = await self.personal_service._execute_query("SELECT discord_id FROM members WHERE dn = %s", (identifier,), fetch="one")
            if details:
                user_id = details.get('discord_id')
        
        if user_id:
            try:
                return await guild.fetch_member(user_id)
            except discord.NotFound:
                return None
        return None

    def _resolve_role(self, guild: discord.Guild, identifier: str) -> discord.Role | None:
        """Findet eine Rolle anhand einer Rang-ID oder Rollen-ID."""
        if identifier.isdigit():
            if role_id_from_rank := self.personal_service.RANK_MAPPING.get(int(identifier)):
                return guild.get_role(role_id_from_rank)
            return guild.get_role(int(identifier))
        return discord.utils.get(guild.roles, name=identifier)

    async def handle(self, interaction: discord.Interaction, tokens: list[str],
                      line: str, line_no: int, errors: list, successes: list):

        if len(tokens) < 3:
            return errors.append((line_no, line, "Zu wenige Argumente für 'personal'."))

        sub_cmd = tokens[1].lower()
        
        if not self.personal_service:
            return errors.append((line_no, line, "Personal-Service ist nicht geladen."))
        
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not permission_service or not permission_service.has_permission(interaction.user, f"personal.{sub_cmd}"):
             return errors.append((line_no, line, f"Keine Berechtigung für 'personal.{sub_cmd}'."))

        try:
            result = None
            user = None

            if sub_cmd == "einstellen":
                if len(tokens) < 6: raise ValueError("Format: einstellen <user_id> \"<name>\" <rang_id> \"<grund>\"")
                user = await self._resolve_user(interaction.guild, tokens[2])
                name, rank_id_str, reason = tokens[3], tokens[4], tokens[5]
                rank_role = self._resolve_role(interaction.guild, rank_id_str)
                if not user or not rank_role: raise ValueError("User oder Rang konnte nicht gefunden werden.")
                
                result = await self.personal_service.hire_member(interaction.guild, user, name, rank_role, reason)
                if result.get("success"):
                    embed = discord.Embed(title="🆕 Einstellung", color=discord.Color.green(), description=f"**Hiermit wird {result['user'].mention} als {result['rank_role'].mention} eingestellt.**\n\n**Grund:** {result['reason']}\n**Dienstnummer:** `{result['dn']}`\n\nHochachtungsvoll,\n<@&{MGMT_ID}>").set_footer(text=f"U.S. ARMY Management | ausgeführt von {interaction.user.display_name}")
                    if channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
                        await channel.send(result['user'].mention, embed=embed)

            else:
                user_identifier = tokens[2]
                user = await self._resolve_user(interaction.guild, user_identifier)
                if not user: raise ValueError(f"User mit Kennung '{user_identifier}' nicht gefunden.")

                if sub_cmd == "kuendigen":
                    if len(tokens) < 4: raise ValueError("Format: kuendigen <dn_oder_id> \"<grund>\"")
                    reason = tokens[3]
                    result = await self.personal_service.fire_member(user, reason)
                    if result.get("success"):
                        embed = discord.Embed(title="📢 Kündigung", color=discord.Color.red(), description=f"**Hiermit wird {result['user'].mention} offiziell aus der Army entlassen.**\n\n**Grund:** {result['reason']}\n**Dienstnummer:** `{result['dn']}`\n\nHochachtungsvoll,\n<@&{MGMT_ID}>").set_footer(text=f"U.S. ARMY Management | ausgeführt von {interaction.user.display_name}")
                        if channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
                            await channel.send(result['user'].mention, embed=embed)
                
                elif sub_cmd in ["uprank", "derank"]:
                    if len(tokens) < 5: raise ValueError(f"Format: {sub_cmd} <dn_oder_id> <rang_id> \"<grund>\"")
                    rank_id_str, reason = tokens[3], tokens[4]
                    new_rank_role = self._resolve_role(interaction.guild, rank_id_str)
                    if not new_rank_role: raise ValueError(f"Rang '{rank_id_str}' nicht gefunden.")
                    
                    if sub_cmd == "uprank":
                        result = await self.personal_service.promote_member(interaction.guild, user, new_rank_role, reason)
                    else:
                        result = await self.personal_service.demote_member(interaction.guild, user, new_rank_role, reason)

                    if result.get("success"):
                        is_uprank = sub_cmd == "uprank"
                        title = "Beförderung" if is_uprank else "Degradierung"
                        color = discord.Color.green() if is_uprank else discord.Color.red()
                        description = f"Hiermit wurde {user.mention} zum {new_rank_role.mention} {'befördert' if is_uprank else 'degradiert'}.\n\nGrund: {reason}\n\n"
                        if result.get("dn_changed"):
                            description += f"Neue Dienstnummer: **{result['new_dn']}**\n\n"
                        description += f"Hochachtungsvoll,\n<@&{MGMT_ID}>"
                        embed = discord.Embed(title=title, color=color, description=description).set_footer(text=f"U.S. ARMY Management | ausgeführt von {interaction.user.display_name}")
                        if channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
                            await channel.send(user.mention, embed=embed)

                elif sub_cmd == "neuedn":
                    if len(tokens) < 4: raise ValueError("Format: neuedn <alte_dn> <neue_dn>")
                    new_dn = tokens[3]
                    result = await self.personal_service.change_dn(user, new_dn)
                    if result.get("success"):
                         embed = discord.Embed(title="🔄 Dienstnummer Änderung", color=discord.Color.blue(), description=f"**Dienstnummer-Update für {user.mention}!**\n\n**Alte DN:** `{result['old_dn']}`\n**Neue DN:** `{result['new_dn']}`").set_footer(text=f"U.S. ARMY Management | ausgeführt von {interaction.user.display_name}")
                         if channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
                            await channel.send(user.mention, embed=embed)

                elif sub_cmd == "rename":
                    if len(tokens) < 4: raise ValueError("Format: rename <dn_oder_id> \"<neuer_name>\"")
                    new_name = tokens[3]
                    result = await self.personal_service.rename_member(user, new_name)
                    if result.get("success"):
                        embed = discord.Embed(title="📛 Namensänderung", color=discord.Color.orange(), description=f"**{user.mention} wurde umbenannt.**\n\n**Alter Name:** `{result['old_name']}`\n**Neuer Name:** `{result['new_name']}`").set_footer(text=f"U.S. ARMY Management | ausgeführt von {interaction.user.display_name}")
                        if channel := self.bot.get_channel(PERSONAL_CHANNEL_ID):
                            await channel.send(user.mention, embed=embed)
                
                else:
                    raise ValueError(f"Unbekanntes Personal-Subkommando: '{sub_cmd}'")

            if result and result.get("success"):
                successes.append((line_no, f"Aktion '{sub_cmd}' für {user.mention if user else tokens[2]} erfolgreich."))
            else:
                raise Exception(result.get("error", "Unbekannter Service-Fehler"))

        except (ValueError, IndexError) as e:
            errors.append((line_no, line, f"Formatfehler oder ungültiger Wert: {e}"))
        except Exception as e:
            errors.append((line_no, line, f"Allgemeiner Fehler: {e}"))
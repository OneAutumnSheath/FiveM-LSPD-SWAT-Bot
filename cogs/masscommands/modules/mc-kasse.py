import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot
    from services.kassen_service import KassenService
    from services.permission_service import PermissionService
    from services.personal_service import PersonalService
    from cogs.kassen_commands import KassenCommands

# --- Modul-Konfiguration für den dynamischen Lader ---
COMMAND_NAME = "kasse"
FRIENDLY_NAME = "Kasse"
SYNTAX = """
kasse einzahlen <geld> <schwarzgeld> <Grund>
kasse auszahlen <user_id_oder_dn> <geld> <schwarzgeld> <Grund>
"""

class MC_KasseModule:
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    async def _resolve_user(self, identifier: str) -> discord.User | None:
        """Findet einen User anhand von ID oder DN."""
        user_id = None
        if identifier.isdigit() and len(identifier) > 5:
            user_id = int(identifier)
        else:
            personal_service: PersonalService = self.bot.get_cog("PersonalService")
            if personal_service:
                details = await personal_service._execute_query("SELECT discord_id FROM members WHERE dn = %s", (identifier,), fetch="one")
                if details:
                    user_id = details.get('discord_id')
        
        if user_id:
            try:
                return await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return None
        return None

    async def handle(self, interaction: discord.Interaction, tokens: list[str],
                      line: str, line_no: int, errors: list, successes: list):

        sub_cmd = tokens[1].lower() if len(tokens) > 1 else ""
        
        kassen_service: KassenService = self.bot.get_cog("KassenService")
        permission_service: PermissionService = self.bot.get_cog("PermissionService")
        if not kassen_service or not permission_service:
            return errors.append((line_no, line, "Benötigte Services sind nicht geladen."))

        perm_node = f"kasse.{sub_cmd}"
        if not permission_service.has_permission(interaction.user, perm_node):
             return errors.append((line_no, line, f"Keine Berechtigung für '{perm_node}'."))

        try:
            if sub_cmd == "einzahlen":
                if len(tokens) < 5: raise ValueError("Format: kasse einzahlen <geld> <schwarzgeld> <Grund>")
                
                geld_str, schwarzgeld_str = tokens[2], tokens[3]
                reason = " ".join(tokens[4:])
                if not reason: raise ValueError("Ein Grund ist erforderlich.")
                geld, schwarzgeld = int(geld_str), int(schwarzgeld_str)
                
                await kassen_service.update_kassenstand(geld, schwarzgeld)
                
                embed = discord.Embed(
                    title="💵 Einzahlung",
                    description=f"👤 **Von:** {interaction.user.mention}\n"
                                f"💰 **Geld:** +{geld:,}$\n"
                                f"🖤 **Schwarzgeld:** +{schwarzgeld:,}$".replace(",", "."),
                    color=discord.Color.green()
                )
                embed.add_field(name="📌 Grund", value=reason, inline=False)
                
                await kassen_service.log_transaction(embed)
                successes.append((line_no, f"Einzahlung von {geld}$ / {schwarzgeld}$ verbucht."))

            elif sub_cmd == "auszahlen":
                if len(tokens) < 6: raise ValueError("Format: kasse auszahlen <user_id_oder_dn> <geld> <schwarzgeld> <Grund>")
                
                identifier, geld_str, schwarzgeld_str = tokens[2], tokens[3], tokens[4]
                reason = " ".join(tokens[5:])
                if not reason: raise ValueError("Ein Grund ist erforderlich.")
                geld, schwarzgeld = int(geld_str), int(schwarzgeld_str)
                
                user = await self._resolve_user(identifier)
                if not user:
                    raise ValueError(f"User mit Kennung '{identifier}' nicht gefunden.")

                kassenstand = await kassen_service.get_kassenstand()
                if geld > kassenstand.get('geld', 0) or schwarzgeld > kassenstand.get('schwarzgeld', 0):
                    raise ValueError("Nicht genug Geld in der Kasse.")
                
                await kassen_service.update_kassenstand(-geld, -schwarzgeld)
                embed = discord.Embed(
                    title="💸 Auszahlung",
                    description=f"👤 **Von:** {interaction.user.mention}\n"
                                f"➡️ **An:** {user.mention}\n"
                                f"💰 **Geld:** -{geld:,}$\n"
                                f"🖤 **Schwarzgeld:** -{schwarzgeld:,}$\n"
                                f"📌 **Grund:** {reason}".replace(",", "."),
                    color=discord.Color.red()
                )
                await kassen_service.log_transaction(embed)
                successes.append((line_no, f"Auszahlung von {geld}$ / {schwarzgeld}$ an {user.mention} verbucht."))
            
            else:
                errors.append((line_no, line, f"Unbekanntes Kassen-Subkommando: '{sub_cmd}'"))

            if kassen_commands_cog := self.bot.get_cog("KassenCommands"):
                await kassen_commands_cog.send_current_kassenstand()

        except ValueError as e:
            errors.append((line_no, line, f"Formatfehler oder ungültiger Wert: {e}"))
        except Exception as e:
            errors.append((line_no, line, f"Allgemeiner Fehler: {e}"))
#cogs/abmeldung_commands.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from utils.decorators import log_on_completion
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MyBot
    from services.abmeldung_service import AbmeldungService
    from services.log_service import LogService
    from services.display_service import DisplayService # HINZUGEFÜGT
    
# --- Konstanten ---
ABMELDE_CHANNEL_ID = 1301272400989524050
UEBERSICHT_CHANNEL_ID = 1352999040756879360
ABGEMELDET_ROLLE_ID = 1367223382646591508
GUILD_ID = 1097625621875675188

# =========================================================================
# MODAL: Zur Eingabe der Abmeldung
# =========================================================================
class AbmeldungModal(discord.ui.Modal, title="Abmeldung einreichen"):
    zeitraum = discord.ui.TextInput(label="Zeitraum", placeholder="TT.MM.JJJJ - TT.MM.JJJJ", required=True)
    grund = discord.ui.TextInput(label="Grund", placeholder="z.B. Urlaub, Krankheit, etc.", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, bot: "MyBot", commands_cog: "AbmeldungCommands"):
        super().__init__()
        self.bot = bot
        self.commands_cog = commands_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            start_str, end_str = [d.strip() for d in self.zeitraum.value.strip().split("-")]
            start = datetime.strptime(start_str, "%d.%m.%Y").date()
            end = datetime.strptime(end_str, "%d.%m.%Y").date()
            if end < start:
                await interaction.followup.send("❌ Das Enddatum darf nicht vor dem Startdatum liegen!", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Bitte gib den Zeitraum im Format 'TT.MM.JJJJ - TT.MM.JJJJ' an!", ephemeral=True)
            return

        service: AbmeldungService = self.bot.get_cog("AbmeldungService")
        if not service:
            await interaction.followup.send("❌ Interner Fehler: Abmelde-Service nicht gefunden.", ephemeral=True)
            return
            
        dn = await service.get_dn_for_user(interaction.user.id)
        if not dn:
            await interaction.followup.send("❌ Du musst in der Datenbank registriert sein, um eine Abmeldung einzureichen.", ephemeral=True)
            return

        embed = discord.Embed(title="Abmeldung", color=discord.Color.orange())
        embed.add_field(name="Name", value=interaction.user.mention, inline=False)
        embed.add_field(name="Zeitraum", value=self.zeitraum.value, inline=False)
        embed.add_field(name="Grund", value=self.grund.value.strip(), inline=False)
        embed.set_footer(text="U.S. ARMY Abmeldesystem")
        
        channel = interaction.guild.get_channel(ABMELDE_CHANNEL_ID)
        msg = await channel.send(embed=embed)

        await service.add_abmeldung(
            user=interaction.user, dn=dn, start_date=start, end_date=end,
            reason=self.grund.value.strip(), message_id=msg.id
        )

        rolle = interaction.guild.get_role(ABGEMELDET_ROLLE_ID)
        if rolle:
            await interaction.user.add_roles(rolle, reason="Abmeldung eingereicht")

        await self.commands_cog.update_abmeldungs_uebersicht_async()
        await interaction.followup.send("✅ Deine Abmeldung wurde erfolgreich eingereicht!", ephemeral=True)
        await self.commands_cog._setup_panel_async()

# =========================================================================
# VIEW: Die persistenten Buttons im Panel
# =========================================================================
class AbmeldungButtonView(discord.ui.View):
    def __init__(self, bot: "MyBot", commands_cog: "AbmeldungCommands"):
        super().__init__(timeout=None)
        self.bot = bot
        self.commands_cog = commands_cog

    @discord.ui.button(label="Abmeldung einreichen", style=discord.ButtonStyle.primary, custom_id="abmeldung_modal_v2")
    async def abmeldung_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AbmeldungModal(self.bot, self.commands_cog))

    @discord.ui.button(label="Letzte Abmeldung löschen", style=discord.ButtonStyle.danger, custom_id="abmeldung_delete_v2")
    async def delete_last_abmeldung(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        service: AbmeldungService = self.bot.get_cog("AbmeldungService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Abmelde-Service nicht gefunden.", ephemeral=True)

        message_id = await service.remove_abmeldung_by_user_id(interaction.user.id)
        if message_id is None:
            return await interaction.followup.send("❌ Du hast keine aktive Abmeldung, die gelöscht werden könnte.", ephemeral=True)

        channel = interaction.guild.get_channel(ABMELDE_CHANNEL_ID)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound: pass

        rolle = interaction.guild.get_role(ABGEMELDET_ROLLE_ID)
        if rolle and isinstance(interaction.user, discord.Member) and rolle in interaction.user.roles:
            await interaction.user.remove_roles(rolle, reason="Abmeldung selbst beendet")

        await self.commands_cog.update_abmeldungs_uebersicht_async()
        await interaction.followup.send("✅ Deine Abmeldung wurde erfolgreich gelöscht.", ephemeral=True)

# =========================================================================
# COG: Der eigentliche Command-Cog
# =========================================================================
class AbmeldungCommands(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot

    async def _setup_panel_async(self):
        print("🚧 _setup_panel_async gestartet")

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild nicht gefunden.")
            return

        channel = guild.get_channel(ABMELDE_CHANNEL_ID)
        if not channel:
            print("❌ Abmeldechannel nicht gefunden.")
            return

        try:
            async for msg in channel.history(limit=20):
                if msg.author == self.bot.user and msg.components:
                    print(f"🧹 Lösche alte Panel-Nachricht: {msg.id}")
                    await msg.delete()
        except discord.Forbidden:
            print("❌ Keine Berechtigung zum Löschen im Abmeldechannel.")

        try:
            embed = discord.Embed(
                title="📨 Abmeldesystem",
                description="Reiche hier deine Abmeldung ein oder lösche deine letzte, falls du wieder da bist.",
                color=discord.Color.blue()
            )
            view = AbmeldungButtonView(self.bot, self)
            await channel.send(embed=embed, view=view)
            print("✅ Panel-Nachricht mit Button erfolgreich gesendet.")
        except discord.HTTPException as e:
            print(f"❌ HTTPException beim Senden der Panel-Nachricht: {e}")
        except discord.Forbidden:
            print("❌ Bot hat keine Berechtigung zum Senden im Abmeldechannel.")
        except Exception as e:
            print(f"❌ Unerwarteter Fehler beim Panel-Senden: {e}")

    async def cog_load(self):
        self.bot.add_view(AbmeldungButtonView(self.bot, self))
        self.bot.loop.create_task(self.delayed_panel_setup())

        print("🤖 Aktive Guilds:")
        for g in self.bot.guilds:
            print(f"- {g.name} ({g.id})")

    async def delayed_panel_setup(self):
        await self.bot.wait_until_ready()
        print("⏳ Bot ist ready – starte Panel-Setup...")

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            print(f"❌ GUILD_ID {GUILD_ID} nicht gefunden.")
            return

        await self._setup_panel_async()
        print("[AbmeldungCommands] Panel wurde gesetzt.")
        await self.update_abmeldungs_uebersicht_async()


    async def update_abmeldungs_uebersicht_async(self):
        guild = self.bot.get_guild(GUILD_ID)
        if not guild: return
        channel = guild.get_channel(UEBERSICHT_CHANNEL_ID)
        if not channel: return
        
        service: AbmeldungService = self.bot.get_cog("AbmeldungService")
        # --- START DER ÄNDERUNG ---
        display_service: DisplayService = self.bot.get_cog("DisplayService")
        if not service or not display_service: return
        # --- ENDE DER ÄNDERUNG ---

        abmeldungen = await service.get_active_abmeldungen()
        
        embed = discord.Embed(title="Aktive Abmeldungen", color=discord.Color.blue(), timestamp=datetime.now())
        if abmeldungen:
            desc = []
            for eintrag in abmeldungen:
                # --- START DER ÄNDERUNG ---
                member = guild.get_member(eintrag['user_id'])
                display_name = await display_service.get_display(member)
                end_datum_str = eintrag['end_date'].strftime('%d.%m.%Y')
                desc.append(f"{display_name} (bis {end_datum_str})")
                # --- ENDE DER ÄNDERUNG ---
            embed.description = "\n".join(desc)
        else:
            embed.description = "Derzeit sind keine Mitglieder abgemeldet."
        
        embed.set_footer(text="U.S. ARMY Abmeldesystem")

        try:
            async for msg in channel.history(limit=10):
                if msg.author == self.bot.user and msg.embeds and msg.embeds[0].title == "Aktive Abmeldungen":
                    await msg.edit(embed=embed)
                    return
            await channel.send(embed=embed)
        except discord.Forbidden: pass

    @app_commands.command(name="admindelabmeldung", description="Löscht eine Abmeldung eines bestimmten Users.")
    @app_commands.describe(user="Das Mitglied, dessen Abmeldung gelöscht werden soll.")
    @app_commands.checks.has_permissions(administrator=True)
    @log_on_completion
    async def admindelabmeldung(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        service: AbmeldungService = self.bot.get_cog("AbmeldungService")
        if not service:
            return await interaction.followup.send("❌ Interner Fehler: Abmelde-Service nicht gefunden.", ephemeral=True)

        message_id = await service.remove_abmeldung_by_user_id(user.id)
        if message_id is None:
            return await interaction.followup.send(f"❌ Für {user.mention} wurde keine Abmeldung gefunden.", ephemeral=True)

        channel = interaction.guild.get_channel(ABMELDE_CHANNEL_ID)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound: pass

        rolle = interaction.guild.get_role(ABGEMELDET_ROLLE_ID)
        if rolle and rolle in user.roles:
            await user.remove_roles(rolle, reason="Abmeldung durch Admin gelöscht")

        await self.update_abmeldungs_uebersicht_async()
        await interaction.followup.send(f"✅ Abmeldung von {user.mention} wurde administrativ entfernt.", ephemeral=True)

async def setup(bot: "MyBot"):
    await bot.add_cog(AbmeldungCommands(bot))
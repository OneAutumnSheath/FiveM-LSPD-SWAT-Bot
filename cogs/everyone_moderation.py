import discord
from discord.ext import commands


class EveryoneModerator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Hier können Sie die erlaubten Rollen-IDs definieren
        self.allowed_role_ids = [
            # Beispiel IDs - diese müssen durch echte Rollen-IDs ersetzt werden
            # 123456789012345678,  # Moderator Rolle
            # 987654321098765432,  # Staff Rolle^
            1097650413165084772, # GENSTAB
            1097650390230630580, # DIV1
            1097834442283827290, # DOM
            1108008526846103664, # CDOM
        ]
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # Bot-Nachrichten ignorieren
        if message.author.bot:
            return
        
        # Prüfen ob die Nachricht @everyone oder @here enthält
        if not (message.mention_everyone or "@everyone" in message.content or "@here" in message.content):
            return
        
        # Prüfen ob der User berechtigt ist
        if self.is_authorized_user(message.author):
            return
        
        try:
            # Nachricht löschen
            await message.delete()
            
            # Optional: Warnung an den User senden
            warning_embed = discord.Embed(
                title="⚠️ Nachricht gelöscht",
                description=f"{message.author.mention}, du bist nicht berechtigt @everyone oder @here zu verwenden.",
                color=discord.Color.red()
            )
            
            # Warnung senden (wird nach 10 Sekunden gelöscht)
            warning_msg = await message.channel.send(embed=warning_embed)
            await warning_msg.delete(delay=10)
            
            # Optional: Log in einen bestimmten Kanal
            await self.log_deletion(message)
            
        except discord.errors.NotFound:
            # Nachricht wurde bereits gelöscht
            pass
        except discord.errors.Forbidden:
            # Bot hat keine Berechtigung zum Löschen
            print(f"Keine Berechtigung zum Löschen der Nachricht von {message.author}")
    
    def is_authorized_user(self, user):
        """Prüft ob ein User berechtigt ist @everyone zu verwenden"""
        
        # Users mit Administrator-Berechtigung sind immer berechtigt
        if user.guild_permissions.administrator:
            return True
        
        # Prüfen ob User eine der erlaubten Rollen-IDs hat
        user_role_ids = [role.id for role in user.roles]
        return any(role_id in self.allowed_role_ids for role_id in user_role_ids)
    
    async def log_deletion(self, message):
        """Loggt gelöschte @everyone Nachrichten"""
        
        # Suche nach einem Log-Kanal
        log_channel = discord.utils.get(message.guild.channels, name="mod-log")
        if not log_channel:
            log_channel = discord.utils.get(message.guild.channels, name="logs")
        
        if log_channel:
            log_embed = discord.Embed(
                title="🚫 @everyone Nachricht gelöscht",
                color=discord.Color.orange(),
                timestamp=message.created_at
            )
            log_embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=True)
            log_embed.add_field(name="Kanal", value=f"{message.channel.mention}", inline=True)
            log_embed.add_field(name="Nachricht", value=message.content[:1000] + ("..." if len(message.content) > 1000 else ""), inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except discord.errors.Forbidden:
                pass
    
    @commands.command(name="add_everyone_role")
    @commands.has_permissions(administrator=True)
    async def add_everyone_role(self, ctx, role_id: int):
        """Fügt eine Rollen-ID zu den erlaubten @everyone Rollen hinzu"""
        
        # Prüfen ob die Rolle existiert
        role = ctx.guild.get_role(role_id)
        if not role:
            embed = discord.Embed(
                title="❌ Fehler",
                description="Rolle mit dieser ID wurde nicht gefunden.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if role_id not in self.allowed_role_ids:
            self.allowed_role_ids.append(role_id)
            embed = discord.Embed(
                title="✅ Rolle hinzugefügt",
                description=f"Rolle {role.mention} ({role_id}) wurde zu den erlaubten @everyone Rollen hinzugefügt.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="ℹ️ Bereits vorhanden",
                description=f"Rolle {role.mention} ({role_id}) ist bereits in der Liste.",
                color=discord.Color.blue()
            )
        await ctx.send(embed=embed)
    
    @commands.command(name="remove_everyone_role")
    @commands.has_permissions(administrator=True)
    async def remove_everyone_role(self, ctx, role_id: int):
        """Entfernt eine Rollen-ID von den erlaubten @everyone Rollen"""
        
        if role_id in self.allowed_role_ids:
            self.allowed_role_ids.remove(role_id)
            role = ctx.guild.get_role(role_id)
            role_name = role.mention if role else f"ID: {role_id}"
            
            embed = discord.Embed(
                title="✅ Rolle entfernt",
                description=f"Rolle {role_name} wurde von den erlaubten @everyone Rollen entfernt.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Nicht gefunden",
                description="Diese Rollen-ID ist nicht in der Liste der erlaubten Rollen.",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)
    
    @commands.command(name="set_everyone_roles_ids")
    @commands.has_permissions(administrator=True)
    async def set_everyone_roles_ids(self, ctx, *, role_ids):
        """Setzt die erlaubten Rollen-IDs für @everyone Usage (kommagetrennt)"""
        
        try:
            id_list = [int(role_id.strip()) for role_id in role_ids.split(",")]
            
            # Validieren ob alle Rollen existieren
            valid_roles = []
            invalid_ids = []
            
            for role_id in id_list:
                role = ctx.guild.get_role(role_id)
                if role:
                    valid_roles.append((role_id, role.name))
                else:
                    invalid_ids.append(role_id)
            
            if invalid_ids:
                embed = discord.Embed(
                    title="⚠️ Warnung",
                    description=f"Folgende Rollen-IDs wurden nicht gefunden: {', '.join(map(str, invalid_ids))}",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
            
            self.allowed_role_ids = [role_id for role_id, _ in valid_roles]
            
            role_list = [f"{name} ({id})" for id, name in valid_roles]
            embed = discord.Embed(
                title="✅ Rollen aktualisiert",
                description=f"Erlaubte Rollen für @everyone:\n" + "\n".join(role_list) if role_list else "Keine gültigen Rollen",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
        except ValueError:
            embed = discord.Embed(
                title="❌ Fehler",
                description="Ungültiges Format. Bitte verwende kommagetrennte Zahlen (Rollen-IDs).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="everyone_roles")
    @commands.has_permissions(manage_messages=True)
    async def show_everyone_roles(self, ctx):
        """Zeigt die aktuell erlaubten Rollen für @everyone"""
        
        if not self.allowed_role_ids:
            embed = discord.Embed(
                title="📋 Erlaubte Rollen für @everyone",
                description="Keine spezifischen Rollen definiert.\n\n**Automatisch berechtigt:**\n• Alle User mit Administrator-Berechtigung",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        role_list = []
        for role_id in self.allowed_role_ids:
            role = ctx.guild.get_role(role_id)
            if role:
                role_list.append(f"• {role.mention} (`{role_id}`)")
            else:
                role_list.append(f"• Unbekannte Rolle (`{role_id}`)")
        
        embed = discord.Embed(
            title="📋 Erlaubte Rollen für @everyone",
            description=f"**Spezifische Rollen:**\n" + "\n".join(role_list) + "\n\n**Automatisch berechtigt:**\n• Alle User mit Administrator-Berechtigung",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EveryoneModerator(bot))
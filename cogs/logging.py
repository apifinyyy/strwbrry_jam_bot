import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import datetime

class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('logging')

    async def get_logging_config(self, guild_id: int) -> dict:
        """Get logging configuration for a guild"""
        try:
            config = await self.bot.data_manager.load("guild_configs", str(guild_id))
            if not config:
                return {
                    'enabled': False,
                    'log_channel': None,
                    'log_events': {
                        'joins': True,
                        'leaves': True,
                        'messages': True,
                        'edits': True,
                        'deletes': True,
                        'voice': True,
                        'roles': True,
                        'bans': True,
                        'nicknames': True
                    }
                }
            
            # Ensure log_events is a dictionary
            if 'log_events' not in config or isinstance(config['log_events'], list):
                config['log_events'] = {
                    'joins': True,
                    'leaves': True,
                    'messages': True,
                    'edits': True,
                    'deletes': True,
                    'voice': True,
                    'roles': True,
                    'bans': True,
                    'nicknames': True
                }
            
            return {
                'enabled': config.get('logging', {}).get('enabled', False),
                'log_channel': config.get('logging', {}).get('channel'),
                'log_events': config.get('log_events', {})
            }
        except Exception as e:
            self.logger.error(f"Error getting logging config: {e}")
            return {
                'enabled': False,
                'log_channel': None,
                'log_events': {
                    'joins': True,
                    'leaves': True,
                    'messages': True,
                    'edits': True,
                    'deletes': True,
                    'voice': True,
                    'roles': True,
                    'bans': True,
                    'nicknames': True
                }
            }

    async def log_event(self, guild: discord.Guild, embed: discord.Embed):
        """Send a log event with proper error handling."""
        try:
            config = await self.get_logging_config(guild.id)
            if not config['log_channel']:
                return

            channel = guild.get_channel(int(config['log_channel']))
            if not channel:
                return

            # Check if bot has permission to send messages and embeds
            if not channel.permissions_for(guild.me).send_messages or \
               not channel.permissions_for(guild.me).embed_links:
                return

            # Ensure embed description isn't too long
            if embed.description and len(embed.description) > 4096:
                embed.description = f"{embed.description[:4093]}..."

            # Ensure total embed length isn't too long
            total_length = len(embed.description or '')
            for field in embed.fields:
                total_length += len(field.name) + len(field.value)
                if total_length > 6000:
                    embed.clear_fields()
                    embed.add_field(name="Note", value="Some content was truncated due to length limitations.")
                    break

            await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error in log_event: {str(e)}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await self.get_logging_config(message.guild.id)
        if not config['log_events'].get('deletes', True):
            return

        content = message.content
        if len(content) > 1024:
            content = f"{content[:1021]}..."
        if not content:
            content = "No content (possibly an embed or attachment)"

        embed = discord.Embed(
            title="Message Deleted",
            description=f"Message by {message.author.mention} deleted in {message.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Content", value=content, inline=False)
        
        # Add attachment information if any
        if message.attachments:
            attachment_info = "\n".join([f"- {att.filename} ({att.size} bytes)" for att in message.attachments])
            embed.add_field(name="Attachments", value=attachment_info, inline=False)

        embed.set_footer(text=f"Author ID: {message.author.id}")
        await self.log_event(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        config = await self.get_logging_config(before.guild.id)
        if not config['log_events'].get('edits', True):
            return

        # Truncate content if necessary
        before_content = before.content[:1021] + "..." if len(before.content) > 1024 else before.content
        after_content = after.content[:1021] + "..." if len(after.content) > 1024 else after.content

        embed = discord.Embed(
            title="Message Edited",
            description=f"Message by {before.author.mention} edited in {before.channel.mention}\n[Jump to Message]({after.jump_url})",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Before", value=before_content or "No content", inline=False)
        embed.add_field(name="After", value=after_content or "No content", inline=False)
        embed.set_footer(text=f"Author ID: {before.author.id}")

        await self.log_event(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await self.get_logging_config(member.guild.id)
        if not config['log_events'].get('joins', True):
            return

        embed = discord.Embed(
            title="Member Joined",
            description=f"{member.mention} joined the server",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style='R'))
        embed.set_footer(text=f"ID: {member.id}")

        await self.log_event(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Log when a member leaves the server"""
        try:
            config = await self.get_logging_config(member.guild.id)
            if not config['enabled']:
                return
                
            if not config['log_events'].get('leaves', True):
                return

            channel = member.guild.get_channel(int(config['log_channel'])) if config['log_channel'] else None
            if not channel:
                return

            embed = discord.Embed(
                title="Member Left",
                description=f"{member.mention} ({member.name}#{member.discriminator})",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="ID", value=member.id)
            embed.add_field(name="Joined At", value=discord.utils.format_dt(member.joined_at) if member.joined_at else "Unknown")
            
            await channel.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in on_member_remove: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        config = await self.get_logging_config(before.guild.id)
        if not config['log_events'].get('roles', True):
            return

        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        if added_roles:
            embed = discord.Embed(
                title="Roles Added",
                description=f"Roles added to {after.mention}",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Added Roles", value=" ".join(role.mention for role in added_roles))
            await self.log_event(after.guild, embed)

        if removed_roles:
            embed = discord.Embed(
                title="Roles Removed",
                description=f"Roles removed from {after.mention}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Removed Roles", value=" ".join(role.mention for role in removed_roles))
            await self.log_event(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        config = await self.get_logging_config(channel.guild.id)
        if not config['log_events'].get('channels', True):
            return

        embed = discord.Embed(
            title="Channel Created",
            description=f"Channel {channel.mention} was created",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Channel Type", value=str(channel.type))
        embed.set_footer(text=f"Channel ID: {channel.id}")

        await self.log_event(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        config = await self.get_logging_config(channel.guild.id)
        if not config['log_events'].get('channels', True):
            return

        embed = discord.Embed(
            title="Channel Deleted",
            description=f"Channel #{channel.name} was deleted",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Channel Type", value=str(channel.type))
        embed.set_footer(text=f"Channel ID: {channel.id}")

        await self.log_event(channel.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not member.guild:
            return

        config = await self.get_logging_config(member.guild.id)
        if not config['log_events'].get('voice', True):
            return

        if before.channel != after.channel:
            embed = discord.Embed(
                title="Voice State Update",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Member ID: {member.id}")

            if not before.channel and after.channel:
                embed.description = f"{member.mention} joined voice channel {after.channel.mention}"
            elif before.channel and not after.channel:
                embed.description = f"{member.mention} left voice channel {before.channel.mention}"
            else:
                embed.description = f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}"

            await self.log_event(member.guild, embed)

    @app_commands.command(name="logsetup", description="Setup logging channel and configure logged events")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        messages: Optional[bool] = True,
        joins: Optional[bool] = True,
        leaves: Optional[bool] = True,
        roles: Optional[bool] = True,
        channels: Optional[bool] = True,
        voice: Optional[bool] = True
    ):
        guild_id = interaction.guild.id
        config = await self.bot.data_manager.load("guild_configs", str(guild_id))
        config['logging'] = {
            'channel': str(channel.id),
            'events': {
                'messages': messages,
                'joins': joins,
                'leaves': leaves,
                'roles': roles,
                'channels': channels,
                'voice': voice
            }
        }
        await self.bot.data_manager.save("guild_configs", str(guild_id), config)

        # Create response embed
        embed = discord.Embed(
            title="Logging Setup Complete",
            description=f"Logging channel set to {channel.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Enabled Events",
            value="\n".join([
                f"📝 Messages: {messages}",
                f"➡️ Joins: {joins}",
                f"⬅️ Leaves: {leaves}",
                f"🎭 Roles: {roles}",
                f"📺 Channels: {channels}",
                f"🔊 Voice: {voice}"
            ]),
            inline=False
        )

        await interaction.response.send_message(embed=embed)

        # Send test log
        test_embed = discord.Embed(
            title="Logging System Active",
            description="This is a test message to confirm the logging system is working.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        await channel.send(embed=test_embed)

    @app_commands.command(name="logstatus", description="View current logging settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_status(self, interaction: discord.Interaction):
        config = await self.get_logging_config(interaction.guild.id)
        channel_id = config.get('log_channel')
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None

        embed = discord.Embed(
            title="Logging Status",
            color=discord.Color.blue()
        )

        if channel:
            permissions = channel.permissions_for(interaction.guild.me)
            status = "✅ Active" if permissions.send_messages and permissions.embed_links else "⚠️ Missing Permissions"
            embed.description = f"**Current Log Channel:** {channel.mention}\n**Status:** {status}"
        else:
            embed.description = "⚠️ No logging channel set"

        events = config['log_events']
        embed.add_field(
            name="Logged Events",
            value="\n".join([
                f"{'✅' if events.get('messages', True) else '❌'} Messages",
                f"{'✅' if events.get('joins', True) else '❌'} Joins",
                f"{'✅' if events.get('leaves', True) else '❌'} Leaves",
                f"{'✅' if events.get('roles', True) else '❌'} Roles",
                f"{'✅' if events.get('channels', True) else '❌'} Channels",
                f"{'✅' if events.get('voice', True) else '❌'} Voice"
            ]),
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Logging(bot))

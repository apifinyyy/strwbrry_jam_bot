import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import datetime

class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_logging_config(self, guild_id: int):
        """Get logging configuration for a guild."""
        config = self.bot.config_manager.get_guild_config(guild_id)
        return {
            'log_channel': config.get('logging', {}).get('channel'),
            'log_events': config.get('logging', {}).get('events', {
                'messages': True,
                'joins': True,
                'leaves': True,
                'roles': True,
                'channels': True,
                'voice': True
            })
        }

    async def log_event(self, guild: discord.Guild, embed: discord.Embed):
        config = self.get_logging_config(guild.id)
        if not config['log_channel']:
            return

        channel = guild.get_channel(int(config['log_channel']))
        if channel:
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = self.get_logging_config(message.guild.id)
        if not config['log_events'].get('messages', True):
            return

        embed = discord.Embed(
            title="Message Deleted",
            description=f"Message by {message.author.mention} deleted in {message.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Content", value=message.content or "No content", inline=False)
        embed.set_footer(text=f"Author ID: {message.author.id}")

        await self.log_event(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        config = self.get_logging_config(before.guild.id)
        if not config['log_events'].get('messages', True):
            return

        embed = discord.Embed(
            title="Message Edited",
            description=f"Message by {before.author.mention} edited in {before.channel.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Before", value=before.content, inline=False)
        embed.add_field(name="After", value=after.content, inline=False)
        embed.set_footer(text=f"Author ID: {before.author.id}")

        await self.log_event(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self.get_logging_config(member.guild.id)
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
        config = self.get_logging_config(member.guild.id)
        if not config['log_events'].get('leaves', True):
            return

        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} left the server",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Joined At", value=discord.utils.format_dt(member.joined_at, style='R'))
        embed.set_footer(text=f"ID: {member.id}")

        await self.log_event(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        config = self.get_logging_config(before.guild.id)
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
        config = self.bot.config_manager.get_guild_config(guild_id)
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
        self.bot.config_manager.set_guild_config(guild_id, config)

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

async def setup(bot):
    await bot.add_cog(Logging(bot))

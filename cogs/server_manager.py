import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import asyncio
import json
import uuid
import re
import logging

class ServerManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('server_manager')
        self.server_key = "server_settings"
        self.broadcast_key = "broadcast_config"
        self.analytics_key = "broadcast_analytics"
        self.scheduled_broadcasts = {}
        self.broadcast_tasks = {}
        self.ready = asyncio.Event()
        self.config_lock = asyncio.Lock()  # Add lock for thread safety
        self.check_server_settings.start()

    async def _validate_channel_permissions(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> bool:
        """Validate bot permissions for a channel"""
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.manage_channels:
            await interaction.response.send_message(
                "❌ I need the 'Manage Channels' permission to perform this action.",
                ephemeral=True
            )
            return False
        if isinstance(channel, discord.TextChannel) and not permissions.send_messages:
            await interaction.response.send_message(
                "❌ I need permission to send messages in the target channel.",
                ephemeral=True
            )
            return False
        return True

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        """Global error handler for the cog"""
        self.logger.error(f"Error in {event}: {args} {kwargs}")

    @tasks.loop(minutes=5)
    async def check_server_settings(self):
        """Periodic check of server settings"""
        try:
            async with self.config_lock:
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                current_time = datetime.utcnow()

                # Check temporary channels
                for channel_id, expiry in list(config.get("temp_channels", {}).items()):
                    if current_time.timestamp() > expiry:
                        channel = self.bot.get_channel(int(channel_id))
                        if channel:
                            try:
                                await channel.delete(reason="Temporary channel expired")
                                del config["temp_channels"][channel_id]
                            except discord.Forbidden:
                                self.logger.warning(f"Failed to delete expired channel {channel_id}: Missing permissions")
                            except discord.NotFound:
                                del config["temp_channels"][channel_id]
                            except Exception as e:
                                self.logger.error(f"Error deleting channel {channel_id}: {e}")

                # Update server stats with rate limiting
                for guild_id, stats in config.get("server_stats", {}).items():
                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        continue

                    for stat_type, channel_id in stats.items():
                        channel = guild.get_channel(int(channel_id))
                        if not channel:
                            continue

                        try:
                            new_name = None
                            if stat_type == "member_count":
                                new_name = f"👥 Members: {guild.member_count:,}"
                            elif stat_type == "bot_count":
                                bot_count = len([m for m in guild.members if m.bot])
                                new_name = f"🤖 Bots: {bot_count:,}"
                            elif stat_type == "channel_count":
                                new_name = f"📊 Channels: {len(guild.channels):,}"
                            elif stat_type == "boost_level":
                                new_name = f"⭐ Boost Level: {guild.premium_tier}"
                            elif stat_type == "active_members":
                                active = len(await self.get_active_members(guild))
                                new_name = f"📈 Active: {active:,}"
                            elif stat_type == "role_count":
                                new_name = f"🎭 Roles: {len(guild.roles):,}"

                            if new_name and new_name != channel.name:
                                await channel.edit(name=new_name)
                                await asyncio.sleep(2)  # Rate limit protection
                        except discord.Forbidden:
                            self.logger.warning(f"Failed to update stats channel {channel_id}: Missing permissions")
                        except Exception as e:
                            self.logger.error(f"Error updating stats channel {channel_id}: {e}")

                # Check backup schedule
                for guild_id, schedule in config.get("backup_schedule", {}).items():
                    if current_time.timestamp() - schedule["last_backup"] >= schedule["interval"]:
                        guild = self.bot.get_guild(int(guild_id))
                        if guild:
                            try:
                                await self.create_backup(guild)
                            except Exception as e:
                                self.logger.error(f"Failed to create scheduled backup for guild {guild_id}: {e}")

                await self.bot.data_manager.save_json("server_config", self.server_key, config)
        except Exception as e:
            self.logger.error(f"Error in check_server_settings task: {e}")

    @commands.cooldown(1, 30, commands.BucketType.guild)
    @app_commands.command(
        name="createautochannel",
        description="Set up an auto-creating voice channel category"
    )
    @app_commands.describe(
        category_name="Name of the category to create",
        channel_template="Template for channel names (use {number} for the channel number)",
        max_channels="Maximum number of channels (default: 50)"
    )
    @app_commands.default_permissions(administrator=True)
    async def create_auto_channel(
        self,
        interaction: discord.Interaction,
        category_name: str,
        channel_template: str,
        max_channels: Optional[int] = 50
    ):
        """Set up an auto-creating voice channel category"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        if max_channels < 1 or max_channels > 100:
            await interaction.response.send_message(
                "❌ Maximum channels must be between 1 and 100",
                ephemeral=True
            )
            return

        if len(category_name) > 100:
            await interaction.response.send_message(
                "❌ Category name must be 100 characters or less",
                ephemeral=True
            )
            return

        try:
            # Check if similar category exists
            for category in interaction.guild.categories:
                if category.name.lower() == category_name.lower():
                    await interaction.response.send_message(
                        f"❌ A category named '{category_name}' already exists",
                        ephemeral=True
                    )
                    return

            # Create category with proper permissions
            category = await interaction.guild.create_category(category_name)
            channel_name = channel_template.replace("{number}", "1")
            voice_channel = await category.create_voice_channel(channel_name)

            # Set up permissions
            await voice_channel.set_permissions(
                interaction.guild.me,
                connect=True,
                manage_channels=True,
                move_members=True
            )

            async with self.config_lock:
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                guild_id = str(interaction.guild.id)
                
                if "auto_channels" not in config:
                    config["auto_channels"] = {}
                if guild_id not in config["auto_channels"]:
                    config["auto_channels"][guild_id] = {}
                    
                config["auto_channels"][guild_id][str(category.id)] = channel_template
                
                if "channel_limits" not in config:
                    config["channel_limits"] = {}
                if guild_id not in config["channel_limits"]:
                    config["channel_limits"][guild_id] = {}
                    
                config["channel_limits"][guild_id][str(category.id)] = max_channels
                
                await self.bot.data_manager.save_json("server_config", self.server_key, config)

            embed = discord.Embed(
                title="✅ Auto Channel Category Created",
                color=discord.Color.green(),
                description=f"Category: **{category_name}**\n"
                           f"Template: **{channel_template}**\n"
                           f"Max Channels: **{max_channels}**\n\n"
                           "Users joining the first channel will automatically get a new channel."
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage channels. Please check my role permissions.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error creating auto channel: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while setting up the auto channel. Please try again later.",
                ephemeral=True
            )

    @commands.cooldown(1, 10, commands.BucketType.guild)
    @app_commands.command(
        name="setserverstats",
        description="Set up server statistics channels"
    )
    @app_commands.describe(
        stat_type="Type of statistic to display",
        channel="Optional: Existing voice channel to use (creates new if not specified)"
    )
    @app_commands.choices(stat_type=[
        app_commands.Choice(name="Member Count", value="member_count"),
        app_commands.Choice(name="Bot Count", value="bot_count"),
        app_commands.Choice(name="Channel Count", value="channel_count"),
        app_commands.Choice(name="Boost Level", value="boost_level"),
        app_commands.Choice(name="Active Members", value="active_members"),
        app_commands.Choice(name="Role Count", value="role_count")
    ])
    @app_commands.default_permissions(administrator=True)
    async def set_server_stats(
        self,
        interaction: discord.Interaction,
        stat_type: str,
        channel: Optional[discord.VoiceChannel] = None
    ):
        """Set up server statistics channels"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            async with self.config_lock:
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                guild_id = str(interaction.guild.id)
                
                if "server_stats" not in config:
                    config["server_stats"] = {}
                if guild_id not in config["server_stats"]:
                    config["server_stats"][guild_id] = {}

                # Create or get channel
                if not channel:
                    # Look for existing stats category
                    stats_category = discord.utils.get(interaction.guild.categories, name="📊 Server Stats")
                    if not stats_category:
                        stats_category = await interaction.guild.create_category("📊 Server Stats")
                        # Move category to top
                        await stats_category.edit(position=0)

                    channel = await stats_category.create_voice_channel("Loading...")
                    await channel.set_permissions(
                        interaction.guild.default_role,
                        connect=False,
                        view_channel=True
                    )

                if not await self._validate_channel_permissions(interaction, channel):
                    return

                # Remove stat_type from any other channel to avoid duplicates
                for ch_id, stat in list(config["server_stats"][guild_id].items()):
                    if stat == stat_type:
                        del config["server_stats"][guild_id][ch_id]

                config["server_stats"][guild_id][str(channel.id)] = stat_type
                await self.bot.data_manager.save_json("server_config", self.server_key, config)

                # Update channel immediately
                stat_names = {
                    "member_count": ("👥 Members", interaction.guild.member_count),
                    "bot_count": ("🤖 Bots", len([m for m in interaction.guild.members if m.bot])),
                    "channel_count": ("📊 Channels", len(interaction.guild.channels)),
                    "boost_level": ("⭐ Boost Level", interaction.guild.premium_tier),
                    "active_members": ("📈 Active", len(await self.get_active_members(interaction.guild))),
                    "role_count": ("🎭 Roles", len(interaction.guild.roles))
                }

                name, value = stat_names[stat_type]
                await channel.edit(name=f"{name}: {value:,}")

                embed = discord.Embed(
                    title="✅ Server Stats Channel Set Up",
                    color=discord.Color.green(),
                    description=f"Statistic: **{name}**\n"
                               f"Channel: {channel.mention}\n"
                               f"Current Value: **{value:,}**\n\n"
                               "The channel will update automatically every 5 minutes."
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage channels. Please check my role permissions.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error setting up stats channel: {e}")
            await interaction.followup.send(
                "❌ An error occurred while setting up the stats channel. Please try again later.",
                ephemeral=True
            )

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self.init_data()
        await self._init_broadcast_data()
        self.ready.set()

    async def init_data(self):
        """Initialize server configuration"""
        if not await self.bot.data_manager.exists("server_config", key=self.server_key):
            default_config = {
                "welcome_channel": None,
                "log_channel": None,
                "mod_role": None,
                "mute_role": None,
                "auto_roles": [],
                "prefix": "!",
                "locale": "en_US",
                "timezone": "UTC",
                "auto_channels": {},    # guild_id -> {category_id: template}
                "temp_channels": {},    # channel_id -> expiry_time
                "channel_limits": {},   # guild_id -> {category_id: max_channels}
                "channel_perms": {},    # guild_id -> {role_id: {channel_type: perms}}
                "server_stats": {},     # guild_id -> {setting: channel_id}
                "audit_log": {},        # guild_id -> {channel_id, filters}
                "cleanup_rules": {},    # guild_id -> {channel_id: {max_age, exempt_roles}}
                "activity_tracking": {},# guild_id -> {hour: activity_count}
                "milestones": {},       # guild_id -> {milestone_type: last_value}
                "backups": {},          # guild_id -> {timestamp: backup_data}
                "backup_schedule": {},   # guild_id -> {interval, last_backup}
                "broadcasts": {         # Merged from broadcast.py
                    "templates": {},    # template_name -> message_template
                    "schedules": {},    # schedule_id -> {channel_id, template, interval}
                    "channels": {},     # channel_id -> {enabled: bool, filters: []}
                    "history": {},      # message_id -> {template, timestamp}
                    "settings": {
                        "max_history": 100,
                        "default_interval": 3600,
                        "rate_limit": 5
                    }
                }
            }
            await self.bot.data_manager.save_json("server_config", self.server_key, default_config)

    async def _init_broadcast_data(self):
        """Initialize broadcast analytics"""
        if not await self.bot.data_manager.exists(self.analytics_key):
            await self.bot.data_manager.save(self.analytics_key, 'default', {
                "broadcasts": {},
                "server_stats": {},
                "global_stats": {
                    "total_broadcasts": 0,
                    "total_reach": 0,
                    "most_active_hour": None,
                    "avg_engagement": 0
                }
            })

    async def get_active_members(self, guild: discord.Guild) -> list:
        """Get list of members active in the last 24 hours"""
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        active_members = set()
        
        for channel in guild.text_channels:
            try:
                async for message in channel.history(after=one_day_ago):
                    active_members.add(message.author.id)
            except discord.Forbidden:
                continue
                
        return list(active_members)

    @commands.cooldown(1, 30, commands.BucketType.guild)
    @app_commands.command(
        name="setauditlog",
        description="Set up audit logging"
    )
    @app_commands.describe(
        channel="The channel to send audit log messages to",
        events="Comma-separated list of events to log (e.g., 'messages,roles,channels') or 'all'"
    )
    @app_commands.choices(events=[
        app_commands.Choice(name="All Events", value="all"),
        app_commands.Choice(name="Messages Only", value="messages"),
        app_commands.Choice(name="Roles Only", value="roles"),
        app_commands.Choice(name="Channels Only", value="channels"),
        app_commands.Choice(name="Members Only", value="members"),
        app_commands.Choice(name="Server Only", value="server")
    ])
    @app_commands.default_permissions(administrator=True)
    async def set_audit_log(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        events: str = "all"
    ):
        """Set up audit logging"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        if not await self._validate_channel_permissions(interaction, channel):
            return

        try:
            async with self.config_lock:
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                guild_id = str(interaction.guild_id)
                
                if "audit_log" not in config:
                    config["audit_log"] = {}

                # Validate events
                valid_events = {"messages", "roles", "channels", "members", "server"}
                if events != "all":
                    event_list = [e.strip().lower() for e in events.split(',')]
                    invalid_events = [e for e in event_list if e not in valid_events]
                    if invalid_events:
                        await interaction.response.send_message(
                            f"❌ Invalid event types: {', '.join(invalid_events)}\n"
                            f"Valid events are: {', '.join(valid_events)}",
                            ephemeral=True
                        )
                        return
                
                config["audit_log"][guild_id] = {
                    "channel_id": str(channel.id),
                    "filters": events.split(',') if events != "all" else "all"
                }
                
                await self.bot.data_manager.save_json("server_config", self.server_key, config)
                
                # Set up channel permissions
                try:
                    await channel.set_permissions(
                        interaction.guild.me,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "⚠️ Could not set up channel permissions. Please ensure I have the 'Manage Channels' permission.",
                        ephemeral=True
                    )
                    return

                embed = discord.Embed(
                    title="✅ Audit Log Channel Set Up",
                    color=discord.Color.green(),
                    description=f"Channel: {channel.mention}\n"
                               f"Events: **{events}**\n\n"
                               "I will now log all specified events to this channel."
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)

                # Send test message to audit log
                try:
                    test_embed = discord.Embed(
                        title="🔍 Audit Log Initialized",
                        color=discord.Color.blue(),
                        description="The audit log has been set up successfully. You will see event logs appear here.",
                        timestamp=datetime.utcnow()
                    )
                    test_embed.add_field(
                        name="Configured Events",
                        value=events if events != "all" else "All events will be logged",
                        inline=False
                    )
                    await channel.send(embed=test_embed)
                except discord.Forbidden:
                    await interaction.followup.send(
                        "⚠️ Could not send test message to the audit log channel. Please check my permissions.",
                        ephemeral=True
                    )

        except Exception as e:
            self.logger.error(f"Error setting up audit log: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while setting up the audit log. Please try again later.",
                ephemeral=True
            )

    @commands.cooldown(1, 30, commands.BucketType.guild)
    @app_commands.command(
        name="setupbackup",
        description="Set up automatic server backups"
    )
    @app_commands.describe(
        interval="How often to create backups (in hours)",
        max_backups="Maximum number of backups to keep (default: 5)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_backup(
        self,
        interaction: discord.Interaction,
        interval: int,
        max_backups: Optional[int] = 5
    ):
        """Set up automatic server backups"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        if interval < 1 or interval > 168:  # 1 week max
            await interaction.response.send_message(
                "❌ Backup interval must be between 1 and 168 hours (1 week)",
                ephemeral=True
            )
            return

        if max_backups < 1 or max_backups > 10:
            await interaction.response.send_message(
                "❌ Maximum backups must be between 1 and 10",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            async with self.config_lock:
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                guild_id = str(interaction.guild_id)
                
                if "backup_schedule" not in config:
                    config["backup_schedule"] = {}
                    
                config["backup_schedule"][guild_id] = {
                    "interval": interval * 3600,  # convert to seconds
                    "last_backup": 0,  # force immediate backup
                    "max_backups": max_backups
                }
                
                await self.bot.data_manager.save_json("server_config", self.server_key, config)
                
                # Create initial backup
                backup_result = await self.create_backup(interaction.guild)
                
                if backup_result:
                    embed = discord.Embed(
                        title="✅ Server Backup Schedule Set",
                        color=discord.Color.green(),
                        description=f"Frequency: Every **{interval}** hours\n"
                                   f"Max Backups: **{max_backups}**\n\n"
                                   "✅ Initial backup created successfully!\n"
                                   "Use `/listbackups` to view available backups."
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "⚠️ Backup schedule set up, but initial backup failed. Please try `/createbackup` manually.",
                        ephemeral=True
                    )
        except Exception as e:
            self.logger.error(f"Error setting up backup schedule: {e}")
            await interaction.followup.send(
                "❌ An error occurred while setting up the backup schedule. Please try again later.",
                ephemeral=True
            )

    @commands.cooldown(1, 300, commands.BucketType.guild)  # 5 minutes cooldown
    @app_commands.command(
        name="createbackup",
        description="Create a manual server backup"
    )
    @app_commands.default_permissions(administrator=True)
    async def manual_backup(self, interaction: discord.Interaction):
        """Create a manual server backup"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            backup = await self.create_backup(interaction.guild)
            if backup:
                embed = discord.Embed(
                    title="✅ Server Backup Created",
                    color=discord.Color.green(),
                    description="Server backup created successfully!\n"
                               "Use `/listbackups` to view all available backups."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Failed to create backup. Please check the bot's permissions.",
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"Error creating manual backup: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating the backup. Please try again later.",
                ephemeral=True
            )

    @commands.cooldown(1, 10, commands.BucketType.guild)
    @app_commands.command(
        name="listbackups",
        description="List available server backups"
    )
    @app_commands.default_permissions(administrator=True)
    async def list_backups(self, interaction: discord.Interaction):
        """List available server backups"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return

        try:
            config = await self.bot.data_manager.load_json("server_config", self.server_key)
            guild_id = str(interaction.guild_id)
            
            if guild_id not in config.get("backups", {}) or not config["backups"][guild_id]:
                await interaction.response.send_message(
                    "❌ No backups found for this server. Use `/createbackup` to create one.",
                    ephemeral=True
                )
                return
            
            backups = config["backups"][guild_id]
            backup_list = []
            
            for timestamp in sorted(backups.keys(), reverse=True):
                try:
                    backup_time = datetime.fromisoformat(timestamp)
                    backup_data = backups[timestamp]
                    role_count = len(backup_data["roles"])
                    channel_count = sum(len(cat["channels"]) for cat in backup_data["categories"])
                    
                    backup_list.append(
                        f"📅 **{backup_time.strftime('%Y-%m-%d %H:%M UTC')}**\n"
                        f"└ {role_count} roles, {channel_count} channels"
                    )
                except (ValueError, KeyError):
                    continue
            
            if not backup_list:
                await interaction.response.send_message(
                    "❌ No valid backups found. Use `/createbackup` to create one.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="📦 Server Backups",
                color=discord.Color.blue(),
                description="\n\n".join(backup_list[:10])  # Show last 10 backups
            )
            
            if len(backup_list) > 10:
                embed.set_footer(text=f"Showing 10 most recent backups of {len(backup_list)} total")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error listing backups: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing backups. Please try again later.",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        """Handle auto voice channels"""
        config = await self.bot.data_manager.load_json("server_config", self.server_key)
        guild_id = str(member.guild.id)
        
        if guild_id not in config.get("auto_channels", {}):
            return
        
        # Handle channel creation
        if after.channel:
            category_id = str(after.channel.category_id)
            if category_id in config["auto_channels"][guild_id]:
                template = config["auto_channels"][guild_id][category_id]
                category = after.channel.category
                
                # Count existing channels
                existing = len(category.channels)
                
                # Check if we need a new channel
                all_empty = all(
                    len(vc.members) > 0 for vc in category.voice_channels
                )
                
                if all_empty and existing < config["channel_limits"][guild_id].get(category_id, 50):
                    try:
                        await category.create_voice_channel(
                            f"{template} {existing + 1}"
                        )
                    except discord.Forbidden:
                        pass
        
        # Handle channel deletion
        if before.channel:
            category_id = str(before.channel.category_id)
            if category_id in config.get("auto_channels", {}).get(guild_id, {}):
                if not before.channel.members:
                    # Don't delete the last channel
                    if len(before.channel.category.channels) > 1:
                        try:
                            await before.channel.delete()
                        except discord.Forbidden:
                            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Log channel creation"""
        await self.log_audit_event(
            channel.guild,
            "channel_create",
            f"Channel {channel.mention} was created"
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Log channel deletion"""
        await self.log_audit_event(
            channel.guild,
            "channel_delete",
            f"Channel #{channel.name} was deleted"
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel
    ):
        """Log channel updates"""
        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if isinstance(before, discord.TextChannel):
            if before.topic != after.topic:
                changes.append(f"Topic changed")
        
        if changes:
            await self.log_audit_event(
                after.guild,
                "channel_update",
                f"Channel {after.mention} was updated:\n" + "\n".join(changes)
            )

    async def log_audit_event(
        self,
        guild: discord.Guild,
        event_type: str,
        message: str
    ):
        """Log an audit event"""
        config = await self.bot.data_manager.load_json("server_config", self.server_key)
        guild_id = str(guild.id)
        
        if guild_id not in config.get("audit_log", {}):
            return
            
        audit_config = config["audit_log"][guild_id]
        if audit_config["filters"] != "all" and event_type not in audit_config["filters"]:
            return
            
        channel = guild.get_channel(int(audit_config["channel_id"]))
        if channel:
            embed = discord.Embed(
                title="📝 Audit Log",
                description=message,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Event Type: {event_type}")
            
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # Broadcast Commands
    @app_commands.command(name="broadcast")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def broadcast(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
        role: Optional[discord.Role] = None,
        schedule: Optional[str] = None
    ):
        """
        Send or schedule a broadcast message
        
        Args:
            message: The message to broadcast
            channel: Target channel (optional, defaults to current)
            role: Mention a role (optional)
            schedule: Schedule timing (e.g. "daily 9:00", "weekly mon 15:00")
        """
        try:
            target_channel = channel or interaction.channel
            
            # Create embed
            embed = discord.Embed(
                title="📢 Server Broadcast",
                description=message,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if role:
                content = role.mention
            else:
                content = None
                
            # Handle scheduling
            if schedule:
                schedule_id = str(uuid.uuid4())
                broadcast_data = {
                    "channel_id": target_channel.id,
                    "message": message,
                    "role_id": role.id if role else None,
                    "schedule": schedule,
                    "last_sent": None
                }
                
                config = await self.bot.data_manager.load_json("server_config", self.server_key)
                config["broadcasts"]["schedules"][schedule_id] = broadcast_data
                await self.bot.data_manager.save_json("server_config", self.server_key, config)
                
                await interaction.response.send_message(
                    f"✅ Broadcast scheduled in {target_channel.mention}!",
                    ephemeral=True
                )
            else:
                # Send immediate broadcast
                await target_channel.send(content=content, embed=embed)
                await interaction.response.send_message(
                    f"✅ Broadcast sent to {target_channel.mention}!",
                    ephemeral=True
                )
                
            # Update analytics
            await self._update_broadcast_stats(
                str(interaction.guild_id),
                True,
                len(interaction.guild.members)
            )
            
        except Exception as e:
            self.logger.error(f"Error in broadcast command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ Failed to send broadcast. Please check my permissions and try again.",
                ephemeral=True
            )

    @app_commands.command(name="listbroadcasts")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def list_broadcasts(self, interaction: discord.Interaction):
        """List all scheduled broadcasts"""
        config = await self.bot.data_manager.load_json("server_config", self.server_key)
        schedules = config["broadcasts"]["schedules"]
        
        if not schedules:
            await interaction.response.send_message(
                "No scheduled broadcasts found.",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="📢 Scheduled Broadcasts",
            color=discord.Color.blue()
        )
        
        for schedule_id, data in schedules.items():
            channel = self.bot.get_channel(data["channel_id"])
            channel_name = channel.mention if channel else "Unknown Channel"
            
            embed.add_field(
                name=f"ID: {schedule_id[:8]}",
                value=f"Channel: {channel_name}\nSchedule: {data['schedule']}\nMessage: {data['message'][:50]}...",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="cancelbroadcast")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def cancel_broadcast(
        self,
        interaction: discord.Interaction,
        schedule_id: str
    ):
        """
        Cancel a scheduled broadcast
        
        Args:
            schedule_id: ID of the scheduled broadcast
        """
        config = await self.bot.data_manager.load_json("server_config", self.server_key)
        
        if schedule_id in config["broadcasts"]["schedules"]:
            del config["broadcasts"]["schedules"][schedule_id]
            await self.bot.data_manager.save_json("server_config", self.server_key, config)
            
            await interaction.response.send_message(
                "✅ Broadcast cancelled successfully!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Broadcast schedule not found.",
                ephemeral=True
            )

    async def _update_broadcast_stats(self, guild_id: str, success: bool, member_count: int):
        """Update broadcast analytics"""
        analytics = await self.bot.data_manager.load(self.analytics_key)
        
        if guild_id not in analytics["server_stats"]:
            analytics["server_stats"][guild_id] = {
                "total_broadcasts": 0,
                "successful_broadcasts": 0,
                "failed_broadcasts": 0,
                "total_reach": 0,
                "last_broadcast": None
            }
        
        stats = analytics["server_stats"][guild_id]
        stats["total_broadcasts"] += 1
        if success:
            stats["successful_broadcasts"] += 1
            stats["total_reach"] += member_count
        else:
            stats["failed_broadcasts"] += 1
        stats["last_broadcast"] = datetime.utcnow().isoformat()
        
        await self.bot.data_manager.save(self.analytics_key, analytics)

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(ServerManager(bot))

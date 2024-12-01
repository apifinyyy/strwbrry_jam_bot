import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from collections import defaultdict
import re
import time
import asyncio
import logging
from copy import deepcopy

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.automod_key = "automod_config"
        self.message_trackers: Dict[str, Dict[str, List[float]]] = {}
        self.join_trackers: Dict[str, List[float]] = {}
        self._tracker_lock = asyncio.Lock()
        self.cleanup_trackers.start()
        self._config_cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update = {}
        self.logger = logging.getLogger('automod')

    def get_safe_default_config(self) -> dict:
        """Return safe default configuration"""
        return {
            "enabled": False,
            "spam_settings": {
                "message_threshold": 5,
                "time_window": 5,
                "mention_limit": 5,
                "repeat_threshold": 3,
                "punishment": "timeout",
                "duration": 300
            },
            "raid_settings": {
                "join_threshold": 10,
                "join_window": 60,
                "account_age": 86400,
                "action": "lockdown",
                "duration": 300
            },
            "quiet_hours": {
                "enabled": False,
                "start": "22:00",
                "end": "08:00",
                "stricter_limits": True
            },
            "log_channel": None,
            "exempt_roles": [],
            "content_filter": {
                "enabled": False,
                "blocked_words": [],
                "blocked_patterns": [],
                "url_whitelist": [],
                "invite_whitelist": [],
                "punishment": "delete"
            }
        }

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self.init_data()

    async def init_data(self):
        """Initialize automod configuration"""
        if not await self.bot.data_manager.exists("automod", self.automod_key):
            await self.bot.data_manager.save_json("automod", self.automod_key, {
                "default": self.get_safe_default_config()
            })

    async def get_guild_config(self, guild_id: int) -> dict:
        """Get guild-specific automod configuration."""
        try:
            config = await self.bot.data_manager.load_json("automod", str(guild_id))
            if not config:
                # Create new config with enabled features
                new_config = {
                    "enabled": True,
                    "spam_settings": {
                        "message_threshold": 5,
                        "time_window": 5,
                        "mention_limit": 5,
                        "repeat_threshold": 3,
                        "punishment": "timeout",
                        "duration": 300
                    },
                    "raid_settings": {
                        "join_threshold": 10,
                        "join_window": 60,
                        "account_age": 86400,
                        "action": "lockdown",
                        "duration": 300
                    },
                    "quiet_hours": {
                        "enabled": False,
                        "start": "22:00",
                        "end": "08:00",
                        "stricter_limits": True
                    },
                    "log_channel": None,  # Will be set via command
                    "exempt_roles": [],
                    "content_filter": {
                        "enabled": True,
                        "blocked_words": [],
                        "blocked_patterns": [],
                        "url_whitelist": [],
                        "invite_whitelist": [],
                        "punishment": "delete"
                    }
                }
                
                await self.bot.data_manager.save_json("automod", str(guild_id), {"default": new_config})
                return new_config
            
            return config.get("default", self.get_safe_default_config())
        except Exception as e:
            self.logger.error(f"Error loading automod config for guild {guild_id}: {e}")
            return self.get_safe_default_config()

    async def get_config(self, guild_id: str) -> dict:
        """Get guild-specific or default config with caching and error handling"""
        try:
            # Check cache first
            current_time = time.time()
            if guild_id in self._config_cache:
                if current_time - self._last_cache_update.get(guild_id, 0) < self._cache_ttl:
                    return deepcopy(self._config_cache[guild_id])

            config = await self.get_guild_config(int(guild_id))
            
            # Update cache
            self._config_cache[guild_id] = config
            self._last_cache_update[guild_id] = current_time
            
            return config
        except Exception as e:
            self.logger.error(f"Error loading config for guild {guild_id}: {e}")
            return self.get_safe_default_config()

    async def check_content(self, message: discord.Message, settings: dict) -> tuple[bool, str]:
        """Check message content against filters with error handling"""
        try:
            content = message.content.lower()
            
            # Check blocked words
            for word in settings.get("blocked_words", []):
                if word.lower() in content:
                    return True, f"Blocked word: {word}"
            
            # Check regex patterns with timeout protection
            for pattern in settings.get("blocked_patterns", []):
                try:
                    if re.search(pattern, content, re.IGNORECASE, timeout=1.0):
                        return True, f"Matched pattern: {pattern}"
                except (re.error, TimeoutError):
                    self.logger.warning(f"Invalid or slow regex pattern: {pattern}")
                    continue
            
            # Check URLs
            urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', content)
            if urls and settings.get("url_whitelist"):
                for url in urls:
                    if not any(whitelist in url for whitelist in settings["url_whitelist"]):
                        return True, "Non-whitelisted URL"
            
            # Check Discord invites
            invites = re.findall(r'discord\.gg/\S+', content)
            if invites and settings.get("invite_whitelist"):
                for invite in invites:
                    if not any(whitelist in invite for whitelist in settings["invite_whitelist"]):
                        return True, "Non-whitelisted Discord invite"
            
            return False, ""
        except Exception as e:
            self.logger.error(f"Error in content check: {e}")
            return False, ""

    async def handle_violation(self, message: discord.Message, member: discord.Member, punishment: str, reason: str):
        """Handle content filter violations"""
        try:
            # Delete message
            await message.delete()
            
            # Apply punishment
            if punishment == "timeout":
                await member.timeout(timedelta(minutes=5), reason=reason)
            elif punishment == "kick":
                await member.kick(reason=reason)
            elif punishment == "ban":
                await member.ban(reason=reason, delete_message_days=1)
            
            # Log violation
            config = await self.get_config(str(message.guild.id))
            if config["log_channel"]:
                channel = message.guild.get_channel(int(config["log_channel"]))
                if channel:
                    embed = discord.Embed(
                        title="🛡️ Content Filter Violation",
                        description=f"Action taken against {member.mention}",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="Reason", value=reason)
                    embed.add_field(name="Action", value=punishment)
                    await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error handling violation: {e}")

    @app_commands.command(name="filter")
    @app_commands.describe(
        action="Action to perform",
        filter_type="Type of filter to modify",
        value="Value to add/remove"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="list", value="list")
        ],
        filter_type=[
            app_commands.Choice(name="word", value="blocked_words"),
            app_commands.Choice(name="pattern", value="blocked_patterns"),
            app_commands.Choice(name="url", value="url_whitelist"),
            app_commands.Choice(name="invite", value="invite_whitelist")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def filter_config(
        self,
        interaction: discord.Interaction,
        action: str,
        filter_type: str,
        value: Optional[str] = None
    ):
        """Configure content filter settings"""
        config = await self.get_config(str(interaction.guild_id))
        
        if action == "list":
            items = config["content_filter"][filter_type]
            if not items:
                await interaction.response.send_message(f"No items in {filter_type}", ephemeral=True)
                return
                
            embed = discord.Embed(
                title=f"Content Filter - {filter_type}",
                description="\n".join(f"• {item}" for item in items),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        if not value:
            await interaction.response.send_message("❌ Please provide a value", ephemeral=True)
            return
            
        try:
            if action == "add":
                if value not in config["content_filter"][filter_type]:
                    config["content_filter"][filter_type].append(value)
            else:  # remove
                if value in config["content_filter"][filter_type]:
                    config["content_filter"][filter_type].remove(value)
                    
            await self.bot.data_manager.save_json("automod", self.automod_key, config)
            await interaction.response.send_message(
                f"✅ Successfully {action}ed {value} to {filter_type}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating filter: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="automod")
    @app_commands.describe(
        action="The action to perform",
        setting="The setting to configure",
        value="The value to set"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Configure Settings", value="config"),
            app_commands.Choice(name="View Settings", value="view")
        ],
        setting=[
            app_commands.Choice(name="Enable/Disable AutoMod", value="enabled"),
            app_commands.Choice(name="Spam Protection", value="spam_settings"),
            app_commands.Choice(name="Raid Protection", value="raid_settings"),
            app_commands.Choice(name="Quiet Hours", value="quiet_hours"),
            app_commands.Choice(name="Log Channel", value="log_channel"),
            app_commands.Choice(name="Content Filter", value="content_filter")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def automod_config(
        self,
        interaction: discord.Interaction,
        action: str,
        setting: Optional[str] = None,
        value: Optional[str] = None
    ):
        """Configure AutoMod settings for your server"""
        try:
            # Verify bot permissions first
            if not interaction.guild.me.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ I need the 'Manage Messages' permission to moderate messages",
                    ephemeral=True
                )
                return

            config = await self.get_config(str(interaction.guild_id))
            
            if action == "view":
                embed = discord.Embed(
                    title="🛡️ AutoMod Configuration",
                    description="Current AutoMod settings for your server",
                    color=discord.Color.blue()
                )
                
                # Status
                embed.add_field(
                    name="Status",
                    value="✅ Enabled" if config["enabled"] else "❌ Disabled",
                    inline=False
                )
                
                # Spam Protection
                spam = config["spam_settings"]
                embed.add_field(
                    name="🔄 Spam Protection",
                    value=f"• Max Messages: {spam['message_threshold']} in {spam['time_window']}s\n"
                          f"• Max Mentions: {spam['mention_limit']} per message\n"
                          f"• Repeat Limit: {spam['repeat_threshold']} messages\n"
                          f"• Punishment: {spam['punishment']} ({spam['duration']}s)",
                    inline=False
                )
                
                # Raid Protection
                raid = config["raid_settings"]
                embed.add_field(
                    name="🛡️ Raid Protection",
                    value=f"• Join Threshold: {raid['join_threshold']} in {raid['join_window']}s\n"
                          f"• Min Account Age: {raid['account_age']}s\n"
                          f"• Action: {raid['action']} ({raid['duration']}s)",
                    inline=False
                )
                
                # Quiet Hours
                quiet = config["quiet_hours"]
                embed.add_field(
                    name="🌙 Quiet Hours",
                    value=f"• Status: {'✅ Enabled' if quiet['enabled'] else '❌ Disabled'}\n"
                          f"• Time: {quiet['start']} - {quiet['end']}\n"
                          f"• Stricter Limits: {'Yes' if quiet['stricter_limits'] else 'No'}",
                    inline=False
                )
                
                # Content Filter
                filter_config = config["content_filter"]
                embed.add_field(
                    name="🔍 Content Filter",
                    value=f"• Status: {'✅ Enabled' if filter_config['enabled'] else '❌ Disabled'}\n"
                          f"• Blocked Words: {len(filter_config['blocked_words'])}\n"
                          f"• Blocked Patterns: {len(filter_config['blocked_patterns'])}\n"
                          f"• URL Whitelist: {len(filter_config['url_whitelist'])}\n"
                          f"• Invite Whitelist: {len(filter_config['invite_whitelist'])}\n"
                          f"• Punishment: {filter_config['punishment']}",
                    inline=False
                )
                
                # Log Channel
                log_channel = config["log_channel"]
                embed.add_field(
                    name="📝 Log Channel",
                    value=f"<#{log_channel}>" if log_channel else "Not set",
                    inline=False
                )
                
                embed.set_footer(text="Use /automod config to modify these settings")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            elif action == "config":
                if not setting or not value:
                    await interaction.response.send_message(
                        "❌ Please provide both a setting and value to configure",
                        ephemeral=True
                    )
                    return
                
                try:
                    # Special handling for enable/disable setting
                    if setting == "enabled":
                        if value.lower() not in ['true', 'false']:
                            await interaction.response.send_message(
                                "❌ Value must be 'true' or 'false'",
                                ephemeral=True
                            )
                            return
                        new_value = value.lower() == 'true'
                        if new_value == config["enabled"]:
                            status = "enabled" if new_value else "disabled"
                            await interaction.response.send_message(
                                f"ℹ️ AutoMod is already {status}",
                                ephemeral=True
                            )
                            return
                        config["enabled"] = new_value
                        await self.bot.data_manager.save_json("automod", self.automod_key, config)
                        status = "enabled" if new_value else "disabled"
                        await interaction.response.send_message(
                            f"✅ AutoMod has been {status}. Use `/automod view` to see current settings.",
                            ephemeral=True
                        )
                        return
                    
                    parts = setting.split('.')
                    current = config
                    
                    # Navigate to the nested setting
                    for part in parts[:-1]:
                        current = current[part]
                    
                    old_value = current[parts[-1]]
                    
                    # Convert and validate value based on setting type
                    if isinstance(old_value, bool):
                        if value.lower() not in ['true', 'false']:
                            await interaction.response.send_message(
                                "❌ Value must be 'true' or 'false'",
                                ephemeral=True
                            )
                            return
                        current[parts[-1]] = value.lower() == 'true'
                    
                    elif isinstance(old_value, int):
                        try:
                            new_value = int(value)
                            if new_value < 0:
                                await interaction.response.send_message(
                                    "❌ Value cannot be negative",
                                    ephemeral=True
                                )
                                return
                            current[parts[-1]] = new_value
                        except ValueError:
                            await interaction.response.send_message(
                                "❌ Value must be a number",
                                ephemeral=True
                            )
                            return
                    
                    elif parts[-1] == 'punishment':
                        if value not in ['delete', 'timeout', 'kick', 'ban']:
                            await interaction.response.send_message(
                                "❌ Punishment must be one of: delete, timeout, kick, ban",
                                ephemeral=True
                            )
                            return
                        current[parts[-1]] = value
                    
                    elif parts[-1] == 'log_channel':
                        # Handle log channel configuration
                        if value.lower() == 'none':
                            current[parts[-1]] = None
                        else:
                            # Extract channel ID from mention or raw ID
                            channel_id = ''.join(filter(str.isdigit, value))
                            if not channel_id:
                                await interaction.response.send_message(
                                    "❌ Please provide a valid channel ID or mention",
                                    ephemeral=True
                                )
                                return

                            # Verify channel exists and bot has permissions
                            channel = interaction.guild.get_channel(int(channel_id))
                            if not channel:
                                await interaction.response.send_message(
                                    "❌ Channel not found in this server",
                                    ephemeral=True
                                )
                                return

                            # Check if it's a text channel
                            if not isinstance(channel, discord.TextChannel):
                                await interaction.response.send_message(
                                    "❌ The log channel must be a text channel",
                                    ephemeral=True
                                )
                                return

                            # Check bot permissions in the channel
                            bot_permissions = channel.permissions_for(interaction.guild.me)
                            if not (bot_permissions.send_messages and bot_permissions.embed_links):
                                await interaction.response.send_message(
                                    "❌ I need 'Send Messages' and 'Embed Links' permissions in the log channel",
                                    ephemeral=True
                                )
                                return

                            current[parts[-1]] = channel_id

                        await self.bot.data_manager.save_json("automod", self.automod_key, config)
                        
                        # Create confirmation message
                        if current[parts[-1]] is None:
                            confirm_msg = "✅ Logging channel has been disabled"
                        else:
                            channel = interaction.guild.get_channel(int(current[parts[-1]]))
                            confirm_msg = f"✅ Set logging channel to {channel.mention}"
                            
                            # Send test message to verify
                            try:
                                test_embed = discord.Embed(
                                    title="🛡️ Logging Channel Test",
                                    description="This is a test message to confirm the logging channel is working correctly.",
                                    color=discord.Color.green()
                                )
                                await channel.send(embed=test_embed)
                            except Exception as e:
                                self.logger.error(f"Error sending test message: {e}")
                                confirm_msg += "\n⚠️ Warning: Failed to send test message. Please check channel permissions."

                        await interaction.response.send_message(confirm_msg, ephemeral=True)
                        return
                    
                    elif isinstance(old_value, str):
                        current[parts[-1]] = value
                    
                    await self.bot.data_manager.save_json("automod", self.automod_key, config)
                    await interaction.response.send_message(
                        f"✅ Updated {setting} from `{old_value}` to `{current[parts[-1]]}`",
                        ephemeral=True
                    )
                
                except KeyError:
                    await interaction.response.send_message(
                        f"❌ Invalid setting: {setting}",
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.error(f"Error updating setting: {e}")
                    await interaction.response.send_message(
                        "❌ An error occurred while updating the setting",
                        ephemeral=True
                    )
        
        except Exception as e:
            self.logger.error(f"Error in automod_config command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your request",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle message moderation with improved error handling and thread safety"""
        if not message.guild or message.author.bot:
            return
            
        try:
            # Check bot permissions first
            if not message.guild.me.guild_permissions.moderate_members:
                return

            config = await self.get_config(str(message.guild.id))
            if not config["enabled"]:
                return

            # Check member permissions
            member = message.guild.get_member(message.author.id)
            if not member:
                return

            # Check exemptions
            if any(role.id in config.get("exempt_roles", []) for role in member.roles):
                return

            # Content filter check
            if config.get("content_filter", {}).get("enabled", False):
                violated, reason = await self.check_content(message, config["content_filter"])
                if violated:
                    await self.handle_violation(message, member, config["content_filter"]["punishment"], reason)
                    return

            # Message tracking with thread safety
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)
            current_time = time.time()
            
            async with self._tracker_lock:
                # Initialize trackers if needed
                if guild_id not in self.message_trackers:
                    self.message_trackers[guild_id] = {}
                if user_id not in self.message_trackers[guild_id]:
                    self.message_trackers[guild_id][user_id] = []
                
                # Add message and trim old ones
                self.message_trackers[guild_id][user_id].append(current_time)
                
                # Keep only recent messages within window
                window = config["spam_settings"]["time_window"]
                self.message_trackers[guild_id][user_id] = [
                    ts for ts in self.message_trackers[guild_id][user_id]
                    if current_time - ts <= window
                ][-50:]  # Keep only last 50 messages
                
                recent_messages = self.message_trackers[guild_id][user_id]

            # Get settings with quiet hours adjustment
            settings = deepcopy(config["spam_settings"])
            
            if config.get("quiet_hours", {}).get("enabled", False):
                current_hour = datetime.utcnow().hour
                try:
                    start_hour = int(config["quiet_hours"]["start"].split(":")[0])
                    end_hour = int(config["quiet_hours"]["end"].split(":")[0])
                    
                    is_quiet_hours = False
                    if start_hour > end_hour:  # Crosses midnight
                        is_quiet_hours = current_hour >= start_hour or current_hour < end_hour
                    else:
                        is_quiet_hours = start_hour <= current_hour < end_hour
                        
                    if is_quiet_hours and config["quiet_hours"].get("stricter_limits", True):
                        settings["message_threshold"] = max(1, settings["message_threshold"] // 2)
                        settings["mention_limit"] = max(1, settings["mention_limit"] // 2)
                except (ValueError, KeyError):
                    self.logger.error("Invalid quiet hours configuration")

            # Check violations
            should_punish = False
            reason = None

            # Message count check
            if len(recent_messages) > settings["message_threshold"]:
                should_punish = True
                reason = f"Sending messages too quickly ({len(recent_messages)} in {settings['time_window']}s)"

            # Mention check
            elif len(message.mentions) > settings.get("mention_limit", 5):
                should_punish = True
                reason = f"Too many mentions ({len(message.mentions)})"

            # Repeated message check
            elif len(recent_messages) >= settings.get("repeat_threshold", 3):
                try:
                    messages = [msg async for msg in message.channel.history(limit=settings["repeat_threshold"])]
                    if all(msg.content == message.content for msg in messages if msg.author.id == message.author.id):
                        should_punish = True
                        reason = "Repeated messages"
                except discord.HTTPException:
                    self.logger.error("Failed to fetch message history")

            if should_punish:
                await self.handle_violation(message, member, settings["punishment"], reason)

        except Exception as e:
            self.logger.error(f"Error in message handling: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle raid detection"""
        config = await self.get_config(str(member.guild.id))
        if not config["enabled"]:
            return

        settings = config["raid_settings"]
        guild_id = str(member.guild.id)
        current_time = time.time()
        
        # Check account age
        account_age = (current_time - member.created_at.timestamp())
        if account_age < settings["account_age"]:
            try:
                await member.kick(reason="Account too new during raid protection")
                return
            except discord.Forbidden:
                pass

        # Track join
        if guild_id not in self.join_trackers:
            self.join_trackers[guild_id] = []
        self.join_trackers[guild_id].append(current_time)
        
        # Check recent joins
        window = settings["join_window"]
        recent_joins = [
            ts for ts in self.join_trackers[guild_id]
            if current_time - ts <= window
        ]
        
        if len(recent_joins) > settings["join_threshold"]:
            # Raid detected
            if settings["action"] == "lockdown":
                try:
                    # Set verification level to highest
                    await member.guild.edit(
                        verification_level=discord.VerificationLevel.highest
                    )
                    
                    # Schedule lockdown end
                    self.bot.loop.create_task(
                        self._end_lockdown(
                            member.guild,
                            settings["duration"]
                        )
                    )
                    
                    if config["log_channel"]:
                        channel = member.guild.get_channel(
                            int(config["log_channel"])
                        )
                        if channel:
                            await channel.send(
                                "🚨 **RAID DETECTED**\n"
                                f"Server locked down for {settings['duration']}s\n"
                                f"Reason: {len(recent_joins)} joins in "
                                f"{settings['join_window']}s"
                            )
                except discord.Forbidden:
                    self.logger.error(f"Missing permissions for raid lockdown in {member.guild.name}")
            
            elif settings["action"] == "kick":
                # Kick all recent joins
                for join_time in recent_joins:
                    members = [
                        m for m in member.guild.members
                        if (current_time - m.joined_at.timestamp()) <= settings["join_window"]
                    ]
                    for m in members:
                        try:
                            await m.kick(reason="Raid protection")
                        except discord.Forbidden:
                            continue

    async def _end_lockdown(self, guild: discord.Guild, duration: int):
        """End server lockdown after duration"""
        await asyncio.sleep(duration)
        try:
            await guild.edit(verification_level=discord.VerificationLevel.medium)
            
            config = await self.get_config(str(guild.id))
            if config["log_channel"]:
                channel = guild.get_channel(int(config["log_channel"]))
                if channel:
                    await channel.send("🛡️ Raid protection lockdown ended")
        except discord.Forbidden:
            self.logger.error(f"Missing permissions to end lockdown in {guild.name}")

    @tasks.loop(minutes=5)
    async def cleanup_trackers(self):
        """Clean up old tracking data with thread safety"""
        try:
            async with self._tracker_lock:
                current_time = time.time()
                
                # Clean message trackers
                for guild_id in list(self.message_trackers.keys()):
                    for user_id in list(self.message_trackers[guild_id].keys()):
                        # Remove messages older than 1 hour
                        self.message_trackers[guild_id][user_id] = [
                            ts for ts in self.message_trackers[guild_id][user_id]
                            if current_time - ts <= 3600
                        ]
                        # Remove empty user trackers
                        if not self.message_trackers[guild_id][user_id]:
                            del self.message_trackers[guild_id][user_id]
                    # Remove empty guild trackers
                    if not self.message_trackers[guild_id]:
                        del self.message_trackers[guild_id]
                
                # Clean join trackers
                for guild_id in list(self.join_trackers.keys()):
                    self.join_trackers[guild_id] = [
                        ts for ts in self.join_trackers[guild_id]
                        if current_time - ts <= 3600
                    ]
                    if not self.join_trackers[guild_id]:
                        del self.join_trackers[guild_id]
                
                # Clean config cache
                for guild_id in list(self._config_cache.keys()):
                    if current_time - self._last_cache_update.get(guild_id, 0) > self._cache_ttl:
                        del self._config_cache[guild_id]
                        del self._last_cache_update[guild_id]
                        
        except Exception as e:
            self.logger.error(f"Error in cleanup: {e}")

async def setup(bot):
    await bot.add_cog(AutoMod(bot))

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Union, Tuple, Literal
import logging
from datetime import datetime
import asyncio
import json
from discord.app_commands import checks
from discord.app_commands.checks import has_permissions
from discord.ext.commands import cooldown, BucketType
from datetime import timedelta

class Moderation(commands.Cog):
    """Moderation commands for server management"""
    
    mod_setup = app_commands.Group(name="mod_setup", description="Setup moderation settings")
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.infractions_key = "infractions"
        self.redemption_key = "redemption_tasks"
        self.escalation_key = "escalation_config"
        self.logger = bot.logger.getChild('moderation')
        self.active_punishments = {}
        self.cleanup_task = None
        self.action_confirmations = {}

    async def cog_load(self):
        """Called when the cog is loaded"""
        try:
            await self._init_data_structure()
            self.cleanup_task = self.bot.loop.create_task(self._cleanup_warnings())
            self.logger.info("Moderation cog loaded and initialized")
        except Exception as e:
            self.logger.error(f"Error loading moderation cog: {e}")
            raise

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.cleanup_task:
            self.cleanup_task.cancel()

    async def _check_mod_permissions(self, interaction: discord.Interaction, target: discord.Member) -> bool:
        """Check if the moderator has permission to moderate the target"""
        if interaction.user.id == interaction.guild.owner_id:
            return True
            
        if target.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot moderate the server owner.", ephemeral=True)
            return False
            
        if target.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ You cannot moderate members with higher or equal roles.", ephemeral=True)
            return False
            
        return True

    async def _confirm_action(self, interaction: discord.Interaction, action: str, target: Union[discord.Member, str]) -> bool:
        """Request confirmation for destructive actions"""
        confirmation_id = f"{interaction.id}-{action}"
        
        if confirmation_id in self.action_confirmations:
            del self.action_confirmations[confirmation_id]
            return True
            
        self.action_confirmations[confirmation_id] = datetime.utcnow()
        
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to {action} {target}? Use the command again within 10 seconds to confirm.",
            ephemeral=True
        )
        
        # Clean up old confirmations
        self._cleanup_confirmations()
        return False

    def _cleanup_confirmations(self):
        """Clean up expired confirmation requests"""
        now = datetime.utcnow()
        expired = [k for k, v in self.action_confirmations.items() if (now - v).total_seconds() > 10]
        for k in expired:
            del self.action_confirmations[k]

    async def _send_mod_log(self, guild: discord.Guild, embed: discord.Embed):
        """Send a moderation log with error handling"""
        try:
            config = await self._get_guild_config(str(guild.id))
            if log_channel_id := config.get("log_channel"):
                channel = guild.get_channel(int(log_channel_id))
                if channel and channel.permissions_for(guild.me).send_messages:
                    await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error sending mod log: {e}")

    async def _init_data_structure(self):
        """Initialize the moderation data structures"""
        try:
            # Initialize infractions data structure
            if not await self.bot.data_manager.exists(self.infractions_key):
                await self.bot.data_manager.save(self.infractions_key, "default", {})
            
            # Initialize redemption tasks
            if not await self.bot.data_manager.exists(self.redemption_key):
                await self.bot.data_manager.save(self.redemption_key, "default", {
                    "tasks": {
                        "help_others": {"description": "Help 3 other members", "points": 2},
                        "contribute_positively": {"description": "Make 5 contributions", "points": 2},
                        "create_guide": {"description": "Create a guide", "points": 3}
                    }
                })
            
            # Initialize escalation config
            if not await self.bot.data_manager.exists(self.escalation_key):
                await self.bot.data_manager.save(self.escalation_key, "default", {
                    "default": {
                        "warning_thresholds": {
                            "3": {"action": "mute", "duration": 3600},    # 1 hour mute
                            "5": {"action": "mute", "duration": 86400},   # 24 hour mute
                            "7": {"action": "kick", "duration": 0},       # Kick
                            "10": {"action": "ban", "duration": 0}        # Ban
                        },
                        "severity_multipliers": {
                            "1": 1,    # Normal warning
                            "2": 2,    # Moderate warning
                            "3": 3     # Severe warning
                        },
                        "warning_expiry": {
                            "1": 2592000,  # 30 days for severity 1
                            "2": 5184000,  # 60 days for severity 2
                            "3": 7776000   # 90 days for severity 3
                        },
                        "cleanup_interval": 86400,      # 24 hours
                        "history_retention": 15552000,  # 180 days
                        "dm_notifications": True,
                        "log_channel": None,
                        "auto_pardon": False,           # Automatically remove expired warnings
                        "require_reason": True,
                        "allow_appeals": True,
                        "appeal_cooldown": 604800,      # 7 days
                        "universal_warnings": False,    # Accept warnings from other servers
                        "share_warnings": False,        # Share warnings with other servers
                        "warning_weight": 1.0           # Weight for warnings from other servers
                    }
                })
            
            self.logger.info("Moderation data structures initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing moderation data: {e}")
            raise

    async def _get_guild_config(self, guild_id: str) -> dict:
        """Get guild configuration with defaults"""
        try:
            config = await self.bot.data_manager.load("guild_configs", guild_id) or {}
            
            # Default configuration
            defaults = {
                "log_channel": None,
                "mute_role": None,
                "warning_expiry": 30,  # Days
                "dm_notifications": True,
                "auto_pardon": False,
                "require_reason": True,
                "allow_appeals": True,
                "universal_warnings": False,
                "share_warnings": False,
                "escalation_config": {
                    "warning_points": 3,
                    "action": "mute",
                    "duration": 24,  # Hours
                    "severity_multiplier": 2
                }
            }
            
            # Update config with defaults while preserving existing values
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
                elif isinstance(value, dict) and isinstance(config[key], dict):
                    # Deep merge for nested dictionaries
                    for subkey, subvalue in value.items():
                        if subkey not in config[key]:
                            config[key][subkey] = subvalue
            
            await self.bot.data_manager.save("guild_configs", guild_id, config)
            return config
            
        except Exception as e:
            self.logger.error(f"Error loading guild config: {e}", exc_info=True)
            return defaults

    async def _save_guild_config(self, guild_id: str, config: dict):
        """Save guild-specific configuration"""
        try:
            all_config = await self.bot.data_manager.load("guild_configs") or {}
            all_config[guild_id] = config
            await self.bot.data_manager.save("guild_configs", guild_id, all_config)
        except Exception as e:
            self.logger.error(f"Error saving guild config: {e}", exc_info=True)

    async def _get_user_infractions(self, guild_id: str, user_id: str) -> dict:
        """Get user infractions with proper initialization"""
        try:
            all_infractions = await self.bot.data_manager.load(self.infractions_key, "default") or {}
            guild_data = all_infractions.get(guild_id, {})
            return guild_data.get(user_id, {"warns": []})
        except Exception as e:
            self.logger.error(f"Error loading user infractions: {e}")
            return {"warns": []}

    async def _save_infraction(self, guild_id: str, user_id: str, infractions: dict):
        """Save user infractions with proper structure"""
        try:
            all_infractions = await self.bot.data_manager.load(self.infractions_key, "default") or {}
            
            if guild_id not in all_infractions:
                all_infractions[guild_id] = {}
            all_infractions[guild_id][user_id] = infractions
            
            await self.bot.data_manager.save(self.infractions_key, "default", all_infractions)
        except Exception as e:
            self.logger.error(f"Error saving infractions: {e}")
            raise

    async def _get_active_warnings(self, guild_id: str, user_id: str) -> list:
        """Get non-expired warnings for a user"""
        infractions = await self._get_user_infractions(guild_id, user_id)
        config = await self._get_guild_config(guild_id)
        
        active_warnings = []
        for warn in infractions["warns"]:
            if warn.get("redeemed", False):
                continue
                
            warn_time = datetime.fromisoformat(warn["timestamp"])
            expiry_seconds = config["warning_expiry"] * 86400
            
            if (datetime.utcnow() - warn_time).total_seconds() < expiry_seconds:
                active_warnings.append(warn)
        
        return active_warnings

    async def _calculate_punishment(self, guild_id: str, user_id: str, severity: int) -> tuple:
        """Calculate punishment based on warning history"""
        try:
            config = await self.bot.data_manager.load(self.escalation_key, "default") or {}
            guild_config = config.get(guild_id, {})
            
            infractions = await self._get_user_infractions(guild_id, user_id)
            active_warnings = await self._get_active_warnings(guild_id, user_id)
            
            total_severity = sum(w["severity"] for w in active_warnings) + severity
            
            # Default escalation rules if not configured
            if "escalation_rules" not in guild_config:
                guild_config["escalation_rules"] = {
                    "3": {"action": "mute", "duration": 3600},     # 1 hour mute
                    "5": {"action": "mute", "duration": 86400},    # 24 hour mute
                    "7": {"action": "kick", "duration": 0},        # Kick
                    "10": {"action": "ban", "duration": 0}         # Ban
                }
            
            # Find appropriate punishment
            rules = guild_config["escalation_rules"]
            action = None
            duration = 0
            for threshold, punishment in sorted(rules.items(), key=lambda x: int(x[0]), reverse=True):
                if total_severity >= int(threshold):
                    action = punishment["action"]
                    duration = punishment["duration"]
                    break
            
            return action, duration, f"Total warning severity: {total_severity}"
            
        except Exception as e:
            self.logger.error(f"Error calculating punishment: {e}")
            return None, 0, "Error calculating punishment"

    async def _apply_punishment(
        self,
        guild: discord.Guild,
        user: discord.Member,
        action: str,
        duration: int,
        reason: str
    ) -> bool:
        """Apply the calculated punishment to the user"""
        try:
            # Check bot permissions
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                self.logger.error("Bot is not a member of the guild")
                return False

            # Check if bot has required permissions
            if not bot_member.guild_permissions.administrator:
                required_perms = {
                    "mute": ["moderate_members"],
                    "kick": ["kick_members"],
                    "ban": ["ban_members"]
                }
                
                if action in required_perms:
                    for perm in required_perms[action]:
                        if not getattr(bot_member.guild_permissions, perm, False):
                            self.logger.error(f"Missing required permission: {perm}")
                            return False

            # Check role hierarchy
            if bot_member.top_role <= user.top_role:
                self.logger.error("Bot's role is not high enough to moderate this user")
                return False

            if action == "mute":
                # Use timeout for mute
                until = discord.utils.utcnow() + timedelta(seconds=duration)
                await user.timeout(until, reason=reason)
                
                # Schedule unmute
                self.active_punishments[f"{guild.id}-{user.id}"] = {
                    "type": "mute",
                    "end_time": until.isoformat()
                }
                asyncio.create_task(self._schedule_unmute(str(guild.id), str(user.id), duration))
                
            elif action == "kick":
                await user.kick(reason=reason)
                
            elif action == "ban":
                await user.ban(reason=reason, delete_message_days=1)
                
            return True
            
        except discord.Forbidden as e:
            self.logger.error(f"Permission error applying punishment: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"Error applying punishment: {str(e)}")
            return False

    async def _schedule_unmute(self, guild_id: str, user_id: str, duration: int):
        """Schedule an unmute after the specified duration"""
        await asyncio.sleep(duration)
        
        # Check if punishment is still active
        punishment_key = f"{guild_id}-{user_id}"
        if punishment_key in self.active_punishments:
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    try:
                        await member.timeout(None)  # Remove timeout
                    except Exception as e:
                        self.logger.error(f"Error removing timeout: {str(e)}")
            
            del self.active_punishments[punishment_key]

    async def _cleanup_warnings(self):
        """Periodically clean up expired warnings"""
        while True:
            try:
                # Load infractions with proper key
                all_infractions = await self.bot.data_manager.load(self.infractions_key, "default") or {}
                
                current_time = datetime.utcnow()
                changes_made = False

                for guild_id, guild_data in all_infractions.items():
                    config = await self._get_guild_config(guild_id)
                    retention_period = config.get("history_retention", 86400 * 30)  # Default 30 days
                    auto_pardon = config.get("auto_pardon", False)

                    for user_id, user_data in guild_data.items():
                        if "warns" not in user_data:
                            continue

                        # Filter warnings based on retention period
                        retained_warnings = []
                        for warn in user_data["warns"]:
                            warn_time = datetime.fromisoformat(warn["timestamp"])
                            age = (current_time - warn_time).total_seconds()

                            if age < retention_period:
                                # Keep warnings within retention period
                                retained_warnings.append(warn)
                            elif auto_pardon and not warn.get("redeemed"):
                                # Mark expired warnings as pardoned if auto_pardon is enabled
                                warn["redeemed"] = True
                                warn["pardon_reason"] = "Automatic expiration"
                                retained_warnings.append(warn)
                                changes_made = True

                                # Log the pardon if log channel is configured
                                log_channel_id = config.get("log_channel")
                                if log_channel_id:
                                    try:
                                        guild = self.bot.get_guild(int(guild_id))
                                        if guild:
                                            log_channel = guild.get_channel(int(log_channel_id))
                                            if log_channel:
                                                user = guild.get_member(int(user_id))
                                                user_text = f"{user.mention} ({user_id})" if user else f"User {user_id}"
                                                await log_channel.send(
                                                    f"🕊️ Warning automatically pardoned for {user_text}\n"
                                                    f"Original Reason: {warn.get('reason', 'No reason provided')}\n"
                                                    f"Warning Age: {age//86400:.1f} days"
                                                )
                                    except Exception as e:
                                        self.logger.error(f"Error sending pardon log: {e}")

                        if len(retained_warnings) != len(user_data["warns"]):
                            user_data["warns"] = retained_warnings
                            changes_made = True

                if changes_made:
                    await self.bot.data_manager.save(self.infractions_key, "default", all_infractions)

                # Get shortest cleanup interval from all guild configs, default to 24h
                cleanup_intervals = []
                for guild_id in all_infractions.keys():
                    try:
                        config = await self._get_guild_config(guild_id)
                        interval = config.get("cleanup_interval", 86400)
                        cleanup_intervals.append(interval)
                    except Exception as e:
                        self.logger.error(f"Error getting cleanup interval for guild {guild_id}: {e}")
                        cleanup_intervals.append(86400)  # Default to 24h on error
                
                await asyncio.sleep(min(cleanup_intervals or [86400]))

            except asyncio.CancelledError:
                self.logger.info("Warning cleanup task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in warning cleanup task: {e}", exc_info=True)
                await asyncio.sleep(3600)  # Wait an hour on error

    async def log_action(self, guild, action: str, description: str, moderator, reason: str = None):
        """Log a moderation action to the configured log channel"""
        try:
            config = await self._get_guild_config(str(guild.id))
            if not config.get("log_channel"):
                return
            
            log_channel = guild.get_channel(int(config["log_channel"]))
            if not log_channel:
                return
            
            embed = discord.Embed(
                title=f"🔨 {action}",
                description=description,
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Moderator", value=moderator.mention)
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await log_channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error logging action: {e}", exc_info=True)

    async def _send_dm_notification(self, user: discord.Member, embed: discord.Embed) -> bool:
        """Send a DM notification to a user with proper error handling."""
        try:
            await user.send(embed=embed)
            return True
        except discord.Forbidden:
            self.logger.debug(
                f"Could not DM user {user.id}: User has DMs disabled or no mutual servers",
                extra={"user_id": user.id}
            )
        except discord.HTTPException as e:
            self.logger.warning(
                f"Failed to DM user {user.id} due to HTTP error: {e}",
                extra={"user_id": user.id, "error": str(e)}
            )
        except Exception as e:
            self.logger.error(
                f"Unexpected error while DMing user {user.id}: {e}",
                extra={"user_id": user.id, "error": str(e)},
                exc_info=True
            )
        return False

    async def _notify_user(
        self,
        user: discord.Member,
        guild: discord.Guild,
        action: str,
        embed: discord.Embed,
        config: dict
    ) -> None:
        """
        Notify a user about a moderation action with proper error handling and fallback.
        """
        if not config.get("dm_notifications", True):
            return

        success = await self._send_dm_notification(user, embed)
        
        # If DM failed and logging is enabled, log it to the mod channel
        if not success and config.get("log_channel"):
            try:
                log_channel = guild.get_channel(int(config["log_channel"]))
                if log_channel:
                    log_embed = discord.Embed(
                        title="⚠️ DM Notification Failed",
                        description=f"Could not send {action} notification to {user.mention}",
                        color=discord.Color.yellow()
                    )
                    log_embed.add_field(
                        name="Note",
                        value="User may have DMs disabled or no mutual servers"
                    )
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                self.logger.warning(f"Failed to log DM failure: {e}")

    @app_commands.command(
        name="warn",
        description="Warn a user with redemption opportunity"
    )
    @app_commands.describe(
        user="The user to warn",
        reason="Reason for the warning",
        severity="Warning severity (1: Minor, 2: Moderate, 3: Severe)"
    )
    @commands.cooldown(rate=3, per=10.0, type=BucketType.user)  # 3 warnings per 10 seconds
    @has_permissions(moderate_members=True)
    async def warn(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        reason: str,
        severity: app_commands.Range[int, 1, 3] = 1
    ):
        """Warn a user with proper error handling and feedback"""
        try:
            # Permission checks
            if not await self._check_mod_permissions(interaction, user):
                return

            # Get configuration
            config = await self._get_guild_config(str(interaction.guild_id))
            
            # Check if reason is required
            if config.get("require_reason", True) and not reason:
                await interaction.response.send_message(
                    "❌ A reason is required for warnings.",
                    ephemeral=True
                )
                return

            # Get user's infractions
            infractions = await self._get_user_infractions(str(interaction.guild_id), str(user.id))
            
            # Add new warning
            warning = {
                "id": f"w{len(infractions.get('warns', []))+1}",
                "reason": reason,
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
                "moderator_id": str(interaction.user.id),
                "redeemed": False
            }

            if "warns" not in infractions:
                infractions["warns"] = []
            infractions["warns"].append(warning)

            # Save updated infractions
            await self._save_infraction(str(interaction.guild_id), str(user.id), infractions)

            # Calculate punishment
            action, duration, escalation_reason = await self._calculate_punishment(
                str(interaction.guild_id),
                str(user.id),
                severity
            )

            # Create response embed
            embed = discord.Embed(
                title=f"⚠️ Warning Issued (Level {severity})",
                color=discord.Color.yellow(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            active_warnings = await self._get_active_warnings(str(interaction.guild_id), str(user.id))
            embed.add_field(
                name="Active Warnings",
                value=f"{len(active_warnings)} warning(s)",
                inline=True
            )

            # Apply punishment if necessary
            if action:
                if await self._apply_punishment(interaction.guild, user, action, duration, escalation_reason):
                    embed.add_field(
                        name="Automatic Action",
                        value=f"{action.title()} ({duration//3600}h)" if duration else action.title(),
                        inline=False
                    )

            # Send response
            await interaction.response.send_message(embed=embed)

            # Send mod log
            await self._send_mod_log(interaction.guild, embed)

            # DM the user if enabled
            if config.get("dm_notifications", True):
                user_embed = discord.Embed(
                    title=f"Warning Received in {interaction.guild.name}",
                    color=discord.Color.yellow(),
                    timestamp=datetime.utcnow()
                )
                user_embed.add_field(name="Reason", value=reason, inline=False)
                user_embed.add_field(name="Severity", value=f"Level {severity}", inline=True)
                if action:
                    user_embed.add_field(
                        name="Automatic Action",
                        value=f"{action.title()} ({duration//3600}h)" if duration else action.title(),
                        inline=False
                    )
                await self._notify_user(user, interaction.guild, "warn", user_embed, config)
                
        except Exception as e:
            self.logger.error(f"Error issuing warning: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while issuing the warning. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(
        name="setup",
        description="Setup moderation settings"
    )
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction):
        """Setup moderation settings"""
        pass

    @mod_setup.command(
        name="escalation_config",
        description="Configure warning escalation settings"
    )
    @app_commands.guild_only()
    async def setup_escalation_config(
        self,
        interaction: discord.Interaction,
        warning_points: Optional[int] = None,
        action: Optional[Literal["mute", "kick", "ban"]] = None,
        duration: Optional[int] = None,
        severity_multiplier: Optional[int] = None,
        warning_expiry: Optional[int] = None
    ):
        """Configure the warning escalation system"""
        guild_id = str(interaction.guild_id)
        
        # Reset to default configuration
        if warning_points is None and action is None and duration is None and severity_multiplier is None and warning_expiry is None:
            all_config = await self.bot.data_manager.load(self.escalation_key, "default")
            if guild_id in all_config:
                del all_config[guild_id]
                await self.bot.data_manager.save(self.escalation_key, "default", all_config)
                await interaction.response.send_message(
                    "✅ Reset to default configuration",
                    ephemeral=True
                )
                return

        config = await self._get_guild_config(guild_id)
        
        # Create guild-specific config if using default
        if guild_id not in (await self.bot.data_manager.load(self.escalation_key, "default")):
            await self._save_guild_config(guild_id, config.copy())

        # Handle different setting types
        if warning_points and action:
            if action not in ["mute", "kick", "ban"]:
                await interaction.response.send_message(
                    "❌ Invalid action! Use: mute, kick, or ban",
                    ephemeral=True
                )
                return

            if warning_points < 1:
                await interaction.response.send_message(
                    "❌ Warning points must be positive!",
                    ephemeral=True
                )
                return

            config["warning_thresholds"][str(warning_points)] = {
                "action": action,
                "duration": duration if action == "mute" else 0
            }

        elif severity_multiplier:
            if severity_multiplier not in [1, 2, 3]:
                await interaction.response.send_message(
                    "❌ Severity must be 1, 2, or 3!",
                    ephemeral=True
                )
                return

            config["severity_multipliers"][str(severity_multiplier)] = severity_multiplier

        elif warning_expiry:
            if warning_expiry not in [1, 2, 3]:
                await interaction.response.send_message(
                    "❌ Severity must be 1, 2, or 3!",
                    ephemeral=True
                )
                return

            if warning_expiry < 1:
                await interaction.response.send_message(
                    "❌ Expiry days must be positive!",
                    ephemeral=True
                )
                return

            config["warning_expiry"][str(warning_expiry)] = warning_expiry * 86400

        else:
            await interaction.response.send_message(
                "❌ Invalid configuration! Use:\n"
                "• warning_points: Set warning point thresholds\n"
                "• action: Set action for warning points\n"
                "• duration: Set duration for mute action\n"
                "• severity_multiplier: Set severity multiplier\n"
                "• warning_expiry: Set warning expiry time",
                ephemeral=True
            )
            return

        await self._save_guild_config(guild_id, config)
        await interaction.response.send_message(
            "✅ Configuration updated!",
            ephemeral=True
        )

    @mod_setup.command(
        name="log_channel",
        description="Set the moderation log channel"
    )
    @app_commands.guild_only()
    async def setup_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Set the channel for moderation logs"""
        try:
            config = await self._get_guild_config(str(interaction.guild_id))
            config["log_channel"] = channel.id
            await self._save_guild_config(str(interaction.guild_id), config)
            
            await interaction.response.send_message(
                f"Moderation logs will now be sent to {channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error setting log channel: {e}", exc_info=True)
            await interaction.response.send_message(
                "Failed to set log channel. Please try again later.",
                ephemeral=True
            )

    @mod_setup.command(
        name="toggle",
        description="Toggle moderation settings"
    )
    @app_commands.guild_only()
    async def setup_toggle(
        self,
        interaction: discord.Interaction,
        setting: Optional[Literal["dm_notifications", "auto_pardon", "require_reason", "allow_appeals",
                        "universal_warnings", "share_warnings"]] = None,
        value: Optional[bool] = None
    ):
        """Toggle various moderation settings"""
        try:
            config = await self._get_guild_config(str(interaction.guild_id))
            if setting:
                valid_toggles = [
                    "dm_notifications", "auto_pardon",
                    "require_reason", "allow_appeals",
                    "universal_warnings", "share_warnings"
                ]
                if setting not in valid_toggles:
                    await interaction.response.send_message(
                        f"❌ Invalid toggle! Use: {', '.join(valid_toggles)}",
                        ephemeral=True
                    )
                    return
                config[setting] = value
            await self._save_guild_config(str(interaction.guild_id), config)
            
            setting_name = next(
                choice.name for choice in self.setup_toggle.extras["choices"] 
                if choice.value == setting
            )
            
            await interaction.response.send_message(
                f"{setting_name} has been {'enabled' if value else 'disabled'}.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error toggling setting: {e}", exc_info=True)
            await interaction.response.send_message(
                "Failed to toggle setting. Please try again later.",
                ephemeral=True
            )

    @mod_setup.command(
        name="redemption",
        description="Configure warning redemption settings"
    )
    @app_commands.guild_only()
    async def setup_redemption(
        self,
        interaction: discord.Interaction,
        action: Optional[Literal["add", "remove", "list"]] = "list",
        task_id: Optional[str] = None,
        description: Optional[str] = None,
        points: Optional[int] = None
    ):
        """Configure warning redemption tasks"""
        try:
            redemption_data = await self.bot.data_manager.load(self.redemption_key, "default")
            tasks = redemption_data.get("tasks", {})
            
            if action == "list":
                if not tasks:
                    await interaction.response.send_message(
                        "No redemption tasks configured.",
                        ephemeral=True
                    )
                    return
                
                embed = discord.Embed(
                    title="🕊️ Redemption Tasks",
                    color=discord.Color.blue()
                )
                for name, task in tasks.items():
                    embed.add_field(
                        name=f"{name} ({task['points']} points)",
                        value=task["description"],
                        inline=False
                    )
                await interaction.response.send_message(embed=embed)
                
            elif action == "add":
                if not all([task_id, description, points]):
                    await interaction.response.send_message(
                        "Please provide task id, description, and points when adding a task.",
                        ephemeral=True
                    )
                    return
                    
                tasks[task_id] = {
                    "description": description,
                    "points": points
                }
                redemption_data["tasks"] = tasks
                await self.bot.data_manager.save(self.redemption_key, "default", redemption_data)
                
                await interaction.response.send_message(
                    f"Added redemption task: {task_id}",
                    ephemeral=True
                )
                
            elif action == "remove":
                if not task_id:
                    await interaction.response.send_message(
                        "Please provide the task id to remove.",
                        ephemeral=True
                    )
                    return
                    
                if task_id not in tasks:
                    await interaction.response.send_message(
                        f"Task {task_id} not found.",
                        ephemeral=True
                    )
                    return
                    
                del tasks[task_id]
                redemption_data["tasks"] = tasks
                await self.bot.data_manager.save(self.redemption_key, "default", redemption_data)
                
                await interaction.response.send_message(
                    f"Removed redemption task: {task_id}",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Error configuring redemption tasks: {e}", exc_info=True)
            await interaction.response.send_message(
                "Failed to configure redemption tasks. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(
        name="redeem",
        description="Submit a redemption task for review"
    )
    @app_commands.describe(
        task="Redemption task to complete",
        proof="Proof of task completion"
    )
    async def redeem(
        self,
        interaction: discord.Interaction,
        task: str,
        proof: str
    ):
        """Submit a redemption task for moderator review"""
        # Check if user has warnings to redeem
        infractions = await self._get_user_infractions(
            str(interaction.guild_id), 
            str(interaction.user.id)
        )
        
        unredeemed_warns = [w for w in infractions["warns"] if not w["redeemed"]]
        if not unredeemed_warns:
            await interaction.response.send_message(
                "You don't have any warnings that need redemption!",
                ephemeral=True
            )
            return

        # Check if task exists
        redemption_tasks = await self.bot.data_manager.load(self.redemption_key, "default")["tasks"]
        if task not in redemption_tasks:
            await interaction.response.send_message(
                f"Invalid task! Available tasks:\n" + \
                "\n".join([f"• {k}: {v['description']}" for k, v in redemption_tasks.items()]),
                ephemeral=True
            )
            return

        # Create redemption request embed
        embed = discord.Embed(
            title="🌟 Redemption Request",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.add_field(name="Task", value=redemption_tasks[task]["description"], inline=True)
        embed.add_field(name="Proof", value=proof, inline=False)

        # Add buttons for moderators
        approve_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Approve",
            custom_id=f"redeem_approve_{interaction.user.id}_{task}"
        )
        deny_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Deny",
            custom_id=f"redeem_deny_{interaction.user.id}_{task}"
        )

        view = discord.ui.View()
        view.add_item(approve_button)
        view.add_item(deny_button)

        await interaction.response.send_message(
            "Your redemption request has been submitted for review!",
            ephemeral=True
        )
        
        # Send to moderation channel
        mod_channel = interaction.guild.get_channel(  # Replace with your mod channel ID
            interaction.guild.system_channel.id  # Temporary: using system channel
        )
        if mod_channel:
            await mod_channel.send(embed=embed, view=view)

    @app_commands.command(
        name="infractions",
        description="View a user's infractions"
    )
    @app_commands.describe(user="The user to check infractions for")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def infractions(
        self, 
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        """View a user's infractions"""
        try:
            # Get user infractions using the helper method
            if user is None:
                user = interaction.user
            user_infractions = await self._get_user_infractions(str(interaction.guild_id), str(user.id))
            if not user_infractions:
                user_infractions = {"warns": [], "mutes": [], "redemption": 0}

            # Create embed
            embed = discord.Embed(
                title=f"Infractions for {user.display_name}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )

            # Add warnings
            warns = user_infractions.get("warns", [])
            if warns:
                warns_text = ""
                for i, warn in enumerate(warns, 1):
                    mod_id = warn.get("moderator_id", warn.get("moderator", "Unknown"))
                    try:
                        mod = interaction.guild.get_member(int(mod_id)) if mod_id != "Unknown" else None
                        mod_name = mod.display_name if mod else "Unknown Moderator"
                    except:
                        mod_name = "Unknown Moderator"
                        
                    status = "✅ Redeemed" if warn.get("redeemed") else "❌ Active"
                    severity = warn.get("severity", 1)
                    warns_text += f"{i}. Level {severity} Warning: {warn.get('reason', 'No reason')}\n"
                    warns_text += f"   By: {mod_name} | Status: {status}\n"
                
                embed.add_field(name=f"Warnings ({len(warns)})", value=warns_text, inline=False)
            else:
                embed.add_field(name="Warnings", value="No warnings", inline=False)

            # Add active mutes
            mutes = user_infractions.get("mutes", [])
            active_mutes = []
            for mute in mutes:
                if "end_time" in mute:
                    try:
                        end_time = datetime.fromisoformat(mute["end_time"])
                        if end_time > datetime.utcnow():
                            active_mutes.append(mute)
                    except:
                        continue

            if active_mutes:
                mutes_text = ""
                for i, mute in enumerate(active_mutes, 1):
                    end_time = datetime.fromisoformat(mute["end_time"])
                    mutes_text += f"{i}. Until: {end_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    mutes_text += f"   Reason: {mute.get('reason', 'No reason provided')}\n"
                embed.add_field(name=f"Active Mutes ({len(active_mutes)})", value=mutes_text, inline=False)

            # Add redemption progress if there are active warnings
            active_warnings = len([w for w in warns if not w.get("redeemed", False)])
            if active_warnings > 0:
                redemption_points = user_infractions.get("redemption", 0)
                embed.add_field(
                    name="Redemption Progress",
                    value=f"Points Earned: {redemption_points}\nActive Warnings: {active_warnings}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in infractions command: {str(e)}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while fetching infractions. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(
        name="appeal",
        description="Appeal a warning"
    )
    @app_commands.describe(
        infraction_id="ID of the infraction to appeal",
        reason="Reason for the appeal"
    )
    async def appeal(
        self, 
        interaction: discord.Interaction,
        infraction_id: str,
        reason: str
    ):
        """Appeal an infraction"""
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        
        # Get user's infractions and config
        infractions = await self._get_user_infractions(guild_id, user_id)
        config = await self._get_guild_config(guild_id)
        
        if not config["allow_appeals"]:
            await interaction.response.send_message(
                "❌ Appeals are not enabled on this server",
                ephemeral=True
            )
            return

        # Find the warning
        warning = None
        for warn in infractions.get("warns", []):
            if warn.get("id") == infraction_id:
                warning = warn
                break

        if not warning:
            await interaction.response.send_message(
                "❌ Warning not found! Use `/infractions` to view your warnings",
                ephemeral=True
            )
            return

        # Check if warning is already appealed/redeemed
        if warning.get("appealed"):
            await interaction.response.send_message(
                "❌ This warning has already been appealed",
                ephemeral=True
            )
            return

        if warning.get("redeemed"):
            await interaction.response.send_message(
                "❌ This warning has already been redeemed",
                ephemeral=True
            )
            return

        # Check appeal cooldown
        last_appeal = warning.get("last_appeal")
        if last_appeal:
            last_appeal_time = datetime.fromisoformat(last_appeal)
            time_since = (datetime.utcnow() - last_appeal_time).total_seconds()
            if time_since < config["appeal_cooldown"]:
                days_left = (config["appeal_cooldown"] - time_since) // 86400
                await interaction.response.send_message(
                    f"❌ Please wait {days_left:.1f} days before appealing again",
                    ephemeral=True
                )
                return

        # Create appeal
        warning["appealed"] = True
        warning["appeal_reason"] = reason
        warning["appeal_time"] = datetime.utcnow().isoformat()
        warning["last_appeal"] = datetime.utcnow().isoformat()
        
        # Save changes
        await self._save_infraction(guild_id, user_id, infractions)

        # Create appeal embed
        embed = discord.Embed(
            title="📋 Warning Appeal",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.add_field(name="Warning ID", value=infraction_id, inline=True)
        embed.add_field(
            name="Original Warning",
            value=f"Reason: {warning['reason']}\n"
                  f"Severity: Level {warning['severity']}\n"
                  f"Time: <t:{int(datetime.fromisoformat(warning['timestamp']).timestamp())}:R>",
            inline=False
        )
        embed.add_field(name="Appeal Reason", value=reason, inline=False)

        # Add buttons for moderators
        approve_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Approve Appeal",
            custom_id=f"appeal_approve_{user_id}_{infraction_id}"
        )
        deny_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Deny Appeal",
            custom_id=f"appeal_deny_{user_id}_{infraction_id}"
        )

        view = discord.ui.View()
        view.add_item(approve_button)
        view.add_item(deny_button)

        # Send to log channel
        if config["log_channel"]:
            log_channel = interaction.guild.get_channel(
                int(config["log_channel"])
            )
            if log_channel:
                await log_channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            "✅ Appeal submitted! Moderators will review it soon",
            ephemeral=True
        )

    @app_commands.command(
        name="manageappeal",
        description="Manage warning appeals"
    )
    @app_commands.describe(
        user="User who made the appeal",
        infraction_id="ID of the infraction being appealed",
        action="Action to take on the appeal",
        reason="Reason for the action"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def manage_appeal(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        infraction_id: str,
        action: Literal["approve", "deny"],
        reason: Optional[str] = None
    ):
        """Manage a warning appeal"""
        if action not in ["approve", "deny"]:
            await interaction.response.send_message(
                "❌ Invalid action! Use: approve or deny",
                ephemeral=True
            )
            return

        # Get warning
        infractions = await self._get_user_infractions(
            str(interaction.guild_id),
            str(user.id)
        )
        
        warning = None
        for warn in infractions.get("warns", []):
            if warn.get("id") == infraction_id:
                warning = warn
                break

        if not warning:
            await interaction.response.send_message(
                "❌ Warning not found!",
                ephemeral=True
            )
            return

        if not warning.get("appealed"):
            await interaction.response.send_message(
                "❌ This warning has not been appealed!",
                ephemeral=True
            )
            return

        # Handle appeal
        if action == "approve":
            warning["redeemed"] = True
            warning["appeal_status"] = "approved"
            warning["appeal_handler"] = str(interaction.user.id)
            warning["appeal_response"] = reason or "Appeal approved"
            
            # Notify user
            try:
                embed = discord.Embed(
                    title="🎉 Appeal Approved",
                    color=discord.Color.green(),
                    description=f"Your appeal for warning {infraction_id} has been approved!"
                )
                if reason:
                    embed.add_field(name="Moderator Note", value=reason)
                await user.send(embed=embed)
            except:
                pass

        else:  # deny
            warning["appeal_status"] = "denied"
            warning["appeal_handler"] = str(interaction.user.id)
            warning["appeal_response"] = reason or "Appeal denied"
            
            # Notify user
            try:
                embed = discord.Embed(
                    title="❌ Appeal Denied",
                    color=discord.Color.red(),
                    description=f"Your appeal for warning {infraction_id} has been denied."
                )
                if reason:
                    embed.add_field(name="Reason", value=reason)
                await user.send(embed=embed)
            except:
                pass

        # Save changes
        await self._save_infraction(
            str(interaction.guild_id),
            str(user.id),
            infractions
        )

        # Log action
        config = await self._get_guild_config(str(interaction.guild_id))
        if config["log_channel"]:
            log_channel = interaction.guild.get_channel(
                int(config["log_channel"])
            )
            if log_channel:
                embed = discord.Embed(
                    title=f"📋 Appeal {action.title()}ed",
                    color=discord.Color.green() if action == "approve"
                    else discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="User", value=user.mention, inline=True)
                embed.add_field(name="Warning ID", value=infraction_id, inline=True)
                embed.add_field(
                    name="Moderator",
                    value=interaction.user.mention,
                    inline=True
                )
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                await log_channel.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Appeal {action}ed successfully!",
            ephemeral=True
        )

    @app_commands.command(
        name="transferwarnings",
        description="Transfer warnings between servers"
    )
    @app_commands.describe(
        from_server="Server ID to transfer warnings from",
        user="User to transfer warnings for",
        warning_ids="Warning IDs to transfer (comma-separated), or 'all'"
    )
    @app_commands.default_permissions(administrator=True)
    async def transfer_warnings(
        self,
        interaction: discord.Interaction,
        from_server: str,
        user: discord.Member,
        warning_ids: Optional[str] = None  # Comma-separated IDs, or "all"
    ):
        """Transfer warnings from another server"""
        # Verify source server shares warnings
        source_config = await self._get_guild_config(from_server)
        if not source_config["share_warnings"]:
            await interaction.response.send_message(
                "❌ Source server does not share warnings!",
                ephemeral=True
            )
            return

        # Get source warnings
        source_infractions = await self._get_user_infractions(from_server, str(user.id))
        if not source_infractions.get("warns"):
            await interaction.response.send_message(
                "❌ No warnings found in source server!",
                ephemeral=True
            )
            return

        # Get target infractions
        target_infractions = await self._get_user_infractions(
            str(interaction.guild_id),
            str(user.id)
        )
        if "warns" not in target_infractions:
            target_infractions["warns"] = []

        # Determine warnings to transfer
        warnings_to_transfer = []
        if warning_ids and warning_ids.lower() != "all":
            ids = warning_ids.split(",")
            for warn in source_infractions["warns"]:
                if warn["id"] in ids:
                    warnings_to_transfer.append(warn.copy())
        else:
            warnings_to_transfer = [
                warn.copy() for warn in source_infractions["warns"]
            ]

        if not warnings_to_transfer:
            await interaction.response.send_message(
                "❌ No valid warnings to transfer!",
                ephemeral=True
            )
            return

        # Transfer warnings
        transferred = []
        for warn in warnings_to_transfer:
            warn["transferred_from"] = from_server
            warn["transfer_time"] = datetime.utcnow().isoformat()
            target_infractions["warns"].append(warn)
            transferred.append(warn["id"])

        # Save changes
        await self._save_infraction(
            str(interaction.guild_id),
            str(user.id),
            target_infractions
        )

        # Create response embed
        embed = discord.Embed(
            title="📋 Warning Transfer Results",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(
            name="Source Server",
            value=f"ID: {from_server}",
            inline=True
        )
        embed.add_field(
            name="Transferred Warnings",
            value=", ".join(transferred) or "None",
            inline=False
        )

        # Log transfer
        config = await self._get_guild_config(str(interaction.guild_id))
        if config["log_channel"]:
            log_channel = interaction.guild.get_channel(
                int(config["log_channel"])
            )
            if log_channel:
                await log_channel.send(embed=embed)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="bulkwarn",
        description="Warn multiple users at once"
    )
    @app_commands.describe(
        users="Users to warn (space-separated mentions or IDs)",
        reason="Reason for the warning",
        severity="Warning severity (1-3)"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def bulkwarn(
        self,
        interaction: discord.Interaction,
        users: str,
        reason: str,
        severity: app_commands.Range[int, 1, 3] = 1
    ):
        """Warn multiple users at once"""
        if severity not in [1, 2, 3]:
            severity = 1

        # Parse users
        user_ids = []
        for user_ref in users.split():
            user_ref = user_ref.strip()
            if user_ref.startswith("<@") and user_ref.endswith(">"):
                user_ids.append(user_ref[2:-1])
            else:
                user_ids.append(user_ref)

        # Validate users
        valid_users = []
        invalid_users = []
        for user_id in user_ids:
            try:
                user = await interaction.guild.fetch_member(user_id)
                if user:
                    valid_users.append(user)
                else:
                    invalid_users.append(user_id)
            except:
                invalid_users.append(user_id)

        if not valid_users:
            await interaction.response.send_message(
                "❌ No valid users found!",
                ephemeral=True
            )
            return

        # Warn valid users
        warned_users = []
        failed_users = []
        
        progress_msg = await interaction.response.send_message(
            f"Processing warnings for {len(valid_users)} users...",
            ephemeral=True
        )

        for user in valid_users:
            try:
                # Get user's infractions
                infractions = await self._get_user_infractions(str(interaction.guild_id), str(user.id))
                
                # Add warning
                warning = {
                    "id": f"w{len(infractions.get('warns', []))+1}",
                    "reason": reason,
                    "severity": severity,
                    "timestamp": datetime.utcnow().isoformat(),
                    "moderator_id": str(interaction.user.id),
                    "redeemed": False
                }
                
                if "warns" not in infractions:
                    infractions["warns"] = []
                infractions["warns"].append(warning)
                
                # Calculate and apply punishment
                action, duration, escalation_reason = await self._calculate_punishment(
                    str(interaction.guild_id),
                    str(user.id),
                    severity
                )
                
                if action:
                    await self._apply_punishment(
                        interaction.guild,
                        user,
                        action,
                        duration,
                        escalation_reason
                    )
                
                # Save warning
                await self._save_infraction(
                    str(interaction.guild_id),
                    str(user.id),
                    infractions
                )
                
                warned_users.append(user)
                
            except Exception as e:
                print(f"Error warning user {user.id}: {str(e)}")
                failed_users.append(user)

        # Create result embed
        embed = discord.Embed(
            title="📋 Bulk Warning Results",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if warned_users:
            embed.add_field(
                name="✅ Successfully Warned",
                value="\n".join(f"• {user.mention}" for user in warned_users),
                inline=False
            )
            
        if failed_users:
            embed.add_field(
                name="❌ Failed to Warn",
                value="\n".join(f"• {user.mention}" for user in failed_users),
                inline=False
            )
            
        if invalid_users:
            embed.add_field(
                name="⚠️ Invalid Users",
                value="\n".join(f"• {user_id}" for user_id in invalid_users),
                inline=False
            )

        embed.add_field(name="Reason", value=reason, inline=True)
        embed.add_field(name="Severity", value=f"Level {severity}", inline=True)
        embed.add_field(
            name="Moderator",
            value=interaction.user.mention,
            inline=True
        )

        # Update response
        await progress_msg.edit(content=None, embed=embed)

    @app_commands.command(
        name="unmute",
        description="Unmute a user from the server"
    )
    @app_commands.describe(
        user="The user to unmute",
        reason="Reason for unmuting the user"
    )
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None
    ):
        """Alias for unmute_command"""
        await self.unmute_command(interaction, user, reason)

    @app_commands.command(
        name="unmute_command",
        description="Unmute a user from the server"
    )
    @app_commands.describe(
        user="The user to unmute",
        reason="Reason for unmuting the user"
    )
    async def unmute_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None
    ):
        """Unmute a user from the server"""
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ You don't have permission to unmute members!", ephemeral=True)
            return

        try:
            # Check if user is actually muted
            if not user.is_timed_out():
                await interaction.response.send_message(
                    "❌ This user is not muted!",
                    ephemeral=True
                )
                return

            # Get configuration
            config = await self._get_guild_config(str(interaction.guild_id))
            
            # Check if reason is required
            if config.get("require_reason", True) and not reason:
                await interaction.response.send_message(
                    "❌ A reason is required for unmuting.",
                    ephemeral=True
                )
                return

            # Remove timeout
            await user.timeout(None, reason=reason or f"Unmuted by {interaction.user}")
            
            # Remove from active punishments if exists
            punishment_key = f"{interaction.guild.id}-{user.id}"
            if punishment_key in self.active_punishments:
                del self.active_punishments[punishment_key]
            
            # Create embed response
            embed = discord.Embed(
                title="User Unmuted",
                description=f"{user.mention} has been unmuted.",
                color=discord.Color.green()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Moderator", value=interaction.user.mention)
            
            await interaction.response.send_message(embed=embed)
            
            # Send mod log
            try:
                await self._send_mod_log(interaction.guild, embed)
            except Exception as e:
                self.logger.warning(f"Failed to send mod log: {e}")

            # DM the user if enabled
            if config.get("dm_notifications", True):
                user_embed = discord.Embed(
                    title=f"Unmuted in {interaction.guild.name}",
                    color=discord.Color.green(),
                    description=f"You have been unmuted in {interaction.guild.name}."
                )
                if reason:
                    user_embed.add_field(name="Reason", value=reason)
                await self._notify_user(user, interaction.guild, "unmute", user_embed, config)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to unmute this user!",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error unmuting user: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while unmuting the user.",
                ephemeral=True
            )

    @app_commands.command(
        name="mute",
        description="Mute a user"
    )
    @app_commands.describe(
        user="User to mute",
        duration="Duration in minutes",
        reason="Reason for the mute"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: int,
        reason: str = None
    ):
        """Mute a user for a specified duration"""
        try:
            # Calculate the end time using discord.utils.utcnow()
            until = discord.utils.utcnow() + timedelta(minutes=duration)
            await user.timeout(until, reason=reason)
            
            # Format duration for display
            duration_str = f"{duration} minute{'s' if duration != 1 else ''}"
            
            embed = discord.Embed(
                title="User Muted",
                description=f"{user.mention} has been muted for {duration_str}.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the mute
            try:
                await self.log_action(
                    interaction.guild,
                    "Mute",
                    f"{user.mention} was muted for {duration_str}",
                    interaction.user,
                    reason
                )
            except Exception as e:
                self.logger.error(f"Error logging mute: {e}", exc_info=True)
                
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Error muting user: {str(e)}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Error muting user: {str(e)}", 
                    ephemeral=True
                )
            self.logger.error(f"Error muting user: {str(e)}", exc_info=True)

    @app_commands.command(
        name="kick",
        description="Kick a user from the server"
    )
    @app_commands.describe(
        user="User to kick",
        reason="Reason for the kick"
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = None
    ):
        """Kick a user from the server"""
        try:
            # Kick user
            await user.kick(reason=reason)
            
            # Create embed response
            embed = discord.Embed(
                title="User Kicked",
                description=f"{user.mention} has been kicked.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the kick
            await self.log_action(
                interaction.guild,
                "Kick",
                f"{user.mention} was kicked",
                interaction.user,
                reason
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error kicking user: {str(e)}", ephemeral=True)
            logging.error(f"Error kicking user: {str(e)}", exc_info=True)

    @app_commands.command(
        name="ban",
        description="Ban a user from the server"
    )
    @app_commands.describe(
        user="User to ban",
        reason="Reason for the ban",
        delete_days="Number of days of messages to delete"
    )
    @commands.cooldown(rate=2, per=10.0, type=BucketType.user)  # 2 bans per 10 seconds
    @has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = None,
        delete_days: app_commands.Range[int, 0, 7] = 0
    ):
        """Ban a user from the server with confirmation"""
        try:
            # Permission checks
            if not await self._check_mod_permissions(interaction, user):
                return

            # Get configuration
            config = await self._get_guild_config(str(interaction.guild_id))
            
            # Check if reason is required
            if config.get("require_reason", True) and not reason:
                await interaction.response.send_message(
                    "❌ A reason is required for bans.",
                    ephemeral=True
                )
                return

            # Require confirmation
            if not await self._confirm_action(interaction, "ban", user):
                return

            # Create ban embed
            embed = discord.Embed(
                title="User Banned",
                description=f"{user.mention} has been banned.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Message Deletion", value=f"{delete_days} days")
            
            # Execute ban
            await user.ban(reason=reason, delete_message_days=delete_days)

            # Send response
            await interaction.response.send_message(embed=embed)

            # Send mod log
            await self._send_mod_log(interaction.guild, embed)

            # DM the user if enabled
            if config.get("dm_notifications", True):
                user_embed = discord.Embed(
                    title=f"Banned from {interaction.guild.name}",
                    color=discord.Color.orange(),
                    description=f"You have been banned from {interaction.guild.name}."
                )
                if reason:
                    user_embed.add_field(name="Reason", value=reason)
                await self._notify_user(user, interaction.guild, "ban", user_embed, config)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to ban this user.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error banning user: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while banning the user. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(
        name="unban",
        description="Unban a user from the server"
    )
    @app_commands.describe(
        user="User ID to unban",
        reason="Reason for the unban"
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(
        self,
        interaction: discord.Interaction,
        user: str,
        reason: str = None
    ):
        """Unban a user from the server"""
        try:
            # Unban user
            await interaction.guild.unban(discord.Object(id=int(user)), reason=reason)
            
            # Create embed response
            embed = discord.Embed(
                title="User Unbanned",
                description=f"User {user} has been unbanned.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the unban
            await self.log_action(
                interaction.guild,
                "Unban",
                f"User {user} was unbanned",
                interaction.user,
                reason
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error unbanning user: {str(e)}", ephemeral=True)
            logging.error(f"Error unbanning user: {str(e)}", exc_info=True)

    @app_commands.command(
        name="clean",
        description="Delete messages from the channel"
    )
    @app_commands.describe(
        amount="Number of messages to delete",
        user="Filter messages by user",
        contains="Filter messages containing text"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clean(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        user: Optional[discord.Member] = None,
        contains: Optional[str] = None
    ):
        """Delete messages from the channel"""
        try:
            # Delete messages
            deleted = await interaction.channel.purge(
                limit=amount,
                check=lambda msg: (
                    (user is None or msg.author == user) and
                    (contains is None or contains in msg.content)
                )
            )
            
            # Create embed response
            embed = discord.Embed(
                title="Messages Deleted",
                description=f"{len(deleted)} messages deleted.",
                color=discord.Color.orange()
            )
            if user:
                embed.add_field(name="User", value=user.mention)
            if contains:
                embed.add_field(name="Contains", value=contains)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the clean
            await self.log_action(
                interaction.guild,
                "Clean",
                f"{len(deleted)} messages deleted",
                interaction.user,
                f"User: {user.mention if user else 'None'} | Contains: {contains or 'None'}"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error deleting messages: {str(e)}", ephemeral=True)
            logging.error(f"Error deleting messages: {str(e)}", exc_info=True)

    @app_commands.command(
        name="slowmode",
        description="Set channel slowmode"
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds",
        channel="Channel to set slowmode in"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
        channel: Optional[discord.TextChannel] = None
    ):
        """Set channel slowmode"""
        try:
            # Set slowmode
            if channel is None:
                channel = interaction.channel
            await channel.edit(slowmode_delay=seconds)
            
            # Create embed response
            embed = discord.Embed(
                title="Slowmode Set",
                description=f"Slowmode set to {seconds} seconds.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Channel", value=channel.mention)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the slowmode
            await self.log_action(
                interaction.guild,
                "Slowmode",
                f"Slowmode set to {seconds} seconds",
                interaction.user,
                f"Channel: {channel.mention}"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error setting slowmode: {str(e)}", ephemeral=True)
            logging.error(f"Error setting slowmode: {str(e)}", exc_info=True)

    @app_commands.command(
        name="lock",
        description="Lock a channel"
    )
    @app_commands.describe(
        channel="Channel to lock",
        reason="Reason for locking the channel"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = None
    ):
        """Lock a channel"""
        try:
            # Lock channel
            if channel is None:
                channel = interaction.channel
            await channel.set_permissions(
                interaction.guild.default_role,
                send_messages=False,
                reason=reason
            )
            
            # Create embed response
            embed = discord.Embed(
                title="Channel Locked",
                description=f"{channel.mention} has been locked.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the lock
            await self.log_action(
                interaction.guild,
                "Lock",
                f"{channel.mention} was locked",
                interaction.user,
                reason
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error locking channel: {str(e)}", ephemeral=True)
            logging.error(f"Error locking channel: {str(e)}", exc_info=True)

    @app_commands.command(
        name="unlock",
        description="Unlock a channel"
    )
    @app_commands.describe(
        channel="Channel to unlock",
        reason="Reason for unlocking the channel"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = None
    ):
        """Unlock a channel"""
        try:
            # Unlock channel
            if channel is None:
                channel = interaction.channel
            await channel.set_permissions(
                interaction.guild.default_role,
                send_messages=None,
                reason=reason
            )
            
            # Create embed response
            embed = discord.Embed(
                title="Channel Unlocked",
                description=f"{channel.mention} has been unlocked.",
                color=discord.Color.orange()
            )
            if reason:
                embed.add_field(name="Reason", value=reason)
            
            await interaction.response.send_message(embed=embed)
            
            # Log the unlock
            await self.log_action(
                interaction.guild,
                "Unlock",
                f"{channel.mention} was unlocked",
                interaction.user,
                reason
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error unlocking channel: {str(e)}", ephemeral=True)
            logging.error(f"Error unlocking channel: {str(e)}", exc_info=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import asyncio
import json

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.infractions_key = "infractions"
        self.redemption_key = "redemption_tasks"
        self.escalation_key = "escalation_config"
        self.active_punishments = {}
        self.cleanup_task = None
        self.logger = bot.logger.getChild('moderation')

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self._init_data_structure()
        self.cleanup_task = self.bot.loop.create_task(self._cleanup_warnings())
        self.logger.info("Moderation cog loaded and initialized")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.cleanup_task:
            self.cleanup_task.cancel()

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


    def _get_guild_config(self, guild_id: str) -> dict:
        """Get guild-specific configuration or default"""
        config = self.bot.data_manager.load(self.escalation_key)
        return config.get(str(guild_id), config["default"])

    def _save_guild_config(self, guild_id: str, config: dict):
        """Save guild-specific configuration"""
        all_config = self.bot.data_manager.load(self.escalation_key)
        all_config[str(guild_id)] = config
        self.bot.data_manager.save(self.escalation_key, all_config)

    def _get_user_infractions(self, guild_id: str, user_id: str):
        """Get a user's infractions"""
        infractions = self.bot.data_manager.load(self.infractions_key)
        guild_infractions = infractions.get(guild_id, {})
        return guild_infractions.get(user_id, {"warns": [], "mutes": [], "redemption": 0})

    def _save_infraction(self, guild_id: str, user_id: str, data: dict):
        """Save a user's infractions"""
        infractions = self.bot.data_manager.load(self.infractions_key)
        if guild_id not in infractions:
            infractions[guild_id] = {}
        infractions[guild_id][user_id] = data
        self.bot.data_manager.save(self.infractions_key, infractions)

    def _get_active_warnings(self, guild_id: str, user_id: str) -> list:
        """Get non-expired warnings for a user"""
        infractions = self._get_user_infractions(guild_id, user_id)
        config = self._get_guild_config(guild_id)
        
        active_warnings = []
        for warn in infractions["warns"]:
            if warn.get("redeemed", False):
                continue
                
            warn_time = datetime.fromisoformat(warn["timestamp"])
            expiry_seconds = config["warning_expiry"][str(warn["severity"])]
            
            if (datetime.utcnow() - warn_time).total_seconds() < expiry_seconds:
                active_warnings.append(warn)
        
        return active_warnings

    def _get_all_infractions(self, user_id: str) -> dict:
        """Get all infractions for a user across all servers"""
        all_infractions = self.bot.data_manager.load(self.infractions_key)
        user_infractions = {}
        
        for guild_id, guild_data in all_infractions.items():
            if str(user_id) in guild_data:
                user_infractions[guild_id] = guild_data[str(user_id)]
        
        return user_infractions

    def _calculate_universal_points(self, guild_id: str, user_id: str, new_severity: int) -> int:
        """Calculate warning points including universal warnings if enabled"""
        config = self._get_guild_config(guild_id)
        if not config["universal_warnings"]:
            active_warnings = self._get_active_warnings(guild_id, user_id)
            return sum(
                config["severity_multipliers"][str(w["severity"])]
                for w in active_warnings
            ) + config["severity_multipliers"][str(new_severity)]
        
        # Get warnings from all servers
        total_points = 0
        all_infractions = self._get_all_infractions(user_id)
        
        for server_id, infractions in all_infractions.items():
            server_config = self._get_guild_config(server_id)
            if not server_config["share_warnings"]:
                continue
                
            # Get active warnings for this server
            current_time = datetime.utcnow()
            for warn in infractions.get("warns", []):
                # Skip if not an automatic warning
                if not warn.get("auto_generated", False):
                    continue
                    
                # Skip if warning is redeemed or expired
                if warn.get("redeemed", False):
                    continue
                    
                warn_time = datetime.fromisoformat(warn["timestamp"])
                expiry_seconds = server_config["warning_expiry"][str(warn["severity"])]
                
                if (current_time - warn_time).total_seconds() < expiry_seconds:
                    # Apply server's warning weight
                    weight = config["warning_weight"] if server_id != guild_id else 1.0
                    points = server_config["severity_multipliers"][str(warn["severity"])]
                    total_points += points * weight
        
        # Add points for new warning if it's automatic
        if new_severity > 0:  # Only add if it's a new warning
            total_points += config["severity_multipliers"][str(new_severity)]
        
        return total_points

    async def _calculate_punishment(self, guild_id: str, user_id: str, new_severity: int) -> Tuple[str, int, str]:
        """Calculate appropriate punishment based on warning history"""
        active_warnings = self._get_active_warnings(guild_id, user_id)
        config = self._get_guild_config(guild_id)
        
        # Calculate warning points from active warnings
        total_points = self._calculate_universal_points(guild_id, user_id, new_severity)

        # Find appropriate punishment
        thresholds = config["warning_thresholds"]
        punishment = {"action": None, "duration": 0}
        reason = f"Automated escalation (Warning Points: {total_points})"

        for points, action in sorted(thresholds.items(), key=lambda x: int(x[0])):
            if total_points >= int(points):
                punishment = action

        return punishment["action"], punishment["duration"], reason

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
            if action == "mute":
                # Use timeout for mute
                until = datetime.utcnow() + timedelta(seconds=duration)
                await user.timeout(until, reason=reason)
                
                # Schedule unmute
                self.active_punishments[f"{guild.id}-{user.id}"] = {
                    "type": "mute",
                    "end_time": until.isoformat()
                }
                asyncio.create_task(self._schedule_unmute(guild.id, user.id, duration))
                
            elif action == "kick":
                await user.kick(reason=reason)
                
            elif action == "ban":
                await user.ban(reason=reason, delete_message_days=1)
                
            return True
        except Exception as e:
            print(f"Error applying punishment: {str(e)}")
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
                        print(f"Error removing timeout: {str(e)}")
            
            del self.active_punishments[punishment_key]

    async def _cleanup_warnings(self):
        """Periodically clean up expired warnings"""
        while True:
            try:
                all_infractions = self.bot.data_manager.load(self.infractions_key)
                current_time = datetime.utcnow()
                changes_made = False

                for guild_id, guild_data in all_infractions.items():
                    config = self._get_guild_config(guild_id)
                    retention_period = config["history_retention"]
                    auto_pardon = config["auto_pardon"]

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
                                if config["log_channel"]:
                                    guild = self.bot.get_guild(int(guild_id))
                                    if guild:
                                        log_channel = guild.get_channel(int(config["log_channel"]))
                                        if log_channel:
                                            user = guild.get_member(int(user_id))
                                            user_text = f"{user.mention} ({user_id})" if user else f"User {user_id}"
                                            await log_channel.send(
                                                f"🕊️ Warning automatically pardoned for {user_text}\n"
                                                f"Original Reason: {warn.get('reason', 'No reason provided')}\n"
                                                f"Warning Age: {age//86400:.1f} days"
                                            )

                        if len(retained_warnings) != len(user_data["warns"]):
                            user_data["warns"] = retained_warnings
                            changes_made = True

                if changes_made:
                    self.bot.data_manager.save(self.infractions_key, all_infractions)

                # Get shortest cleanup interval from all guild configs
                cleanup_intervals = [
                    self._get_guild_config(str(guild_id))["cleanup_interval"]
                    for guild_id in all_infractions.keys()
                ]
                await asyncio.sleep(min(cleanup_intervals or [86400]))  # Default to 24h

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in warning cleanup task: {str(e)}")
                await asyncio.sleep(3600)  # Wait an hour on error

    @app_commands.command(
        name="warn",
        description="Warn a user with redemption opportunity"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        severity: Optional[int] = 1  # 1-3, affects redemption requirements
    ):
        """Warn a user and offer redemption path"""
        if severity not in [1, 2, 3]:
            severity = 1

        # Get user's infractions
        infractions = self._get_user_infractions(str(interaction.guild_id), str(user.id))
        
        # Add new warning
        warning = {
            "id": f"w{len(infractions.get('warns', []))+1}",
            "reason": reason,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
            "moderator_id": str(interaction.user.id),
            "redeemed": False
        }
        infractions["warns"].append(warning)
        
        # Calculate and apply punishment
        action, duration, escalation_reason = await self._calculate_punishment(
            str(interaction.guild_id),
            str(user.id),
            severity
        )
        
        punishment_applied = False
        if action:
            punishment_applied = await self._apply_punishment(
                interaction.guild,
                user,
                action,
                duration,
                escalation_reason
            )
        
        # Save updated infractions
        self._save_infraction(str(interaction.guild_id), str(user.id), infractions)

        # Create warning embed
        embed = discord.Embed(
            title="⚠️ Warning Issued",
            color=discord.Color.yellow(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Severity", value=f"Level {severity}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        # Add punishment info if applied
        if action and punishment_applied:
            punishment_text = {
                "mute": f"🔇 Muted for {duration//3600} hours",
                "kick": "👢 Kicked from server",
                "ban": "🔨 Banned from server"
            }.get(action, "Unknown action")
            
            embed.add_field(
                name="Automated Punishment",
                value=f"{punishment_text}\nReason: {escalation_reason}",
                inline=False
            )
        
        # Add redemption info if not banned
        if action != "ban":
            redemption_tasks = self.bot.data_manager.load(self.redemption_key)["tasks"]
            points_needed = severity * 2  # 2 points for level 1, 4 for level 2, 6 for level 3
            
            embed.add_field(
                name="🌟 Redemption Path",
                value=f"Complete tasks to earn {points_needed} redemption points:\n" + \
                      "\n".join([f"• {task['description']} ({task['points']} points)" 
                               for task in redemption_tasks.values()]),
                inline=False
            )

        # Send to user and moderation channel
        try:
            if action != "ban":  # Can't DM if banned
                await user.send(embed=embed)
                embed.add_field(name="Status", value="✅ User notified", inline=False)
        except:
            embed.add_field(name="Status", value="❌ Could not DM user", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="escalationconfig",
        description="Configure warning escalation settings"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def escalation_config(
        self,
        interaction: discord.Interaction,
        setting_type: Optional[str] = None,
        warning_points: Optional[int] = None,
        action: Optional[str] = None,
        duration: Optional[int] = None,
        severity: Optional[int] = None,
        expiry_days: Optional[int] = None,
        reset: Optional[bool] = False,
        log_channel: Optional[discord.TextChannel] = None,
        cleanup_hours: Optional[int] = None,
        retention_days: Optional[int] = None,
        toggle_setting: Optional[str] = None
    ):
        """Configure the warning escalation system"""
        guild_id = str(interaction.guild_id)
        
        if reset:
            # Reset to default configuration
            all_config = self.bot.data_manager.load(self.escalation_key)
            if guild_id in all_config:
                del all_config[guild_id]
                self.bot.data_manager.save(self.escalation_key, all_config)
                await interaction.response.send_message(
                    "✅ Reset to default configuration",
                    ephemeral=True
                )
                return

        config = self._get_guild_config(guild_id)
        
        if not setting_type:
            # Show current config
            embed = discord.Embed(
                title="⚙️ Server Moderation Configuration",
                color=discord.Color.blue()
            )
            
            # Warning Thresholds
            thresholds_text = ""
            for points, data in sorted(
                config["warning_thresholds"].items(),
                key=lambda x: int(x[0])
            ):
                duration_text = f" for {data['duration']//3600}h" if data['duration'] else ""
                thresholds_text += f"{points} points → {data['action'].title()}{duration_text}\n"
            embed.add_field(
                name="Warning Thresholds",
                value=thresholds_text or "None set",
                inline=False
            )
            
            # Severity Multipliers
            multipliers_text = "\n".join(
                f"Level {sev}: {mult}x points"
                for sev, mult in config["severity_multipliers"].items()
            )
            embed.add_field(
                name="Severity Multipliers",
                value=multipliers_text,
                inline=False
            )
            
            # Warning Expiry
            expiry_text = "\n".join(
                f"Level {sev}: {days//86400} days"
                for sev, days in config["warning_expiry"].items()
            )
            embed.add_field(
                name="Warning Expiry",
                value=expiry_text,
                inline=False
            )

            # System Settings
            settings_text = (
                f"🔄 Cleanup Interval: {config['cleanup_interval']//3600}h\n"
                f"📁 History Retention: {config['history_retention']//86400} days\n"
                f"📨 DM Notifications: {config['dm_notifications']}\n"
                f"📝 Require Reason: {config['require_reason']}\n"
                f"🤝 Allow Appeals: {config['allow_appeals']}\n"
                f"⏳ Appeal Cooldown: {config['appeal_cooldown']//86400} days\n"
                f"🗑️ Auto-Pardon: {config['auto_pardon']}\n"
                f"📢 Log Channel: {'<#' + str(config['log_channel']) + '>' if config['log_channel'] else 'None'}\n"
                f"🌐 Universal Warnings: {config['universal_warnings']} (Auto-warnings only)\n"
                f"🤝 Share Warnings: {config['share_warnings']}\n"
                f"⚖️ Warning Weight: {config['warning_weight']}"
            )
            embed.add_field(name="System Settings", value=settings_text, inline=False)
            
            # Note if using default config
            if guild_id not in self.bot.data_manager.load(self.escalation_key):
                embed.set_footer(text="Using default configuration")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Create guild-specific config if using default
        if guild_id not in self.bot.data_manager.load(self.escalation_key):
            self._save_guild_config(guild_id, config.copy())

        # Handle different setting types
        if setting_type == "threshold" and warning_points and action:
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

        elif setting_type == "multiplier" and severity:
            if severity not in [1, 2, 3]:
                await interaction.response.send_message(
                    "❌ Severity must be 1, 2, or 3!",
                    ephemeral=True
                )
                return

            config["severity_multipliers"][str(severity)] = warning_points or 1

        elif setting_type == "expiry" and severity and expiry_days:
            if severity not in [1, 2, 3]:
                await interaction.response.send_message(
                    "❌ Severity must be 1, 2, or 3!",
                    ephemeral=True
                )
                return

            if expiry_days < 1:
                await interaction.response.send_message(
                    "❌ Expiry days must be positive!",
                    ephemeral=True
                )
                return

            config["warning_expiry"][str(severity)] = expiry_days * 86400

        elif setting_type == "system":
            if log_channel is not None:
                config["log_channel"] = str(log_channel.id) if log_channel else None

            if cleanup_hours is not None:
                if cleanup_hours < 1:
                    await interaction.response.send_message(
                        "❌ Cleanup interval must be positive!",
                        ephemeral=True
                    )
                    return
                config["cleanup_interval"] = cleanup_hours * 3600

            if retention_days is not None:
                if retention_days < 1:
                    await interaction.response.send_message(
                        "❌ Retention period must be positive!",
                        ephemeral=True
                    )
                    return
                config["history_retention"] = retention_days * 86400

            if toggle_setting:
                valid_toggles = [
                    "dm_notifications", "require_reason",
                    "allow_appeals", "auto_pardon",
                    "universal_warnings", "share_warnings"
                ]
                if toggle_setting not in valid_toggles:
                    await interaction.response.send_message(
                        f"❌ Invalid toggle! Use: {', '.join(valid_toggles)}",
                        ephemeral=True
                    )
                    return
                config[toggle_setting] = not config[toggle_setting]

            if warning_points is not None:
                if warning_points < 0 or warning_points > 1:
                    await interaction.response.send_message(
                        "❌ Warning weight must be between 0 and 1!",
                        ephemeral=True
                    )
                    return
                config["warning_weight"] = warning_points

        else:
            await interaction.response.send_message(
                "❌ Invalid configuration! Use:\n"
                "• threshold: Set warning point thresholds\n"
                "• multiplier: Set severity multipliers\n"
                "• expiry: Set warning expiry time\n"
                "• system: Configure system settings",
                ephemeral=True
            )
            return

        self._save_guild_config(guild_id, config)
        await interaction.response.send_message(
            "✅ Configuration updated!",
            ephemeral=True
        )

    @app_commands.command(
        name="redeem",
        description="Submit a redemption task for review"
    )
    async def redeem(
        self,
        interaction: discord.Interaction,
        task: str,
        proof: str
    ):
        """Submit a redemption task for moderator review"""
        # Check if user has warnings to redeem
        infractions = self._get_user_infractions(
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
        redemption_tasks = self.bot.data_manager.load(self.redemption_key)["tasks"]
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
        description="View a user's infractions and redemption status"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def infractions(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):
        """View a user's infractions and redemption progress"""
        infractions = self._get_user_infractions(str(interaction.guild_id), str(user.id))
        
        embed = discord.Embed(
            title=f"📋 Infractions for {user.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Add warnings
        if infractions["warns"]:
            warns_text = ""
            for i, warn in enumerate(infractions["warns"], 1):
                status = "✅ Redeemed" if warn["redeemed"] else "❌ Not Redeemed"
                moderator = interaction.guild.get_member(int(warn["moderator_id"]))
                mod_name = moderator.display_name if moderator else "Unknown Moderator"
                warns_text += f"{i}. {warn['reason']} (Level {warn['severity']})\n" \
                            f"By: {mod_name} | Status: {status}\n\n"
            embed.add_field(name="Warnings", value=warns_text, inline=False)
        else:
            embed.add_field(name="Warnings", value="No warnings on record", inline=False)

        # Add mutes if any
        if infractions.get("mutes"):
            mutes_text = ""
            for mute in infractions["mutes"]:
                end_time = datetime.fromisoformat(mute["end_time"])
                if end_time > datetime.utcnow():
                    mutes_text += f"• Until {end_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    mutes_text += f"Reason: {mute['reason']}\n\n"
            if mutes_text:
                embed.add_field(name="Active Mutes", value=mutes_text, inline=False)

        # Add redemption progress
        embed.add_field(
            name="Redemption Progress",
            value=f"Points Earned: {infractions.get('redemption', 0)}",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="appeal",
        description="Appeal a warning"
    )
    async def appeal(
        self,
        interaction: discord.Interaction,
        warning_id: str,
        reason: str
    ):
        """Appeal a warning"""
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        
        # Get user's infractions and config
        infractions = self._get_user_infractions(guild_id, user_id)
        config = self._get_guild_config(guild_id)
        
        if not config["allow_appeals"]:
            await interaction.response.send_message(
                "❌ Appeals are not enabled on this server",
                ephemeral=True
            )
            return

        # Find the warning
        warning = None
        for warn in infractions.get("warns", []):
            if warn.get("id") == warning_id:
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
        self._save_infraction(guild_id, user_id, infractions)

        # Create appeal embed
        embed = discord.Embed(
            title="📋 Warning Appeal",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.add_field(name="Warning ID", value=warning_id, inline=True)
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
            custom_id=f"appeal_approve_{user_id}_{warning_id}"
        )
        deny_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Deny Appeal",
            custom_id=f"appeal_deny_{user_id}_{warning_id}"
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
    @app_commands.checks.has_permissions(moderate_members=True)
    async def manage_appeal(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        warning_id: str,
        action: str,  # approve/deny
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
        infractions = self._get_user_infractions(
            str(interaction.guild_id),
            str(user.id)
        )
        
        warning = None
        for warn in infractions.get("warns", []):
            if warn.get("id") == warning_id:
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
                    description=f"Your appeal for warning {warning_id} has been approved!"
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
                    description=f"Your appeal for warning {warning_id} has been denied."
                )
                if reason:
                    embed.add_field(name="Reason", value=reason)
                await user.send(embed=embed)
            except:
                pass

        # Save changes
        self._save_infraction(
            str(interaction.guild_id),
            str(user.id),
            infractions
        )

        # Log action
        config = self._get_guild_config(str(interaction.guild_id))
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
                embed.add_field(name="Warning ID", value=warning_id, inline=True)
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
        source_config = self._get_guild_config(from_server)
        if not source_config["share_warnings"]:
            await interaction.response.send_message(
                "❌ Source server does not share warnings!",
                ephemeral=True
            )
            return

        # Get source warnings
        source_infractions = self._get_user_infractions(from_server, str(user.id))
        if not source_infractions.get("warns"):
            await interaction.response.send_message(
                "❌ No warnings found in source server!",
                ephemeral=True
            )
            return

        # Get target infractions
        target_infractions = self._get_user_infractions(
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
        self._save_infraction(
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
        config = self._get_guild_config(str(interaction.guild_id))
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
    @app_commands.checks.has_permissions(moderate_members=True)
    async def bulk_warn(
        self,
        interaction: discord.Interaction,
        users: str,  # Comma-separated user mentions or IDs
        reason: str,
        severity: Optional[int] = 1
    ):
        """Warn multiple users at once"""
        if severity not in [1, 2, 3]:
            severity = 1

        # Parse users
        user_ids = []
        for user_ref in users.split(","):
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
                infractions = self._get_user_infractions(
                    str(interaction.guild_id),
                    str(user.id)
                )
                
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
                self._save_infraction(
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

async def setup(bot):
    await bot.add_cog(Moderation(bot))

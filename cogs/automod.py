import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from collections import defaultdict
import re
import time
import asyncio

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.automod_key = "automod_config"
        self.message_trackers = {}  # guild_id -> {user_id: [message_timestamps]}
        self.join_trackers = {}     # guild_id -> [join_timestamps]
        self.cleanup_trackers.start()

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self.init_data()

    async def init_data(self):
        """Initialize automod configuration"""
        if not await self.bot.data_manager.exists("automod", "key = ?", self.automod_key):
            await self.bot.data_manager.save_json("automod", self.automod_key, {
                "default": {
                    "enabled": True,
                    "spam_settings": {
                        "message_threshold": 5,  # messages
                        "time_window": 5,        # seconds
                        "repeat_threshold": 3,    # repeated messages
                        "mention_limit": 3,      # mentions per message
                        "punishment": "timeout",  # mute/kick/ban
                        "duration": 300          # 5 minutes
                    },
                    "raid_settings": {
                        "join_threshold": 5,     # joins
                        "join_window": 10,       # seconds
                        "account_age": 86400,    # 1 day in seconds
                        "action": "lockdown",    # lockdown/kick
                        "duration": 300          # 5 minutes
                    },
                    "quiet_hours": {
                        "enabled": False,
                        "start": "22:00",        # 24-hour format
                        "end": "06:00",
                        "stricter_limits": True
                    },
                    "exempt_roles": [],
                    "log_channel": None
                }
            })

    async def get_config(self, guild_id: str) -> dict:
        """Get guild-specific or default config"""
        config = await self.bot.data_manager.load_json("automod", self.automod_key)
        return config.get(str(guild_id), config["default"])

    @tasks.loop(minutes=5)
    async def cleanup_trackers(self):
        """Clean up old tracking data"""
        current_time = time.time()
        
        # Clean up message trackers
        for guild_id in self.message_trackers:
            for user_id in list(self.message_trackers[guild_id].keys()):
                # Remove messages older than the time window
                self.message_trackers[guild_id][user_id] = [
                    ts for ts in self.message_trackers[guild_id][user_id]
                    if current_time - ts <= 60  # 1 minute window
                ]
                
                # Remove user if no recent messages
                if not self.message_trackers[guild_id][user_id]:
                    del self.message_trackers[guild_id][user_id]
            
            # Remove guild if no users
            if not self.message_trackers[guild_id]:
                del self.message_trackers[guild_id]
        
        # Clean up join trackers
        for guild_id in list(self.join_trackers.keys()):
            # Remove joins older than the time window
            self.join_trackers[guild_id] = [
                ts for ts in self.join_trackers[guild_id]
                if current_time - ts <= 300  # 5 minute window
            ]
            
            # Remove guild if no recent joins
            if not self.join_trackers[guild_id]:
                del self.join_trackers[guild_id]

    @app_commands.command(
        name="automod",
        description="Configure automod settings"
    )
    @app_commands.default_permissions(administrator=True)
    async def automod_config(
        self,
        interaction: discord.Interaction,
        setting: str,
        value: str
    ):
        """Configure automod settings"""
        config = await self.bot.data_manager.load_json("automod", self.automod_key)
        guild_id = str(interaction.guild_id)
        
        if guild_id not in config:
            config[guild_id] = config["default"].copy()
        
        parts = setting.lower().split('.')
        current = config[guild_id]
        
        try:
            # Navigate to the nested setting
            for part in parts[:-1]:
                current = current[part]
            
            # Convert value to appropriate type
            if isinstance(current[parts[-1]], bool):
                current[parts[-1]] = value.lower() == "true"
            elif isinstance(current[parts[-1]], int):
                current[parts[-1]] = int(value)
            else:
                current[parts[-1]] = value
            
            await self.bot.data_manager.save_json("automod", self.automod_key, config)
            await interaction.response.send_message(
                f"✅ Updated {setting} to {value}",
                ephemeral=True
            )
        except:
            await interaction.response.send_message(
                "❌ Invalid setting or value",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle message spam detection"""
        if not message.guild or message.author.bot:
            return
            
        config = await self.get_config(str(message.guild.id))
        if not config["enabled"]:
            return

        # Check exemptions
        member = message.guild.get_member(message.author.id)
        if any(role.id in config["exempt_roles"] for role in member.roles):
            return

        # Track message
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        current_time = time.time()
        
        # Add message timestamp
        if guild_id not in self.message_trackers:
            self.message_trackers[guild_id] = {}
        if user_id not in self.message_trackers[guild_id]:
            self.message_trackers[guild_id][user_id] = []
        self.message_trackers[guild_id][user_id].append(current_time)
        
        # Get settings
        settings = config["spam_settings"]
        window = settings["time_window"]
        
        # Check quiet hours
        if config["quiet_hours"]["enabled"]:
            current_hour = datetime.utcnow().hour
            start_hour = int(config["quiet_hours"]["start"].split(":")[0])
            end_hour = int(config["quiet_hours"]["end"].split(":")[0])
            
            is_quiet_hours = False
            if start_hour > end_hour:  # Crosses midnight
                is_quiet_hours = current_hour >= start_hour or current_hour < end_hour
            else:
                is_quiet_hours = start_hour <= current_hour < end_hour
                
            if is_quiet_hours and config["quiet_hours"]["stricter_limits"]:
                settings["message_threshold"] //= 2
                settings["mention_limit"] //= 2

        # Check recent messages
        recent_messages = [
            ts for ts in self.message_trackers[guild_id][user_id]
            if current_time - ts <= window
        ]
        
        should_punish = False
        reason = None

        # Check message count
        if len(recent_messages) > settings["message_threshold"]:
            should_punish = True
            reason = f"Sending messages too quickly ({len(recent_messages)} in {settings['time_window']}s)"

        # Check mentions
        elif len(message.mentions) > settings["mention_limit"]:
            should_punish = True
            reason = f"Too many mentions ({len(message.mentions)})"

        # Check repeated messages
        elif len(recent_messages) >= settings["repeat_threshold"]:
            last_messages = [msg.content for msg in message.channel.history(limit=settings["repeat_threshold"])]
            if all(msg == message.content for msg in last_messages):
                should_punish = True
                reason = "Repeated messages"

        if should_punish:
            # Apply punishment
            try:
                if settings["punishment"] == "timeout":
                    await member.timeout(
                        timedelta(seconds=settings["duration"]),
                        reason=reason
                    )
                elif settings["punishment"] == "kick":
                    await member.kick(reason=reason)
                elif settings["punishment"] == "ban":
                    await member.ban(reason=reason, delete_message_days=1)
                
                # Log if channel is set
                if config["log_channel"]:
                    channel = message.guild.get_channel(int(config["log_channel"]))
                    if channel:
                        embed = discord.Embed(
                            title="🛡️ AutoMod Action",
                            description=f"Action taken against {member.mention}",
                            color=discord.Color.red(),
                            timestamp=datetime.utcnow()
                        )
                        embed.add_field(name="Reason", value=reason)
                        embed.add_field(
                            name="Punishment",
                            value=f"{settings['punishment']} ({settings['duration']}s)"
                        )
                        await channel.send(embed=embed)
                
                # Delete spam messages
                await message.channel.purge(
                    limit=len(recent_messages),
                    check=lambda m: m.author.id == message.author.id
                )
            except discord.Forbidden:
                print(f"Missing permissions for automod in {message.guild.name}")

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
                    print(f"Missing permissions for raid lockdown in {member.guild.name}")
            
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
            print(f"Missing permissions to end lockdown in {guild.name}")

async def setup(bot):
    await bot.add_cog(AutoMod(bot))

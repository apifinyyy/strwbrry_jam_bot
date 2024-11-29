import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import asyncio

class ServerManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_key = "server_config"
        self.init_data()
        self.check_server_settings.start()

    def init_data(self):
        """Initialize server configuration data"""
        if not self.bot.data_manager.exists(self.server_key):
            self.bot.data_manager.save(self.server_key, {
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
            })

    @tasks.loop(minutes=5)
    async def check_server_settings(self):
        """Periodic check of server settings"""
        config = self.bot.data_manager.load(self.server_key)
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
                        pass

        # Update server stats
        for guild_id, stats in config.get("server_stats", {}).items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            for stat_type, channel_id in stats.items():
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue

                try:
                    if stat_type == "member_count":
                        await channel.edit(name=f"Members: {guild.member_count}")
                    elif stat_type == "bot_count":
                        bot_count = len([m for m in guild.members if m.bot])
                        await channel.edit(name=f"Bots: {bot_count}")
                    elif stat_type == "channel_count":
                        await channel.edit(name=f"Channels: {len(guild.channels)}")
                    elif stat_type == "boost_level":
                        await channel.edit(name=f"Boost Level: {guild.premium_tier}")
                    elif stat_type == "active_members":
                        # Count members who sent messages in last 24h
                        active = len(await self.get_active_members(guild))
                        await channel.edit(name=f"Active: {active}")
                    elif stat_type == "role_count":
                        await channel.edit(name=f"Roles: {len(guild.roles)}")
                except discord.Forbidden:
                    pass

        # Check backup schedule
        for guild_id, schedule in config.get("backup_schedule", {}).items():
            if current_time.timestamp() - schedule["last_backup"] >= schedule["interval"]:
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    await self.create_backup(guild)

        self.bot.data_manager.save(self.server_key, config)

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

    @app_commands.command(
        name="createautochannel",
        description="Set up an auto-creating voice channel category"
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
        try:
            category = await interaction.guild.create_category(category_name)
            await category.create_voice_channel(f"{channel_template} 1")
            
            config = self.bot.data_manager.load(self.server_key)
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
            
            self.bot.data_manager.save(self.server_key, config)
            
            await interaction.response.send_message(
                f"✅ Created auto-channel category {category_name}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to create channels",
                ephemeral=True
            )

    @app_commands.command(
        name="setserverstats",
        description="Set up server statistics channels"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_server_stats(
        self,
        interaction: discord.Interaction,
        stat_type: str,  # member_count, bot_count, channel_count
        channel: Optional[discord.VoiceChannel] = None
    ):
        """Set up server statistics channels"""
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild.id)
        
        if "server_stats" not in config:
            config["server_stats"] = {}
        if guild_id not in config["server_stats"]:
            config["server_stats"][guild_id] = {}
        
        try:
            if not channel:
                # Create new channel
                category = await interaction.guild.create_category("📊 Server Stats")
                channel = await category.create_voice_channel("Loading...")
                await channel.set_permissions(
                    interaction.guild.default_role,
                    connect=False
                )
            
            config["server_stats"][guild_id][stat_type] = str(channel.id)
            self.bot.data_manager.save(self.server_key, config)
            
            # Update immediately
            if stat_type == "member_count":
                await channel.edit(
                    name=f"Members: {interaction.guild.member_count}"
                )
            elif stat_type == "bot_count":
                bot_count = len([m for m in interaction.guild.members if m.bot])
                await channel.edit(name=f"Bots: {bot_count}")
            elif stat_type == "channel_count":
                await channel.edit(
                    name=f"Channels: {len(interaction.guild.channels)}"
                )
            
            await interaction.response.send_message(
                f"✅ Set up {stat_type} counter",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to manage channels",
                ephemeral=True
            )

    @app_commands.command(
        name="setauditlog",
        description="Set up audit logging"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_audit_log(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        events: str = "all"  # Comma-separated list of events or 'all'
    ):
        """Set up audit logging"""
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild_id)
        
        if "audit_log" not in config:
            config["audit_log"] = {}
        
        config["audit_log"][guild_id] = {
            "channel_id": str(channel.id),
            "filters": events.split(',') if events != "all" else "all"
        }
        
        self.bot.data_manager.save(self.server_key, config)
        
        await interaction.response.send_message(
            f"✅ Set {channel.mention} as audit log channel",
            ephemeral=True
        )

    @app_commands.command(
        name="setcleanup",
        description="Set up channel cleanup rules"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_cleanup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        max_age: int,  # hours
        exempt_roles: Optional[str] = None  # Comma-separated role mentions
    ):
        """Set up channel cleanup rules"""
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild_id)
        
        if "cleanup_rules" not in config:
            config["cleanup_rules"] = {}
        if guild_id not in config["cleanup_rules"]:
            config["cleanup_rules"][guild_id] = {}
        
        exempt_role_ids = []
        if exempt_roles:
            for role_str in exempt_roles.split(','):
                role_str = role_str.strip()
                if role_str.startswith('<@&') and role_str.endswith('>'):
                    exempt_role_ids.append(role_str[3:-1])
        
        config["cleanup_rules"][guild_id][str(channel.id)] = {
            "max_age": max_age * 3600,  # convert to seconds
            "exempt_roles": exempt_role_ids
        }
        
        self.bot.data_manager.save(self.server_key, config)
        
        await interaction.response.send_message(
            f"✅ Set cleanup rules for {channel.mention}\n"
            f"Messages older than {max_age} hours will be deleted\n"
            f"Exempt roles: {exempt_roles if exempt_roles else 'None'}",
            ephemeral=True
        )

    @app_commands.command(
        name="setupbackup",
        description="Set up automatic server backups"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_backup(
        self,
        interaction: discord.Interaction,
        interval: int  # hours
    ):
        """Set up automatic server backups"""
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild_id)
        
        if "backup_schedule" not in config:
            config["backup_schedule"] = {}
            
        config["backup_schedule"][guild_id] = {
            "interval": interval * 3600,  # convert to seconds
            "last_backup": 0  # force immediate backup
        }
        
        self.bot.data_manager.save(self.server_key, config)
        
        # Create initial backup
        await self.create_backup(interaction.guild)
        
        await interaction.response.send_message(
            f"✅ Server backups scheduled every {interval} hours",
            ephemeral=True
        )

    @app_commands.command(
        name="createbackup",
        description="Create a manual server backup"
    )
    @app_commands.default_permissions(administrator=True)
    async def manual_backup(self, interaction: discord.Interaction):
        """Create a manual server backup"""
        await interaction.response.defer(ephemeral=True)
        
        backup = await self.create_backup(interaction.guild)
        if backup:
            await interaction.followup.send(
                "✅ Server backup created successfully!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Failed to create backup",
                ephemeral=True
            )

    @app_commands.command(
        name="restorebackup",
        description="Restore a server backup"
    )
    @app_commands.default_permissions(administrator=True)
    async def restore_backup(
        self,
        interaction: discord.Interaction,
        timestamp: str = "latest"
    ):
        """Restore a server backup"""
        await interaction.response.defer(ephemeral=True)
        
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild_id)
        
        if guild_id not in config.get("backups", {}):
            await interaction.followup.send(
                "❌ No backups found for this server",
                ephemeral=True
            )
            return
            
        backups = config["backups"][guild_id]
        if not backups:
            await interaction.followup.send(
                "❌ No backups found for this server",
                ephemeral=True
            )
            return
            
        if timestamp == "latest":
            timestamp = max(backups.keys())
        elif timestamp not in backups:
            await interaction.followup.send(
                "❌ Backup not found for specified timestamp",
                ephemeral=True
            )
            return
            
        backup_data = backups[timestamp]
        
        try:
            # Restore roles
            for role_data in backup_data["roles"]:
                if not discord.utils.get(interaction.guild.roles, name=role_data["name"]):
                    await interaction.guild.create_role(
                        name=role_data["name"],
                        permissions=discord.Permissions(role_data["permissions"]),
                        color=discord.Color(role_data["color"]),
                        hoist=role_data["hoist"],
                        mentionable=role_data["mentionable"]
                    )
            
            # Restore channels
            for category_data in backup_data["categories"]:
                category = await interaction.guild.create_category(
                    name=category_data["name"],
                    position=category_data["position"]
                )
                
                for channel_data in category_data["channels"]:
                    if channel_data["type"] == "text":
                        await category.create_text_channel(
                            name=channel_data["name"],
                            topic=channel_data.get("topic", ""),
                            slowmode_delay=channel_data.get("slowmode_delay", 0),
                            nsfw=channel_data.get("nsfw", False)
                        )
                    elif channel_data["type"] == "voice":
                        await category.create_voice_channel(
                            name=channel_data["name"],
                            user_limit=channel_data.get("user_limit", 0)
                        )
            
            await interaction.followup.send(
                f"✅ Restored backup from {timestamp}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to restore backup",
                ephemeral=True
            )

    async def create_backup(self, guild: discord.Guild) -> bool:
        """Create a server backup"""
        try:
            backup_data = {
                "roles": [
                    {
                        "name": role.name,
                        "permissions": role.permissions.value,
                        "color": role.color.value,
                        "hoist": role.hoist,
                        "mentionable": role.mentionable
                    }
                    for role in guild.roles
                    if role != guild.default_role
                ],
                "categories": []
            }
            
            for category in guild.categories:
                category_data = {
                    "name": category.name,
                    "position": category.position,
                    "channels": []
                }
                
                for channel in category.channels:
                    channel_data = {
                        "name": channel.name,
                        "type": "text" if isinstance(channel, discord.TextChannel) else "voice"
                    }
                    
                    if isinstance(channel, discord.TextChannel):
                        channel_data.update({
                            "topic": channel.topic,
                            "slowmode_delay": channel.slowmode_delay,
                            "nsfw": channel.nsfw
                        })
                    elif isinstance(channel, discord.VoiceChannel):
                        channel_data.update({
                            "user_limit": channel.user_limit
                        })
                    
                    category_data["channels"].append(channel_data)
                
                backup_data["categories"].append(category_data)
            
            config = self.bot.data_manager.load(self.server_key)
            guild_id = str(guild.id)
            
            if "backups" not in config:
                config["backups"] = {}
            if guild_id not in config["backups"]:
                config["backups"][guild_id] = {}
                
            # Keep only last 5 backups
            backups = config["backups"][guild_id]
            if len(backups) >= 5:
                oldest = min(backups.keys())
                del backups[oldest]
            
            timestamp = datetime.utcnow().isoformat()
            config["backups"][guild_id][timestamp] = backup_data
            
            if guild_id in config.get("backup_schedule", {}):
                config["backup_schedule"][guild_id]["last_backup"] = datetime.utcnow().timestamp()
            
            self.bot.data_manager.save(self.server_key, config)
            return True
            
        except Exception as e:
            print(f"Backup failed for guild {guild.id}: {str(e)}")
            return False

    @app_commands.command(
        name="listbackups",
        description="List available server backups"
    )
    @app_commands.default_permissions(administrator=True)
    async def list_backups(self, interaction: discord.Interaction):
        """List available server backups"""
        config = self.bot.data_manager.load(self.server_key)
        guild_id = str(interaction.guild_id)
        
        if guild_id not in config.get("backups", {}):
            await interaction.response.send_message(
                "❌ No backups found for this server",
                ephemeral=True
            )
            return
            
        backups = config["backups"][guild_id]
        if not backups:
            await interaction.response.send_message(
                "❌ No backups found for this server",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Server Backups",
            color=discord.Color.blue()
        )
        
        for timestamp in sorted(backups.keys(), reverse=True):
            backup = backups[timestamp]
            embed.add_field(
                name=timestamp,
                value=f"Roles: {len(backup['roles'])}\n"
                      f"Categories: {len(backup['categories'])}",
                inline=False
            )
        
        await interaction.response.send_message(
            embed=embed,
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
        config = self.bot.data_manager.load(self.server_key)
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
        config = self.bot.data_manager.load(self.server_key)
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

async def setup(bot):
    await bot.add_cog(ServerManager(bot))

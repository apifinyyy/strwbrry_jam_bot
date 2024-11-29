import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import json
from datetime import datetime
import uuid
import re
from datetime import timedelta

class Broadcast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.broadcast_key = "broadcast_config"
        self._init_data_structure()
        self.check_scheduled_broadcasts.start()

    def _init_data_structure(self):
        """Initialize the broadcast configuration in data manager if it doesn't exist"""
        if not self.bot.data_manager.exists(self.broadcast_key):
            self.bot.data_manager.save(self.broadcast_key, {
                "channels": {},         # guild_id -> channel_id
                "enabled": {},          # guild_id -> bool
                "scheduled": {},        # message_id -> {content, timestamp, repeat_interval, guilds}
                "interactive": {},      # message_id -> {options, votes, end_time}
                "templates": {},        # template_name -> {content, variables}
                "history": {},          # guild_id -> [message_ids]
                "analytics": {}         # message_id -> {views, reactions, responses}
            })

    @tasks.loop(minutes=1)
    async def check_scheduled_broadcasts(self):
        """Check and send scheduled broadcasts"""
        config = self.bot.data_manager.load(self.broadcast_key)
        current_time = datetime.utcnow()
        
        for msg_id, schedule in list(config.get("scheduled", {}).items()):
            if current_time.timestamp() >= schedule["timestamp"]:
                # Send the broadcast
                success = await self.send_broadcast(
                    schedule["content"],
                    schedule.get("guilds", None)
                )
                
                if success and schedule.get("repeat_interval"):
                    # Update timestamp for next broadcast
                    config["scheduled"][msg_id]["timestamp"] += schedule["repeat_interval"]
                else:
                    # Remove one-time broadcast
                    del config["scheduled"][msg_id]
                
                self.bot.data_manager.save(self.broadcast_key, config)

    @app_commands.command(
        name="setupbroadcast",
        description="Set up a channel to receive bot broadcasts"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_broadcast(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None
    ):
        """Set up a broadcast channel for the server"""
        # Use current channel if none specified
        channel = channel or interaction.channel

        # Get current broadcast config
        broadcast_config = self.bot.data_manager.load(self.broadcast_key)
        
        # Update config for this server
        broadcast_config["channels"][str(interaction.guild_id)] = channel.id
        broadcast_config["enabled"][str(interaction.guild_id)] = True
        
        # Save updated config
        self.bot.data_manager.save(self.broadcast_key, broadcast_config)
        
        await interaction.response.send_message(
            f"✅ Broadcast channel set to {channel.mention}. You will now receive bot announcements here.",
            ephemeral=True
        )

    @app_commands.command(
        name="disablebroadcast",
        description="Disable bot broadcasts for this server"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_broadcast(self, interaction: discord.Interaction):
        """Disable broadcasts for the server"""
        broadcast_config = self.bot.data_manager.load(self.broadcast_key)
        
        if str(interaction.guild_id) not in broadcast_config["enabled"]:
            await interaction.response.send_message(
                "❌ Broadcasts are not set up for this server.",
                ephemeral=True
            )
            return
        
        broadcast_config["enabled"][str(interaction.guild_id)] = False
        self.bot.data_manager.save(self.broadcast_key, broadcast_config)
        
        await interaction.response.send_message(
            "✅ Broadcasts have been disabled for this server.",
            ephemeral=True
        )

    @app_commands.command(
        name="enablebroadcast",
        description="Enable bot broadcasts for this server"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_broadcast(self, interaction: discord.Interaction):
        """Enable broadcasts for the server"""
        broadcast_config = self.bot.data_manager.load(self.broadcast_key)
        
        if str(interaction.guild_id) not in broadcast_config["enabled"]:
            await interaction.response.send_message(
                "❌ Please set up broadcasts first using `/setupbroadcast`.",
                ephemeral=True
            )
            return
        
        broadcast_config["enabled"][str(interaction.guild_id)] = True
        self.bot.data_manager.save(self.broadcast_key, broadcast_config)
        
        await interaction.response.send_message(
            "✅ Broadcasts have been enabled for this server.",
            ephemeral=True
        )

    @app_commands.command(
        name="broadcast",
        description="Send a broadcast message to all configured servers"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def broadcast(
        self,
        interaction: discord.Interaction,
        message: str,
        ping_everyone: Optional[bool] = False,
        color: Optional[str] = None
    ):
        """Send a broadcast to all configured channels"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can send broadcasts.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        broadcast_config = self.bot.data_manager.load(self.broadcast_key)
        success_count = 0
        fail_count = 0
        
        embed = discord.Embed(
            title="📢 Bot Broadcast",
            description=message,
            color=discord.Color.from_str(color) if color else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"From: {interaction.user.name}")

        analytics_cog = self.bot.get_cog('BroadcastAnalytics')
        
        for guild_id, channel_id in broadcast_config.get("channels", {}).items():
            if not broadcast_config.get("enabled", {}).get(str(guild_id), True):
                continue
                
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    raise Exception("Could not find guild")
                    
                channel = guild.get_channel(channel_id)
                if channel:
                    content = "@everyone " if ping_everyone else ""
                    await channel.send(content=content, embed=embed)
                    success_count += 1
                    
                    # Update analytics if available
                    if analytics_cog:
                        analytics_cog.update_stats(guild_id, True, guild.member_count)
                    
                    # Update last broadcast time
                    if "history" not in broadcast_config:
                        broadcast_config["history"] = {}
                    if str(guild_id) not in broadcast_config["history"]:
                        broadcast_config["history"][str(guild_id)] = []
                    broadcast_config["history"][str(guild_id)].append(message)
                else:
                    raise Exception("Could not find channel")
            except Exception as e:
                fail_count += 1
                if analytics_cog:
                    analytics_cog.update_stats(guild_id, False, 
                                            guild.member_count if guild else 0)
                print(f"Failed to send broadcast to guild {guild_id}: {str(e)}")

        self.bot.data_manager.save(self.broadcast_key, broadcast_config)
        
        await interaction.followup.send(
            f"✅ Broadcast sent!\nSuccess: {success_count} servers\nFailed: {fail_count} servers",
            ephemeral=True
        )

    async def send_broadcast(self, message, guilds=None):
        """Send a broadcast to all configured channels"""
        broadcast_config = self.bot.data_manager.load(self.broadcast_key)
        success_count = 0
        fail_count = 0
        
        embed = discord.Embed(
            title="📢 Bot Broadcast",
            description=message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for guild_id, channel_id in broadcast_config.get("channels", {}).items():
            if guilds and str(guild_id) not in guilds:
                continue
            if not broadcast_config.get("enabled", {}).get(str(guild_id), True):
                continue
                
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    raise Exception("Could not find guild")
                    
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.send(embed=embed)
                    success_count += 1
                else:
                    raise Exception("Could not find channel")
            except Exception as e:
                fail_count += 1
                print(f"Failed to send broadcast to guild {guild_id}: {str(e)}")

        return success_count > 0

    @app_commands.command(
        name="schedulebroadcast",
        description="Schedule a broadcast message"
    )
    @app_commands.default_permissions(administrator=True)
    async def schedule_broadcast(
        self,
        interaction: discord.Interaction,
        content: str,
        timestamp: str,  # ISO format
        repeat_hours: int = 0
    ):
        """Schedule a broadcast message"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can schedule broadcasts",
                ephemeral=True
            )
            return

        try:
            broadcast_time = datetime.fromisoformat(timestamp)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid timestamp format. Use ISO format (YYYY-MM-DDTHH:MM:SS)",
                ephemeral=True
            )
            return

        config = self.bot.data_manager.load(self.broadcast_key)
        msg_id = str(uuid.uuid4())
        
        config["scheduled"][msg_id] = {
            "content": content,
            "timestamp": broadcast_time.timestamp(),
            "repeat_interval": repeat_hours * 3600 if repeat_hours > 0 else None,
            "guilds": None  # Broadcast to all configured channels
        }
        
        self.bot.data_manager.save(self.broadcast_key, config)
        
        await interaction.response.send_message(
            f"✅ Broadcast scheduled for {timestamp}" + 
            (f" (repeating every {repeat_hours} hours)" if repeat_hours > 0 else ""),
            ephemeral=True
        )

    @app_commands.command(
        name="listschedules",
        description="List scheduled broadcasts"
    )
    @app_commands.default_permissions(administrator=True)
    async def list_schedules(self, interaction: discord.Interaction):
        """List scheduled broadcasts"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can view scheduled broadcasts",
                ephemeral=True
            )
            return

        config = self.bot.data_manager.load(self.broadcast_key)
        schedules = config.get("scheduled", {})
        
        if not schedules:
            await interaction.response.send_message(
                "No scheduled broadcasts found",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Scheduled Broadcasts",
            color=discord.Color.blue()
        )
        
        for msg_id, schedule in schedules.items():
            next_time = datetime.fromtimestamp(schedule["timestamp"])
            content_preview = schedule["content"][:100] + "..." if len(schedule["content"]) > 100 else schedule["content"]
            
            embed.add_field(
                name=f"Next: {next_time.isoformat()}",
                value=f"Content: {content_preview}\n" +
                      (f"Repeats every {schedule['repeat_interval'] // 3600} hours" if schedule.get("repeat_interval") else "One-time broadcast"),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="createtemplate",
        description="Create a broadcast template"
    )
    @app_commands.default_permissions(administrator=True)
    async def create_template(
        self,
        interaction: discord.Interaction,
        name: str,
        content: str
    ):
        """Create a broadcast template"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can create templates",
                ephemeral=True
            )
            return

        config = self.bot.data_manager.load(self.broadcast_key)
        
        if "templates" not in config:
            config["templates"] = {}
            
        # Extract variables from content (format: {variable_name})
        variables = re.findall(r'\{(\w+)\}', content)
        
        config["templates"][name] = {
            "content": content,
            "variables": variables
        }
        
        self.bot.data_manager.save(self.broadcast_key, config)
        
        await interaction.response.send_message(
            f"✅ Template '{name}' created with variables: {', '.join(variables) if variables else 'none'}",
            ephemeral=True
        )

    @app_commands.command(
        name="usetemplate",
        description="Use a broadcast template"
    )
    @app_commands.default_permissions(administrator=True)
    async def use_template(
        self,
        interaction: discord.Interaction,
        template_name: str,
        **variables
    ):
        """Use a broadcast template"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can use templates",
                ephemeral=True
            )
            return

        config = self.bot.data_manager.load(self.broadcast_key)
        
        if template_name not in config.get("templates", {}):
            await interaction.response.send_message(
                f"❌ Template '{template_name}' not found",
                ephemeral=True
            )
            return
            
        template = config["templates"][template_name]
        content = template["content"]
        
        # Replace variables in content
        try:
            content = content.format(**variables)
        except KeyError as e:
            await interaction.response.send_message(
                f"❌ Missing variable: {str(e)}",
                ephemeral=True
            )
            return
            
        await self.send_broadcast(content)
        
        await interaction.response.send_message(
            "✅ Broadcast sent using template",
            ephemeral=True
        )

    @app_commands.command(
        name="interactivebroadcast",
        description="Send an interactive broadcast with voting"
    )
    @app_commands.default_permissions(administrator=True)
    async def interactive_broadcast(
        self,
        interaction: discord.Interaction,
        content: str,
        options: str,  # comma-separated options
        duration: int = 24  # hours
    ):
        """Send an interactive broadcast with voting"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can send interactive broadcasts",
                ephemeral=True
            )
            return

        option_list = [opt.strip() for opt in options.split(",")]
        if len(option_list) < 2:
            await interaction.response.send_message(
                "❌ At least 2 options are required",
                ephemeral=True
            )
            return
            
        config = self.bot.data_manager.load(self.broadcast_key)
        
        # Create embed for the interactive broadcast
        embed = discord.Embed(
            title="Interactive Broadcast",
            description=content,
            color=discord.Color.blue()
        )
        
        # Add options with reactions
        reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][:len(option_list)]
        for option, reaction in zip(option_list, reactions):
            embed.add_field(
                name=f"Option {reaction}",
                value=option,
                inline=False
            )
            
        end_time = datetime.utcnow() + timedelta(hours=duration)
        embed.set_footer(text=f"Voting ends: {end_time.isoformat()}")
        
        # Send the broadcast
        success = False
        messages = []
        for guild_id, channel_id in config.get("channels", {}).items():
            if not config.get("enabled", {}).get(str(guild_id), True):
                continue
                
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                try:
                    msg = await channel.send(embed=embed)
                    messages.append(msg)
                    for reaction in reactions:
                        await msg.add_reaction(reaction)
                    success = True
                except discord.Forbidden:
                    pass
                    
        if success:
            # Store interactive broadcast data
            msg_id = str(messages[0].id)
            config["interactive"][msg_id] = {
                "options": option_list,
                "votes": {str(i): 0 for i in range(len(option_list))},
                "end_time": end_time.timestamp()
            }
            
            self.bot.data_manager.save(self.broadcast_key, config)
            
            await interaction.response.send_message(
                "✅ Interactive broadcast sent",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to send interactive broadcast",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reactions to interactive broadcasts"""
        if payload.user_id == self.bot.user.id:
            return
            
        config = self.bot.data_manager.load(self.broadcast_key)
        msg_id = str(payload.message_id)
        
        if msg_id in config.get("interactive", {}):
            broadcast = config["interactive"][msg_id]
            
            if datetime.utcnow().timestamp() > broadcast["end_time"]:
                return
                
            reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            if str(payload.emoji) in reactions:
                option_idx = reactions.index(str(payload.emoji))
                if option_idx < len(broadcast["options"]):
                    broadcast["votes"][str(option_idx)] += 1
                    
            self.bot.data_manager.save(self.broadcast_key, config)

    @app_commands.command(
        name="broadcastresults",
        description="Show results of an interactive broadcast"
    )
    @app_commands.default_permissions(administrator=True)
    async def broadcast_results(
        self,
        interaction: discord.Interaction,
        message_id: str
    ):
        """Show results of an interactive broadcast"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can view broadcast results",
                ephemeral=True
            )
            return

        config = self.bot.data_manager.load(self.broadcast_key)
        
        if message_id not in config.get("interactive", {}):
            await interaction.response.send_message(
                "❌ Interactive broadcast not found",
                ephemeral=True
            )
            return
            
        broadcast = config["interactive"][message_id]
        
        embed = discord.Embed(
            title="Interactive Broadcast Results",
            color=discord.Color.blue()
        )
        
        total_votes = sum(broadcast["votes"].values())
        for i, option in enumerate(broadcast["options"]):
            votes = broadcast["votes"][str(i)]
            percentage = (votes / total_votes * 100) if total_votes > 0 else 0
            embed.add_field(
                name=option,
                value=f"Votes: {votes} ({percentage:.1f}%)",
                inline=False
            )
            
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Broadcast(bot))

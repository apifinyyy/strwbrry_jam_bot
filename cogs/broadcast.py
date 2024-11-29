import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional
import asyncio
import json
from datetime import datetime, timedelta
import uuid
import re

class Broadcast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager
        self.broadcast_key = "broadcast_config"
        self.scheduled_broadcasts = {}
        self.ready = asyncio.Event()
        self.check_scheduled_broadcasts.start()

    async def cog_load(self):
        """Called when the cog is loaded."""
        await self._init_data_structure()
        self.ready.set()

    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.check_scheduled_broadcasts.cancel()

    async def _init_data_structure(self):
        """Initialize the broadcast configuration in data manager if it doesn't exist"""
        try:
            if not await self.data_manager.exists("broadcasts", "key = ?", self.broadcast_key):
                initial_config = {
                    "templates": {},           # template_name -> message_template
                    "schedules": {},           # schedule_id -> {channel_id, template, variables, interval, last_sent}
                    "channels": {},            # channel_id -> {enabled: bool, filters: []}
                    "history": {},             # message_id -> {template, variables, timestamp}
                    "settings": {
                        "max_history": 100,    # messages
                        "default_interval": 3600,  # seconds
                        "rate_limit": 5        # messages per minute
                    }
                }
                await self.data_manager.save_json("broadcasts", self.broadcast_key, initial_config)
        except Exception as e:
            print(f"Failed to initialize broadcast data structure: {str(e)}")

    @tasks.loop(minutes=1)
    async def check_scheduled_broadcasts(self):
        """Check and send scheduled broadcasts"""
        await self.ready.wait()  # Wait for initialization to complete
        
        try:
            config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
            current_time = datetime.utcnow()
            
            for msg_id, schedule in list(config.get("schedules", {}).items()):
                if current_time.timestamp() >= schedule["last_sent"] + schedule["interval"]:
                    # Send the broadcast
                    success = await self.send_broadcast(
                        schedule["template"],
                        schedule["variables"],
                        schedule["channel_id"]
                    )
                    
                    if success:
                        # Update timestamp for next broadcast
                        config["schedules"][msg_id]["last_sent"] = current_time.timestamp()
                    else:
                        # Remove one-time broadcast
                        del config["schedules"][msg_id]
                    
                    await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
        except Exception as e:
            print(f"Failed to check scheduled broadcasts: {str(e)}")

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
        broadcast_config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
        # Update config for this server
        broadcast_config["channels"][str(interaction.guild_id)] = {
            "enabled": True,
            "filters": []
        }
        
        # Save updated config
        await self.data_manager.save_json("broadcasts", self.broadcast_key, broadcast_config)
        
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
        broadcast_config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
        if str(interaction.guild_id) not in broadcast_config["channels"]:
            await interaction.response.send_message(
                "❌ Broadcasts are not set up for this server.",
                ephemeral=True
            )
            return
        
        broadcast_config["channels"][str(interaction.guild_id)]["enabled"] = False
        await self.data_manager.save_json("broadcasts", self.broadcast_key, broadcast_config)
        
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
        broadcast_config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
        if str(interaction.guild_id) not in broadcast_config["channels"]:
            await interaction.response.send_message(
                "❌ Please set up broadcasts first using `/setupbroadcast`. ",
                ephemeral=True
            )
            return
        
        broadcast_config["channels"][str(interaction.guild_id)]["enabled"] = True
        await self.data_manager.save_json("broadcasts", self.broadcast_key, broadcast_config)
        
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
        
        broadcast_config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
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
        
        for guild_id, channel_config in broadcast_config.get("channels", {}).items():
            if not channel_config["enabled"]:
                continue
                
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    raise Exception("Could not find guild")
                    
                channel = guild.get_channel(int(guild_id))
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

        await self.data_manager.save_json("broadcasts", self.broadcast_key, broadcast_config)
        
        await interaction.followup.send(
            f"✅ Broadcast sent!\nSuccess: {success_count} servers\nFailed: {fail_count} servers",
            ephemeral=True
        )

    async def send_broadcast(self, message, guilds=None):
        """Send a broadcast to all configured channels"""
        broadcast_config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        success_count = 0
        fail_count = 0
        
        embed = discord.Embed(
            title="📢 Bot Broadcast",
            description=message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for guild_id, channel_config in broadcast_config.get("channels", {}).items():
            if guilds and str(guild_id) not in guilds:
                continue
            if not channel_config["enabled"]:
                continue
                
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    raise Exception("Could not find guild")
                    
                channel = guild.get_channel(int(guild_id))
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

        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        msg_id = str(uuid.uuid4())
        
        config["schedules"][msg_id] = {
            "channel_id": interaction.channel_id,
            "template": content,
            "variables": {},
            "interval": repeat_hours * 3600 if repeat_hours > 0 else None,
            "last_sent": broadcast_time.timestamp()
        }
        
        await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
        
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

        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        schedules = config.get("schedules", {})
        
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
            next_time = datetime.fromtimestamp(schedule["last_sent"] + schedule["interval"])
            content_preview = schedule["template"][:100] + "..." if len(schedule["template"]) > 100 else schedule["template"]
            
            embed.add_field(
                name=f"Next: {next_time.isoformat()}",
                value=f"Content: {content_preview}\n" +
                      (f"Repeats every {schedule['interval'] // 3600} hours" if schedule.get("interval") else "One-time broadcast"),
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

        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
        if "templates" not in config:
            config["templates"] = {}
            
        # Extract variables from content (format: {variable_name})
        variables = re.findall(r'\{(\w+)\}', content)
        
        config["templates"][name] = {
            "content": content,
            "variables": variables
        }
        
        await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
        
        await interaction.response.send_message(
            f"✅ Template '{name}' created with variables: {', '.join(variables) if variables else 'none'}",
            ephemeral=True
        )

    @app_commands.command(
        name="template",
        description="Create or edit a message template"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def template(
        self,
        interaction: discord.Interaction,
        name: str,
        template: str
    ):
        """Create or edit a message template"""
        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
        if "templates" not in config:
            config["templates"] = {}
            
        config["templates"][name] = template
        
        await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
        
        await interaction.response.send_message(
            f"✅ Template '{name}' created or updated",
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
        variables: str,
        schedule_time: Optional[str] = None,
        repeat_interval: Optional[int] = None,
        target_guilds: Optional[str] = None
    ):
        """Use a broadcast template with variables."""
        try:
            # Load broadcast config
            config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
            
            if template_name not in config.get("templates", {}):
                await interaction.response.send_message(f"Template '{template_name}' not found!", ephemeral=True)
                return
            
            template = config["templates"][template_name]
            
            # Parse variables
            try:
                var_dict = json.loads(variables)
                if not isinstance(var_dict, dict):
                    raise ValueError("Variables must be a JSON object")
            except json.JSONDecodeError:
                await interaction.response.send_message("Invalid variables format! Must be a valid JSON object.", ephemeral=True)
                return
            
            # Replace variables in template
            content = template
            for key, value in var_dict.items():
                content = content.replace(f"{{{key}}}", str(value))
            
            # Handle scheduling if provided
            if schedule_time:
                try:
                    schedule_dt = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M")
                    if schedule_dt < datetime.utcnow():
                        await interaction.response.send_message("Schedule time must be in the future!", ephemeral=True)
                        return
                except ValueError:
                    await interaction.response.send_message("Invalid schedule time format! Use YYYY-MM-DD HH:MM", ephemeral=True)
                    return
                
                # Parse target guilds if provided
                guild_list = None
                if target_guilds:
                    try:
                        guild_list = [int(g.strip()) for g in target_guilds.split(",")]
                    except ValueError:
                        await interaction.response.send_message("Invalid guild IDs format!", ephemeral=True)
                        return
                
                # Create scheduled broadcast
                msg_id = str(uuid.uuid4())
                config["schedules"][msg_id] = {
                    "channel_id": interaction.channel_id,
                    "template": content,
                    "variables": var_dict,
                    "interval": repeat_interval,
                    "last_sent": schedule_dt.timestamp()
                }
                
                await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
                await interaction.response.send_message(
                    f"Broadcast scheduled for {schedule_time} UTC!",
                    ephemeral=True
                )
            else:
                # Send immediately
                success = await self.send_broadcast(content)
                await interaction.response.send_message(
                    "Broadcast sent successfully!" if success else "Failed to send broadcast!",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"Error using template: {str(e)}", ephemeral=True)
            raise e

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
            
        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
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
        for guild_id, channel_config in config.get("channels", {}).items():
            if not channel_config["enabled"]:
                continue
                
            channel = self.bot.get_channel(int(guild_id))
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
            
            await self.data_manager.save_json("broadcasts", self.broadcast_key, config)
            
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
            
        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
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
                    
            await self.data_manager.save_json("broadcasts", self.broadcast_key, config)

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

        config = await self.data_manager.load_json("broadcasts", self.broadcast_key)
        
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

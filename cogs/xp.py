import discord
from discord import app_commands
from discord.ext import commands
import random

class XPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.xp_key = "xp_config"
        self.logger = bot.logger.getChild('xp')
        self.xp_cooldown = {}  # Add cooldown tracking
        self.cooldown_duration = 60  # 60 seconds cooldown
        self.level_multiplier = 100  # XP needed per level
        self.min_voice_time = 1  # Minimum minutes in voice to get XP
        self.DEFAULT_CONFIG = {
            'chat_xp': {'min': 15, 'max': 25},
            'voice_xp': {'per_minute': 10},
            'enabled_channels': ['*'],  # '*' means all channels enabled
            'enabled_categories': ['*'],  # '*' means all categories enabled
            'blocked_users': [],
            'level_roles': {},
            'level_up_channel': None,
            'level_up_message': '🎉 Congratulations {user}! You reached level {level}!',
            'xp_gain_message': True,  # Whether to show XP gain messages
            'xp_gain_message_chance': 0.1  # 10% chance to show XP gain
        }

    async def get_xp_config(self, guild_id: int) -> dict:
        """Get XP configuration for a guild"""
        try:
            config = await self.bot.data_manager.load("xp_config", str(guild_id))
            if not config:
                return self.DEFAULT_CONFIG.copy()
            return config
        except Exception as e:
            self.logger.error(f"Error loading XP config: {e}")
            return self.DEFAULT_CONFIG.copy()

    async def save_xp_config(self, guild_id: int, config: dict):
        """Save XP configuration for a guild."""
        try:
            await self.bot.data_manager.save("xp_config", str(guild_id), config)
        except Exception as e:
            self.logger.error(f"Error saving XP config: {e}")

    async def calculate_level(self, xp: int) -> tuple[int, int]:
        """Calculate level and XP needed for next level."""
        level = int((xp / self.level_multiplier) ** 0.5)
        next_level_xp = (level + 1) ** 2 * self.level_multiplier
        return level, next_level_xp

    async def check_and_handle_level_up(self, member: discord.Member, old_xp: int, new_xp: int):
        """Check for level up and handle rewards."""
        try:
            old_level, _ = await self.calculate_level(old_xp)
            new_level, _ = await self.calculate_level(new_xp)

            if new_level > old_level:
                config = await self.get_xp_config(member.guild.id)
                
                # Handle level roles
                level_roles = config.get('level_roles', {})
                for level_str, role_id in level_roles.items():
                    level = int(level_str)
                    if old_level < level <= new_level:
                        try:
                            role = member.guild.get_role(int(role_id))
                            if role:
                                await member.add_roles(role)
                                self.logger.info(f"Gave level {level} role to {member}")
                        except Exception as e:
                            self.logger.error(f"Error giving level role: {e}")

                # Send level up message
                if channel_id := config.get('level_up_channel'):
                    try:
                        channel = member.guild.get_channel(int(channel_id))
                        if channel:
                            message = config['level_up_message'].format(
                                user=member.mention,
                                level=new_level,
                                old_level=old_level
                            )
                            await channel.send(message)
                    except Exception as e:
                        self.logger.error(f"Error sending level up message: {e}")

        except Exception as e:
            self.logger.error(f"Error handling level up: {e}")

    async def is_channel_enabled(self, channel: discord.TextChannel | discord.VoiceChannel) -> bool:
        """Check if XP gain is enabled for a channel."""
        try:
            config = await self.get_xp_config(channel.guild.id)
            enabled_channels = config['enabled_channels']
            enabled_categories = config['enabled_categories']
            
            # If '*' is in either list, that means all channels/categories are enabled
            if '*' in enabled_channels or '*' in enabled_categories:
                return True
                
            return (
                str(channel.id) in enabled_channels or
                (channel.category_id and str(channel.category_id) in enabled_categories)
            )
        except Exception as e:
            self.logger.error(f"Error checking channel enabled status: {e}")
            return True  # Default to enabled if there's an error

    async def get_user_xp(self, guild_id: int, user_id: int) -> dict:
        """Get user XP data with proper initialization."""
        try:
            xp_data = self.bot.data_manager.load_data(guild_id, "xp")
            if not xp_data:
                xp_data = {}
            
            if str(user_id) not in xp_data:
                xp_data[str(user_id)] = {
                    'chat_xp': 0,
                    'voice_xp': 0,
                    'total_messages': 0,
                    'voice_time': 0,
                    'last_daily': None
                }
                self.bot.data_manager.save_data(guild_id, "xp", xp_data)
            
            return xp_data[str(user_id)]
        except Exception as e:
            self.logger.error(f"Error getting user XP: {e}")
            return {
                'chat_xp': 0,
                'voice_xp': 0,
                'total_messages': 0,
                'voice_time': 0,
                'last_daily': None
            }

    async def save_user_xp(self, guild_id: int, user_id: int, xp_data: dict) -> bool:
        """Save user XP data safely."""
        try:
            all_xp_data = self.bot.data_manager.load_data(guild_id, "xp") or {}
            all_xp_data[str(user_id)] = xp_data
            self.bot.data_manager.save_data(guild_id, "xp", all_xp_data)
            return True
        except Exception as e:
            self.logger.error(f"Error saving user XP: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        try:
            config = await self.get_xp_config(message.guild.id)
            
            # Check if channel is enabled
            if not await self.is_channel_enabled(message.channel):
                return

            # Check if user is blocked
            if str(message.author.id) in config['blocked_users']:
                return

            # Check cooldown
            user_id = str(message.author.id)
            current_time = discord.utils.utcnow().timestamp()
            if user_id in self.xp_cooldown:
                if current_time - self.xp_cooldown[user_id] < self.cooldown_duration:
                    return
            self.xp_cooldown[user_id] = current_time

            # Get user data
            user_data = await self.get_user_xp(message.guild.id, message.author.id)
            old_xp = user_data['chat_xp']
            
            # Calculate XP gain
            xp_gain = random.randint(
                config['chat_xp']['min'],
                config['chat_xp']['max']
            )
            
            # Update user data
            user_data['chat_xp'] += xp_gain
            user_data['total_messages'] += 1
            
            # Save data
            if not await self.save_user_xp(message.guild.id, message.author.id, user_data):
                self.logger.error(f"Failed to save XP for user {message.author.id}")
                return

            # Show XP gain message (if enabled and random chance hits)
            if (config['xp_gain_message'] and 
                random.random() < config['xp_gain_message_chance']):
                try:
                    embed = discord.Embed(
                        title="✨ XP Gained!",
                        description=f"You earned **{xp_gain}** XP!",
                        color=discord.Color.green()
                    )
                    await message.channel.send(
                        message.author.mention,
                        embed=embed,
                        delete_after=5
                    )
                except Exception as e:
                    self.logger.error(f"Error sending XP gain message: {e}")

            # Handle level up
            await self.check_and_handle_level_up(
                message.author,
                old_xp,
                user_data['chat_xp']
            )

        except Exception as e:
            self.logger.error(f"Error in on_message XP handling: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        try:
            if after.channel:
                enabled = await self.is_channel_enabled(after.channel)
                if enabled:
                    # Don't give XP if user is alone or muted
                    if len([m for m in after.channel.members if not m.bot]) < 2 or after.self_mute:
                        return
                    self.voice_states[member.id] = discord.utils.utcnow()
            elif before.channel and member.id in self.voice_states:
                start_time = self.voice_states.pop(member.id)
                duration = (discord.utils.utcnow() - start_time).total_seconds() / 60

                # Only give XP if they were in voice for minimum time
                if duration < self.min_voice_time:
                    return

                config = await self.get_xp_config(member.guild.id)
                if str(member.id) in config['blocked_users']:
                    return

                user_id = str(member.id)
                user_data = await self.get_user_xp(member.guild.id, member.id)
                old_xp = user_data['voice_xp']
                
                # Calculate XP gain
                xp_gain = int(duration * config['voice_xp']['per_minute'])
                
                # Update user data
                user_data['voice_xp'] += xp_gain
                user_data['voice_time'] += duration
                
                # Save data
                if not await self.save_user_xp(member.guild.id, member.id, user_data):
                    self.logger.error(f"Failed to save XP for user {member.id}")
                    return

                # Handle level up
                await self.check_and_handle_level_up(
                    member,
                    old_xp,
                    user_data['voice_xp']
                )

        except Exception as e:
            self.logger.error(f"Error handling voice XP: {e}")

    @app_commands.command(name="rank")
    async def rank(self, interaction: discord.Interaction, user: discord.User = None):
        """View your or another user's XP rank"""
        try:
            target_user = user or interaction.user
            user_id = str(target_user.id)

            if user_id not in self.bot.data['users']:
                await interaction.response.send_message(
                    f"❌ {'You haven''t' if user == interaction.user else f'{target_user.name} hasn''t'} earned any XP yet!",
                    ephemeral=True
                )
                return

            user_data = self.bot.data['users'][user_id]
            chat_xp = user_data.get('chat_xp', 0)
            voice_xp = user_data.get('voice_xp', 0)
            total_xp = chat_xp + voice_xp

            chat_level, next_chat = await self.calculate_level(chat_xp)
            voice_level, next_voice = await self.calculate_level(voice_xp)
            total_level, next_total = await self.calculate_level(total_xp)

            embed = discord.Embed(
                title=f"🏆 {target_user.name}'s Rank",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)

            # Chat XP
            chat_progress = f"{chat_xp:,}/{next_chat:,}"
            embed.add_field(
                name="💬 Chat",
                value=f"Level: {chat_level}\nXP: {chat_progress}",
                inline=True
            )

            # Voice XP
            voice_progress = f"{voice_xp:,}/{next_voice:,}"
            embed.add_field(
                name="🎤 Voice",
                value=f"Level: {voice_level}\nXP: {voice_progress}",
                inline=True
            )

            # Total
            total_progress = f"{total_xp:,}/{next_total:,}"
            embed.add_field(
                name="📊 Total",
                value=f"Level: {total_level}\nXP: {total_progress}",
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in rank command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching rank data.",
                ephemeral=True
            )

    @app_commands.command(name="setlevelrole")
    @app_commands.describe(
        level="The level required for this role",
        role="The role to give at this level"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level_role(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 100],
        role: discord.Role
    ):
        """Set a role reward for reaching a specific level"""
        try:
            guild_id = str(interaction.guild_id)
            config = await self.get_xp_config(guild_id)
            
            if "level_roles" not in config:
                config["level_roles"] = {}
                
            config["level_roles"][str(level)] = str(role.id)
            await self.save_xp_config(guild_id, config)
            
            embed = discord.Embed(
                title="✅ Level Role Set",
                description=f"Members will receive {role.mention} when they reach level {level}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error setting level role: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while setting the level role.",
                ephemeral=True
            )

    @app_commands.command(name="setlevelchannel")
    @app_commands.describe(
        channel="The channel to send level up messages in",
        message="Custom level up message (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None
    ):
        """Set the channel and message for level up announcements"""
        try:
            guild_id = str(interaction.guild_id)
            config = await self.get_xp_config(guild_id)
            
            config["level_up_channel"] = str(channel.id)
            if message:
                config["level_up_message"] = message
                
            await self.save_xp_config(guild_id, config)
            
            embed = discord.Embed(
                title="✅ Level Channel Set",
                description=f"Level up messages will be sent to {channel.mention}",
                color=discord.Color.green()
            )
            if message:
                embed.add_field(
                    name="Custom Message",
                    value=message,
                    inline=False
                )
            embed.add_field(
                name="Available Variables",
                value="`{user}`: User mention\n`{level}`: New level\n`{old_level}`: Previous level",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error setting level channel: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while setting the level channel.",
                ephemeral=True
            )

    @app_commands.command(name="givexp", description="Give XP to a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: int, xp_type: str):
        if xp_type not in ['chat', 'voice']:
            await interaction.response.send_message("Invalid XP type. Use 'chat' or 'voice'.", ephemeral=True)
            return

        user_id = str(user.id)
        if user_id not in self.bot.data['users']:
            self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

        self.bot.data['users'][user_id][f'{xp_type}_xp'] += amount
        self.bot.save_data()
        await interaction.response.send_message(f"Gave {amount} {xp_type} XP to {user.name}")

    @app_commands.command(name="takexp", description="Take XP from a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def take_xp(self, interaction: discord.Interaction, user: discord.User, amount: int, xp_type: str):
        if xp_type not in ['chat', 'voice']:
            await interaction.response.send_message("Invalid XP type. Use 'chat' or 'voice'.", ephemeral=True)
            return

        user_id = str(user.id)
        if user_id not in self.bot.data['users']:
            self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

        xp_key = f'{xp_type}_xp'
        self.bot.data['users'][user_id][xp_key] = max(0, self.bot.data['users'][user_id][xp_key] - amount)
        self.bot.save_data()
        await interaction.response.send_message(f"Took {amount} {xp_type} XP from {user.name}")

    @app_commands.command(name="blockxp", description="Block a user from gaining XP")
    @app_commands.checks.has_permissions(administrator=True)
    async def block_xp(self, interaction: discord.Interaction, user: discord.User):
        """Block a user from gaining XP"""
        guild_id = str(interaction.guild_id)
        
        # Load XP config
        config = await self.get_xp_config(guild_id)
        if "blocked_users" not in config:
            config["blocked_users"] = []
        
        user_id = str(user.id)
        if user_id not in config["blocked_users"]:
            config["blocked_users"].append(user_id)
            await self.save_xp_config(guild_id, config)
            await interaction.response.send_message(f"{user.name} has been blocked from gaining XP")
        else:
            await interaction.response.send_message(f"{user.name} is already blocked from gaining XP", ephemeral=True)

    @app_commands.command(name="unblockxp", description="Unblock a user from gaining XP")
    @app_commands.checks.has_permissions(administrator=True)
    async def unblock_xp(self, interaction: discord.Interaction, user: discord.User):
        """Unblock a user from gaining XP"""
        guild_id = str(interaction.guild_id)
        
        # Load XP config
        config = await self.get_xp_config(guild_id)
        if "blocked_users" in config:
            user_id = str(user.id)
            if user_id in config["blocked_users"]:
                config["blocked_users"].remove(user_id)
                await self.save_xp_config(guild_id, config)
                await interaction.response.send_message(f"{user.name} has been unblocked from gaining XP")
                return
                
        await interaction.response.send_message(f"{user.name} is not blocked from gaining XP", ephemeral=True)

    @app_commands.command(name="leaderboard", description="View XP leaderboard")
    @app_commands.choices(board_type=[
        app_commands.Choice(name="Chat XP", value="top"),
        app_commands.Choice(name="Voice XP", value="vctop")
    ])
    async def leaderboard(self, interaction: discord.Interaction, board_type: str):
        """View the XP leaderboard for either chat or voice XP."""
        try:
            # Defer the response since we'll be making API calls
            await interaction.response.defer()

            if board_type not in ['top', 'vctop']:
                await interaction.followup.send(
                    "Invalid leaderboard type. Use 'top' for chat XP or 'vctop' for voice XP.",
                    ephemeral=True
                )
                return

            xp_type = 'voice_xp' if board_type == 'vctop' else 'chat_xp'
            
            try:
                data = self.bot.data_manager.load_data(interaction.guild_id, "xp")
            except FileNotFoundError:
                await interaction.followup.send(
                    "❌ No XP data found for this server!",
                    ephemeral=True
                )
                return

            if not data:
                await interaction.followup.send(
                    "❌ No XP data found for this server!",
                    ephemeral=True
                )
                return

            # Sort users by XP
            sorted_users = sorted(
                [(uid, udata.get(xp_type, 0)) for uid, udata in data.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]  # Top 10

            if not sorted_users:
                await interaction.followup.send(
                    "❌ No users have earned XP yet!",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"{'🎤 Voice' if board_type == 'vctop' else '💬 Chat'} XP Leaderboard",
                color=discord.Color.blue()
            )

            for i, (user_id, xp) in enumerate(sorted_users, 1):
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👑"
                    embed.add_field(
                        name=f"{medal} #{i} - {user.name}",
                        value=f"**{xp:,}** XP",
                        inline=False
                    )
                except discord.NotFound:
                    continue
                except Exception as e:
                    print(f"Error fetching user {user_id}: {e}")
                    continue

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in leaderboard command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the leaderboard. Please try again later.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(XPSystem(bot))

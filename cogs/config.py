import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal, List
import aiohttp
import time
import logging

class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "config"
        self._config_cache = {}  # guild_id -> (config, timestamp)
        self.cache_ttl = 300  # 5 minutes
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        """Initialize the cog"""
        self.valid_settings = {
            'economy': {
                'starting_balance': ('Starting balance for new users', '100', int, lambda x: 0 <= x <= 1000000),
                'max_balance': ('Maximum balance allowed', '1000000', int, lambda x: x > 0),
                'daily_amount': ('Daily reward amount', '100', int, lambda x: x > 0),
                'weekly_amount': ('Weekly reward amount', '1000', int, lambda x: x > 0),
                'min_bet': ('Minimum bet amount', '10', int, lambda x: x > 0),
                'max_bet': ('Maximum bet amount', '1000', int, lambda x: x > 0)
            },
            'rewards': {
                'message_reward': ('Coins per message', '1', int, lambda x: 0 <= x <= 100),
                'voice_reward': ('Coins per minute in voice', '2', int, lambda x: 0 <= x <= 100),
                'message_cooldown': ('Cooldown between message rewards in seconds', '60', int, lambda x: x >= 0),
                'voice_cooldown': ('Cooldown between voice rewards in seconds', '300', int, lambda x: x >= 0)
            },
            'welcome': {
                'channel': ('Welcome channel ID', 'None', str, None),
                'message': ('Welcome message (use {user} for mention)', 'Welcome {user} to the server!', str, None),
                'enabled': ('Enable/disable welcome messages', 'true', bool, None),
                'color': ('Embed color (hex)', '#7289DA', str, lambda x: len(x) == 7 and x.startswith('#'))
            },
            'moderation': {
                'mod_role': ('Moderator role ID', 'None', str, None),
                'admin_role': ('Administrator role ID', 'None', str, None),
                'mute_role': ('Mute role ID', 'None', str, None),
                'log_channel': ('Moderation log channel ID', 'None', str, None)
            },
            'levels': {
                'enabled': ('Enable/disable leveling system', 'true', bool, None),
                'xp_per_message': ('XP gained per message', '15', int, lambda x: 1 <= x <= 100),
                'xp_cooldown': ('Cooldown between XP gains in seconds', '60', int, lambda x: x >= 0),
                'level_up_channel': ('Channel for level up announcements (None for same channel)', 'None', str, None)
            }
        }

    def _get_config(self, guild_id: int) -> dict:
        """Get configuration for a specific guild with caching."""
        current_time = time.time()
        
        # Check cache first
        if guild_id in self._config_cache:
            config, timestamp = self._config_cache[guild_id]
            if current_time - timestamp < self.cache_ttl:
                return config.copy()  # Return a copy to prevent mutations
        
        try:
            # Load from storage
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
            
            # Update cache
            self._config_cache[guild_id] = (data, current_time)
            
            return data.copy()
        except FileNotFoundError:
            # Create default config
            data = self._create_default_config()
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
            self._config_cache[guild_id] = (data, current_time)
            return data.copy()

    def _create_default_config(self) -> dict:
        """Create default configuration"""
        config = {}
        for category, settings in self.valid_settings.items():
            config[category] = {
                setting: info[1] for setting, info in settings.items()
            }
        return config

    async def _validate_setting(self, category: str, setting: str, value: str) -> tuple[bool, str, any]:
        """Validate a setting value with detailed error messages"""
        if category not in self.valid_settings:
            return False, f"❌ Invalid category: `{category}`\nValid categories: {', '.join(f'`{c}`' for c in self.valid_settings.keys())}", None
            
        if setting not in self.valid_settings[category]:
            return False, f"❌ Invalid setting: `{setting}`\nValid settings for {category}: {', '.join(f'`{s}`' for s in self.valid_settings[category].keys())}", None
            
        setting_info = self.valid_settings[category][setting]
        value_type = setting_info[2]
        validator = setting_info[3]
        description = setting_info[0]
        
        try:
            # Convert value to correct type
            if value_type == bool:
                if value.lower() not in ['true', 'false', 'yes', 'no', 'on', 'off', '1', '0']:
                    return False, f"❌ Invalid boolean value: `{value}`\nPlease use: true/false, yes/no, on/off, or 1/0", None
                typed_value = value.lower() in ['true', 'yes', 'on', '1']
            else:
                typed_value = value_type(value)
            
            # Validate if validator exists
            if validator and not validator(typed_value):
                if value_type == int:
                    # Get validator bounds
                    test_val = -1
                    lower_bound = None
                    while True:
                        if validator(test_val):
                            lower_bound = test_val
                            break
                        if test_val < -1000000:  # Prevent infinite loop
                            break
                        test_val -= 1
                    
                    test_val = 1
                    upper_bound = None
                    while True:
                        if validator(test_val):
                            upper_bound = test_val
                            break
                        if test_val > 1000000:  # Prevent infinite loop
                            break
                        test_val += 1
                    
                    bounds_msg = ""
                    if lower_bound is not None and upper_bound is not None:
                        bounds_msg = f" (must be between {lower_bound} and {upper_bound})"
                    elif lower_bound is not None:
                        bounds_msg = f" (must be at least {lower_bound})"
                    elif upper_bound is not None:
                        bounds_msg = f" (must be at most {upper_bound})"
                    
                    return False, f"❌ Invalid value: `{value}`{bounds_msg}", None
                else:
                    return False, f"❌ Invalid value: `{value}` (doesn't meet requirements for {description})", None
                
            return True, "", typed_value
            
        except ValueError:
            if value_type == int:
                return False, f"❌ Invalid number format: `{value}`\nPlease enter a whole number", None
            return False, f"❌ Invalid value type. Expected {value_type.__name__}", None

    async def setting_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for settings based on selected category."""
        try:
            # Get the category from the current interaction
            category = interaction.namespace.category
            if not category:
                return []

            # Get valid settings for the category
            settings = self.valid_settings.get(category, {})
            
            # Filter and sort choices based on current input
            choices = [
                app_commands.Choice(
                    name=f"{setting} - {desc[0]}", 
                    value=setting
                )
                for setting, desc in settings.items()
                if current.lower() in setting.lower() or current.lower() in desc[0].lower()
            ]
            return choices[:25]  # Discord has a limit of 25 choices
        except Exception:
            return []

    @app_commands.command(name="viewconfig", description="View current configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction, category: Optional[str] = None):
        """View the current configuration for this server."""
        try:
            config = self._get_config(interaction.guild_id)
            
            if not config:
                await interaction.response.send_message("❌ No configuration set for this server.", ephemeral=True)
                return

            if category and category not in config:
                categories = ", ".join(f"`{c}`" for c in config.keys())
                await interaction.response.send_message(
                    f"❌ Invalid category: `{category}`\nValid categories: {categories}",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🔧 Server Configuration",
                description="Use the specific configuration commands to modify these settings:\n• `/automod` - For moderation settings\n• `/gameconfig` - For game settings\n• `/botappearance` - For bot appearance\n• `/viewconfig` - To view current settings",
                color=discord.Color.blue()
            )

            categories_to_show = [category] if category else config.keys()
            
            for cat in categories_to_show:
                settings = config[cat]
                if isinstance(settings, dict):
                    # Get descriptions for each setting
                    setting_lines = []
                    for k, v in settings.items():
                        desc = self.valid_settings[cat][k][0] if cat in self.valid_settings and k in self.valid_settings[cat] else "No description"
                        setting_lines.append(f"• `{k}`: {v}\n  ↳ {desc}")
                    value = "\n".join(setting_lines)
                else:
                    value = str(settings)
                
                embed.add_field(
                    name=f"📁 {cat.title()}",
                    value=value or "No settings configured",
                    inline=False
                )

            embed.set_footer(text="💡 Tip: Use /viewconfig <category> to view specific settings")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in view_config: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching the configuration. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(name="config", description="[DEPRECATED] Configure bot settings - Please use the newer specific commands")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        category="The category to configure",
        setting="The setting to change",
        value="The new value to set"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="💰 Economy Settings", value="economy"),
        app_commands.Choice(name="🎁 Rewards Settings", value="rewards"),
        app_commands.Choice(name="👋 Welcome Settings", value="welcome"),
        app_commands.Choice(name="🛡️ Moderation Settings", value="moderation"),
        app_commands.Choice(name="⭐ Levels Settings", value="levels")
    ])
    @app_commands.autocomplete(setting=setting_autocomplete)
    async def config(
        self,
        interaction: discord.Interaction,
        category: str,
        setting: str,
        value: str
    ):
        """[DEPRECATED] Configure bot settings for this server. Please use the newer specific commands:
        - /automod - For moderation settings
        - /gameconfig - For game settings
        - /botappearance - For bot appearance
        - /viewconfig - To view current settings"""
        
        # Send deprecation notice
        embed = discord.Embed(
            title="⚠️ Command Deprecated",
            description=(
                "The `/config` command is deprecated and will be removed in a future update.\n\n"
                "Please use these newer commands instead:\n"
                "• `/automod` - For moderation settings\n"
                "• `/gameconfig` - For game settings\n"
                "• `/botappearance` - For bot appearance\n"
                "• `/viewconfig` - To view current settings"
            ),
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Still process the command for backward compatibility
        try:
            # Check bot permissions
            if not interaction.guild.me.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ I need Administrator permissions to manage server settings",
                    ephemeral=True
                )
                return

            # Validate setting
            valid, error_msg, typed_value = await self._validate_setting(category, setting, value)
            if not valid:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Get and update config
            config = self._get_config(interaction.guild_id)
            if category not in config:
                config[category] = {}
            
            old_value = config[category].get(setting, "Not set")
            config[category][setting] = typed_value
            
            # Save config
            try:
                self.bot.data_manager.save_data(interaction.guild_id, self.data_type, config)
                self._config_cache[interaction.guild_id] = (config, time.time())
            except Exception as e:
                self.logger.error(f"Error saving config: {e}")
                await interaction.response.send_message(
                    "❌ Failed to save configuration. Please try again later.",
                    ephemeral=True
                )
                return
            
            # Get setting description and emoji
            setting_desc = self.valid_settings[category][setting][0]
            category_emoji = next((c.name.split()[0] for c in self.config.choices if c.value == category), "📝")
            
            embed = discord.Embed(
                title=f"{category_emoji} Configuration Updated",
                description=f"Successfully updated {category} configuration",
                color=discord.Color.green()
            )
            
            # Category field
            embed.add_field(
                name="Category",
                value=f"{category_emoji} {category.title()}",
                inline=True
            )
            
            # Setting field with description
            embed.add_field(
                name="Setting",
                value=f"`{setting}`\n↳ {setting_desc}",
                inline=True
            )
            
            # Value change field
            if isinstance(typed_value, bool):
                new_value = "✅ Enabled" if typed_value else "❌ Disabled"
                old_value_display = "✅ Enabled" if str(old_value).lower() in ['true', 'yes', 'on', '1'] else "❌ Disabled"
            else:
                new_value = str(typed_value)
                old_value_display = str(old_value)
            
            embed.add_field(
                name="Value Changed",
                value=f"From: `{old_value_display}`\nTo: `{new_value}`",
                inline=False
            )
            
            # Add relevant tips based on the setting
            tips = []
            if category == "welcome" and setting == "channel":
                tips.append("💡 Don't forget to enable welcome messages with `/config welcome enabled true`")
            elif category == "moderation" and setting == "log_channel":
                tips.append("💡 Make sure the bot has permission to send messages in the log channel")
            elif category == "levels" and setting == "enabled":
                tips.append("💡 Configure XP settings with `/config levels xp_per_message` and `/config levels xp_cooldown`")
            
            if tips:
                embed.add_field(
                    name="💡 Tips",
                    value="\n".join(tips),
                    inline=False
                )
            
            embed.set_footer(text="Use /viewconfig to see all current settings")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in config command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the configuration. Please try again later.",
                ephemeral=True
            )

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook:
        """Get existing webhook or create a new one."""
        # Look for existing webhook
        webhooks = await channel.webhooks()
        webhook = discord.utils.get(webhooks, name="CustomBotHook", user=self.bot.user)
        
        # Create new webhook if none exists
        if webhook is None:
            webhook = await channel.create_webhook(name="CustomBotHook")
        
        return webhook

    @app_commands.command(name="botappearance", description="Customize the bot's name and avatar for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_bot_appearance(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ):
        """Set the bot's name and/or avatar for this server."""
        try:
            # Defer response since we'll be making API calls
            await interaction.response.defer(ephemeral=True)
            
            # Get current config
            config = self._get_config(interaction.guild_id)
            if "appearance" not in config:
                config["appearance"] = {}

            # Validate name
            if name:
                if len(name) < 2 or len(name) > 32:
                    await interaction.followup.send(
                        "❌ Bot name must be between 2 and 32 characters long!",
                        ephemeral=True
                    )
                    return
                config["appearance"]["name"] = name

            # Validate avatar URL
            if avatar_url:
                # Check if URL is valid
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(avatar_url) as resp:
                            if resp.status != 200:
                                await interaction.followup.send(
                                    "❌ Invalid avatar URL! Please provide a direct image URL.",
                                    ephemeral=True
                                )
                                return
                            if not resp.headers.get("content-type", "").startswith("image/"):
                                await interaction.followup.send(
                                    "❌ The URL must point to an image file!",
                                    ephemeral=True
                                )
                                return
                except Exception:
                    await interaction.followup.send(
                        "❌ Failed to access the avatar URL. Please make sure it's a valid, direct image URL.",
                        ephemeral=True
                    )
                    return

                config["appearance"]["avatar_url"] = avatar_url

            # Save config
            self.bot.data_manager.save_data(interaction.guild_id, self.data_type, config)

            # Create response embed
            embed = discord.Embed(
                title="🎨 Bot Appearance Updated",
                color=discord.Color.green()
            )
            
            if name:
                embed.add_field(
                    name="New Name",
                    value=name,
                    inline=True
                )
            
            if avatar_url:
                embed.add_field(
                    name="New Avatar",
                    value="[Click to view](" + avatar_url + ")",
                    inline=True
                )
                embed.set_thumbnail(url=avatar_url)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage webhooks in this server!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="resetbotappearance", description="Reset the bot's appearance to default for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_bot_appearance(self, interaction: discord.Interaction):
        """Reset the bot's appearance to default for this server."""
        try:
            # Get current config
            config = self._get_config(interaction.guild_id)
            
            # Remove appearance settings
            if "appearance" in config:
                del config["appearance"]
                self.bot.data_manager.save_data(interaction.guild_id, self.data_type, config)
                
            await interaction.response.send_message(
                "✅ Bot appearance has been reset to default!",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="invite", description="Get the bot's invite link and information")
    async def invite_link(self, interaction: discord.Interaction):
        """Generate an invite link for the bot with detailed information."""
        permissions = discord.Permissions(
            # Moderation permissions
            kick_members=True,
            ban_members=True,
            moderate_members=True,
            manage_messages=True,
            manage_threads=True,
            
            # Channel permissions
            manage_channels=True,
            manage_roles=True,
            manage_webhooks=True,
            view_channel=True,
            
            # Message permissions
            send_messages=True,
            send_messages_in_threads=True,
            create_public_threads=True,
            embed_links=True,
            attach_files=True,
            add_reactions=True,
            use_external_emojis=True,
            use_external_stickers=True,
            read_message_history=True,
            mention_everyone=True,
            
            # Voice permissions
            connect=True,
            speak=True,
            mute_members=True,
            deafen_members=True,
            move_members=True,
            use_voice_activation=True,
        )
        
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )
        
        embed = discord.Embed(
            title="🍓 Invite Strwbrry Jam Bot",
            description=(
                f"Click [here]({invite_url}) to add me to your server!\n\n"
                "**Why choose Strwbrry Jam Bot?**\n"
                "• 🛡️ Advanced moderation & auto-moderation\n"
                "• 💰 Fun economy system with games\n"
                "• ⭐ XP system with role rewards\n"
                "• 🎮 Interactive mini-games\n"
                "• 🎫 Support ticket system\n"
                "• 👋 Customizable welcome messages\n"
                "• 📊 Detailed server statistics\n"
            ),
            color=discord.Color.from_rgb(255, 182, 193)  # Strawberry pink color
        )
        
        # Add feature sections
        embed.add_field(
            name="🛡️ Moderation Features",
            value=(
                "• Warning system with infractions tracking\n"
                "• Temporary & permanent bans\n"
                "• Advanced auto-moderation\n"
                "• Detailed logging system"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎮 Fun & Games",
            value=(
                "• Economy system with shop\n"
                "• Interactive mini-games\n"
                "• Trivia challenges\n"
                "• Giveaway system"
            ),
            inline=True
        )
        
        # Add bot stats if available
        if hasattr(self.bot, 'guild_count'):
            embed.add_field(
                name="📊 Bot Stats",
                value=(
                    f"• Servers: {len(self.bot.guilds):,}\n"
                    f"• Users: {sum(g.member_count for g in self.bot.guilds):,}\n"
                    f"• Commands: {len(self.bot.tree.get_commands()):,}\n"
                    "• Uptime: 99.9%"
                ),
                inline=False
            )
        
        # Add support info
        embed.add_field(
            name="🔗 Quick Links",
            value=(
                "[Support Server](https://discord.gg/your-support-server)\n"
                "[Documentation](https://docs.your-bot-website.com)\n"
                "[Top.gg Page](https://top.gg/your-bot)\n"
                "[GitHub](https://github.com/your-username/strwbrry_jam_bot)"
            ),
            inline=False
        )
        
        # Set bot avatar as thumbnail if available
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add footer with tip
        embed.set_footer(
            text="💡 Tip: Make sure to grant all permissions for full functionality!"
        )
        
        # Create button view
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="🔗 Add to Server",
                url=invite_url
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="📚 Documentation",
                url="https://docs.your-bot-website.com"
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="💬 Support Server",
                url="https://discord.gg/your-support-server"
            )
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

    async def _use_custom_appearance(self, message: discord.Message) -> bool:
        """Check if we should use custom appearance for this message."""
        if not message.guild:
            return False
            
        try:
            config = self._get_config(message.guild.id)
            appearance = config.get("appearance", {})
            
            if not appearance:
                return False
                
            webhook = await self._get_or_create_webhook(message.channel)
            
            # Send message with custom appearance
            await webhook.send(
                content=message.content,
                username=appearance.get("name", self.bot.user.name),
                avatar_url=appearance.get("avatar_url", self.bot.user.avatar.url),
                embeds=message.embeds
            )
            
            # Delete original message
            await message.delete()
            return True
            
        except Exception as e:
            print(f"Error using custom appearance: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages to apply custom appearance."""
        if message.author != self.bot.user:
            return
            
        await self._use_custom_appearance(message)

async def setup(bot):
    await bot.add_cog(Config(bot))

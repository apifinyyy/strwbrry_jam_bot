import discord
from discord import app_commands
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('welcome')
        self.max_message_length = 2000
        self.available_variables = {
            "{user}": "Mentions the user",
            "{server}": "Server name",
            "{member_count}": "Current member count",
            "{user_name}": "User's name without mention",
            "{join_position}": "Member's join position"
        }

    async def cog_load(self):
        """Called when the cog is loaded."""
        try:
            await self._init_welcome_config()
        except Exception as e:
            self.logger.error(f"Error initializing welcome config: {e}")
            raise

    async def _init_welcome_config(self):
        """Initialize welcome configuration."""
        default_config = {
            'welcome_channel': None,
            'welcome_message': 'Welcome {user} to {server}!',
            'goodbye_channel': None,
            'goodbye_message': 'Goodbye {user}, we\'ll miss you!',
            'welcome_embed': False,
            'goodbye_embed': False,
            'welcome_color': 0x2ecc71,  # Green
            'goodbye_color': 0xe74c3c,  # Red
        }

        try:
            if not await self.bot.data_manager.exists('welcome_config'):
                await self.bot.data_manager.save('welcome_config', 'default', default_config)
            self.logger.info("Welcome config initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize welcome config: {e}")
            raise

    async def get_welcome_config(self, guild_id: int) -> dict:
        """Get welcome configuration for a guild."""
        try:
            config = await self.bot.data_manager.load('welcome_config', str(guild_id))
            if not config:
                config = await self.bot.data_manager.load('welcome_config', 'default')
            return config or {
                'welcome_channel': None,
                'welcome_message': 'Welcome {user} to {server}!',
                'goodbye_channel': None,
                'goodbye_message': 'Goodbye {user}, we\'ll miss you!',
                'welcome_embed': False,
                'goodbye_embed': False,
                'welcome_color': 0x2ecc71,  # Green
                'goodbye_color': 0xe74c3c,  # Red,
            }
        except Exception as e:
            self.logger.error(f"Failed to load welcome config for guild {guild_id}: {e}")
            raise

    async def save_welcome_config(self, guild_id: int, welcome_config: dict):
        """Save welcome configuration for a guild."""
        try:
            await self.bot.data_manager.save('welcome_config', str(guild_id), welcome_config)
        except Exception as e:
            self.logger.error(f"Failed to save welcome config: {e}")
            raise

    async def format_message(self, message: str, member: discord.Member, is_join: bool = True) -> str:
        """Format welcome/goodbye message with variables."""
        try:
            join_position = sum(1 for m in member.guild.members if not m.bot) if is_join else None
            return message.format(
                user=member.mention,
                server=member.guild.name,
                member_count=len([m for m in member.guild.members if not m.bot]),
                user_name=member.name,
                join_position=join_position
            )
        except Exception as e:
            self.logger.error(f"Error formatting message: {e}")
            return f"Welcome {member.mention} to {member.guild.name}!"

    async def send_welcome_message(self, member: discord.Member, config: dict):
        """Send welcome message with enhanced formatting."""
        if not config['welcome_channel']:
            return

        try:
            channel = member.guild.get_channel(int(config['welcome_channel']))
            if not channel:
                return

            message = await self.format_message(config['welcome_message'], member, True)

            if config.get('welcome_embed', False):
                embed = discord.Embed(
                    description=message,
                    color=config.get('welcome_color', 0x2ecc71)
                )
                embed.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.display_avatar.url)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Member #{sum(1 for m in member.guild.members if not m.bot)}")
                await channel.send(embed=embed)
            else:
                await channel.send(message)

        except Exception as e:
            self.logger.error(f"Error sending welcome message in guild {member.guild.id}: {e}")

    async def send_goodbye_message(self, member: discord.Member, config: dict):
        """Send goodbye message with enhanced formatting."""
        if not config['goodbye_channel']:
            return

        try:
            channel = member.guild.get_channel(int(config['goodbye_channel']))
            if not channel:
                return

            message = await self.format_message(config['goodbye_message'], member, False)

            if config.get('goodbye_embed', False):
                embed = discord.Embed(
                    description=message,
                    color=config.get('goodbye_color', 0xe74c3c)
                )
                embed.set_author(name=f"Goodbye from {member.guild.name}!", icon_url=member.display_avatar.url)
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
            else:
                await channel.send(message)

        except Exception as e:
            self.logger.error(f"Error sending goodbye message in guild {member.guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle member join events."""
        if member.bot:
            return
        config = await self.get_welcome_config(member.guild.id)
        await self.send_welcome_message(member, config)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member leave events."""
        if member.bot:
            return
        config = await self.get_welcome_config(member.guild.id)
        await self.send_goodbye_message(member, config)

    @app_commands.command(name="setwelcome")
    @app_commands.describe(
        channel="The channel to send welcome messages in",
        message="The welcome message (optional)",
        use_embed="Whether to use an embed for the message (optional)",
        color="Hex color for the embed (optional, e.g., #2ecc71)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None,
        use_embed: bool = None,
        color: str = None
    ):
        """Set welcome message and channel."""
        try:
            if message and len(message) > self.max_message_length:
                await interaction.response.send_message(
                    f"❌ Message too long! Maximum length is {self.max_message_length} characters.",
                    ephemeral=True
                )
                return

            config = await self.get_welcome_config(interaction.guild.id)
            config['welcome_channel'] = str(channel.id)
            if message:
                config['welcome_message'] = message
            if use_embed is not None:
                config['welcome_embed'] = use_embed
            if color:
                try:
                    color_int = int(color.strip('#'), 16)
                    config['welcome_color'] = color_int
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Invalid color format! Please use hex format (e.g., #2ecc71)",
                        ephemeral=True
                    )
                    return

            await self.save_welcome_config(interaction.guild.id, config)

            # Create preview embed
            embed = discord.Embed(
                title="Welcome Configuration Updated",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Channel",
                value=channel.mention,
                inline=False
            )
            embed.add_field(
                name="Message",
                value=message or config['welcome_message'],
                inline=False
            )
            embed.add_field(
                name="Using Embed",
                value="Yes" if config.get('welcome_embed', False) else "No",
                inline=True
            )
            if config.get('welcome_embed', False):
                embed.add_field(
                    name="Embed Color",
                    value=f"#{config.get('welcome_color', 0x2ecc71):06x}",
                    inline=True
                )

            # Add available variables field
            variables_text = "\n".join(f"`{k}`: {v}" for k, v in self.available_variables.items())
            embed.add_field(
                name="Available Variables",
                value=variables_text,
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in set_welcome: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the welcome configuration.",
                ephemeral=True
            )

    @app_commands.command(name="setgoodbye")
    @app_commands.describe(
        channel="The channel to send goodbye messages in",
        message="The goodbye message (optional)",
        use_embed="Whether to use an embed for the message (optional)",
        color="Hex color for the embed (optional, e.g., #e74c3c)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_goodbye(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None,
        use_embed: bool = None,
        color: str = None
    ):
        """Set goodbye message and channel."""
        try:
            if message and len(message) > self.max_message_length:
                await interaction.response.send_message(
                    f"❌ Message too long! Maximum length is {self.max_message_length} characters.",
                    ephemeral=True
                )
                return

            config = await self.get_welcome_config(interaction.guild.id)
            config['goodbye_channel'] = str(channel.id)
            if message:
                config['goodbye_message'] = message
            if use_embed is not None:
                config['goodbye_embed'] = use_embed
            if color:
                try:
                    color_int = int(color.strip('#'), 16)
                    config['goodbye_color'] = color_int
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Invalid color format! Please use hex format (e.g., #e74c3c)",
                        ephemeral=True
                    )
                    return

            await self.save_welcome_config(interaction.guild.id, config)

            # Create preview embed
            embed = discord.Embed(
                title="Goodbye Configuration Updated",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Channel",
                value=channel.mention,
                inline=False
            )
            embed.add_field(
                name="Message",
                value=message or config['goodbye_message'],
                inline=False
            )
            embed.add_field(
                name="Using Embed",
                value="Yes" if config.get('goodbye_embed', False) else "No",
                inline=True
            )
            if config.get('goodbye_embed', False):
                embed.add_field(
                    name="Embed Color",
                    value=f"#{config.get('goodbye_color', 0xe74c3c):06x}",
                    inline=True
                )

            # Add available variables field
            variables_text = "\n".join(f"`{k}`: {v}" for k, v in self.available_variables.items())
            embed.add_field(
                name="Available Variables",
                value=variables_text,
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in set_goodbye: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the goodbye configuration.",
                ephemeral=True
            )

    @app_commands.command(name="testwelcome", description="Test the welcome message")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_welcome(self, interaction: discord.Interaction):
        """Test the welcome message."""
        config = await self.get_welcome_config(interaction.guild.id)
        if not config['welcome_channel']:
            await interaction.response.send_message(
                "❌ Welcome channel not set! Use `/setwelcome` first.",
                ephemeral=True
            )
            return

        try:
            channel = interaction.guild.get_channel(int(config['welcome_channel']))
            if channel:
                message = await self.format_message(config['welcome_message'], interaction.user, True)
                if config.get('welcome_embed', False):
                    embed = discord.Embed(
                        description=message,
                        color=config.get('welcome_color', 0x2ecc71)
                    )
                    embed.set_author(name=f"Welcome to {interaction.guild.name}!", icon_url=interaction.user.display_avatar.url)
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    embed.set_footer(text=f"Member #{sum(1 for m in interaction.guild.members if not m.bot)}")
                    await channel.send(embed=embed)
                else:
                    await channel.send(message)
                await interaction.response.send_message(
                    "✅ Test welcome message sent!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Welcome channel not found! Please set it again.",
                    ephemeral=True
                )
        except (ValueError, TypeError):
            await interaction.response.send_message(
                "❌ Invalid channel configuration! Please set the channel again.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages in the welcome channel!",
                ephemeral=True
            )

    @app_commands.command(name="testgoodbye", description="Test the goodbye message")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_goodbye(self, interaction: discord.Interaction):
        """Test the goodbye message."""
        config = await self.get_welcome_config(interaction.guild.id)
        if not config['goodbye_channel']:
            await interaction.response.send_message(
                "❌ Goodbye channel not set! Use `/setgoodbye` first.",
                ephemeral=True
            )
            return

        try:
            channel = interaction.guild.get_channel(int(config['goodbye_channel']))
            if channel:
                message = await self.format_message(config['goodbye_message'], interaction.user, False)
                if config.get('goodbye_embed', False):
                    embed = discord.Embed(
                        description=message,
                        color=config.get('goodbye_color', 0xe74c3c)
                    )
                    embed.set_author(name=f"Goodbye from {interaction.guild.name}!", icon_url=interaction.user.display_avatar.url)
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    await channel.send(embed=embed)
                else:
                    await channel.send(message)
                await interaction.response.send_message(
                    "✅ Test goodbye message sent!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Goodbye channel not found! Please set it again.",
                    ephemeral=True
                )
        except (ValueError, TypeError):
            await interaction.response.send_message(
                "❌ Invalid channel configuration! Please set the channel again.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages in the goodbye channel!",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Welcome(bot))

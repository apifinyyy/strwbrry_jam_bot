import discord
from discord import app_commands
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('welcome')

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
            'goodbye_message': 'Goodbye {user}, we\'ll miss you!'
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
                'goodbye_message': 'Goodbye {user}, we\'ll miss you!'
            }
        except Exception as e:
            self.logger.error(f"Failed to load welcome config: {e}")
            raise

    async def save_welcome_config(self, guild_id: int, welcome_config: dict):
        """Save welcome configuration for a guild."""
        try:
            await self.bot.data_manager.save('welcome_config', str(guild_id), welcome_config)
        except Exception as e:
            self.logger.error(f"Failed to save welcome config: {e}")
            raise

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle member join events."""
        config = await self.get_welcome_config(member.guild.id)
        if not config['welcome_channel']:
            return

        try:
            channel = member.guild.get_channel(int(config['welcome_channel']))
            if channel:
                message = config['welcome_message'].format(
                    user=member.mention,
                    server=member.guild.name
                )
                await channel.send(message)
        except (ValueError, TypeError, discord.Forbidden):
            self.logger.error(f"Error sending welcome message: {member.guild.id}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member leave events."""
        config = await self.get_welcome_config(member.guild.id)
        if not config['goodbye_channel']:
            return

        try:
            channel = member.guild.get_channel(int(config['goodbye_channel']))
            if channel:
                message = config['goodbye_message'].format(
                    user=member.mention,
                    server=member.guild.name
                )
                await channel.send(message)
        except (ValueError, TypeError, discord.Forbidden):
            self.logger.error(f"Error sending goodbye message: {member.guild.id}")

    @app_commands.command(name="setwelcome", description="Set the welcome message and channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None
    ):
        """Set welcome message and channel."""
        config = await self.get_welcome_config(interaction.guild.id)
        config['welcome_channel'] = str(channel.id)
        if message:
            config['welcome_message'] = message
        
        await self.save_welcome_config(interaction.guild.id, config)

        await interaction.response.send_message(
            f"Welcome messages will be sent to {channel.mention}\n"
            f"Message: {message or config['welcome_message']}"
        )

    @app_commands.command(name="setgoodbye", description="Set the goodbye message and channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_goodbye(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None
    ):
        """Set goodbye message and channel."""
        config = await self.get_welcome_config(interaction.guild.id)
        config['goodbye_channel'] = str(channel.id)
        if message:
            config['goodbye_message'] = message
        
        await self.save_welcome_config(interaction.guild.id, config)

        await interaction.response.send_message(
            f"Goodbye messages will be sent to {channel.mention}\n"
            f"Message: {message or config['goodbye_message']}"
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
                message = config['welcome_message'].format(
                    user=interaction.user.mention,
                    server=interaction.guild.name
                )
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
                message = config['goodbye_message'].format(
                    user=interaction.user.mention,
                    server=interaction.guild.name
                )
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

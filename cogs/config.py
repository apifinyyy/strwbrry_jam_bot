import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import aiohttp

class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "config"

    def _get_config(self, guild_id: int) -> dict:
        """Get configuration for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {}
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
        return data

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook:
        """Get existing webhook or create a new one."""
        # Look for existing webhook
        webhooks = await channel.webhooks()
        webhook = discord.utils.get(webhooks, name="CustomBotHook", user=self.bot.user)
        
        # Create new webhook if none exists
        if webhook is None:
            webhook = await channel.create_webhook(name="CustomBotHook")
        
        return webhook

    @app_commands.command(name="viewconfig", description="View current configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction):
        """View the current configuration for this server."""
        try:
            config = self._get_config(interaction.guild_id)
            
            if not config:
                await interaction.response.send_message("❌ No configuration set for this server.", ephemeral=True)
                return

            embed = discord.Embed(
                title="🔧 Server Configuration",
                color=discord.Color.blue()
            )

            for category, settings in config.items():
                if isinstance(settings, dict):
                    value = "\n".join(f"`{k}`: {v}" for k, v in settings.items())
                else:
                    value = str(settings)
                embed.add_field(
                    name=f"📁 {category.title()}",
                    value=value or "No settings configured",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="config", description="Configure bot settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def config(
        self,
        interaction: discord.Interaction,
        category: Literal[
            'games',
            'economy',
            'xp',
            'rewards',
            'roles',
            'welcome'
        ],
        setting: str,
        value: str
    ):
        """Configure bot settings for this server."""
        try:
            # Get current config
            config = self._get_config(interaction.guild_id)
            
            # Initialize category if it doesn't exist
            if category not in config:
                config[category] = {}
            
            # Update setting
            config[category][setting] = value
            
            # Save config
            self.bot.data_manager.save_data(interaction.guild_id, self.data_type, config)
            
            await interaction.response.send_message(
                f"✅ Updated {category}.{setting} to: {value}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

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

    @app_commands.command(name="invite", description="Get the bot's invite link")
    async def invite_link(self, interaction: discord.Interaction):
        """Generate an invite link for the bot."""
        permissions = discord.Permissions(
            manage_roles=True,
            manage_channels=True,
            manage_webhooks=True,
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            add_reactions=True,
            use_external_emojis=True,
            view_channel=True,
            moderate_members=True
        )
        
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )
        
        embed = discord.Embed(
            title="🔗 Invite Strwbrry Jam Bot",
            description=f"Click [here]({invite_url}) to invite me to your server!\n\n"
                       f"**Required Permissions:**\n"
                       f"• Manage Roles\n"
                       f"• Manage Channels\n"
                       f"• Manage Webhooks\n"
                       f"• Read/Send Messages\n"
                       f"• Manage Messages\n"
                       f"• Embed Links\n"
                       f"• Attach Files\n"
                       f"• Read Message History\n"
                       f"• Add Reactions\n"
                       f"• Use External Emojis\n"
                       f"• Moderate Members",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Make sure to grant all permissions for full functionality!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

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

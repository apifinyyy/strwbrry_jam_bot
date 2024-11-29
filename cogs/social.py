import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import json
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiohttp
import os
import re

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.data_manager  # Use bot's data_manager instance
        self.logger = bot.logger.getChild('social')  # Add logger
        self.session = None  # aiohttp session
        self.default_themes = {
            "default": {
                "background_color": "#2C2F33",
                "text_color": "#FFFFFF",
                "accent_color": "#7289DA"
            },
            "night": {
                "background_color": "#1a1a1a",
                "text_color": "#E1E1E1",
                "accent_color": "#9B59B6"
            },
            "sunset": {
                "background_color": "#FF7F50",
                "text_color": "#FFFFFF",
                "accent_color": "#FFD700"
            }
        }
        self.available_badges = {
            "early_supporter": "",
            "active_chatter": "",
            "helper": "",
            "event_winner": "",
            "custom_badge": ""
        }
        self.font_path = os.path.join(os.getenv('SYSTEMROOT', ''), 'Fonts', 'arial.ttf')
        if not os.path.exists(self.font_path):
            self.font_path = os.path.join(os.getenv('SYSTEMROOT', ''), 'Fonts', 'segoeui.ttf')

    async def cog_load(self):
        """Called when the cog is loaded."""
        try:
            self.session = aiohttp.ClientSession()
            await self._init_profile_data()
            self.logger.info("Social cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading social cog: {e}")
            raise

    async def _init_profile_data(self):
        """Initialize default profile data."""
        try:
            if not await self.data_manager.exists('user_profiles'):
                await self.data_manager.save('user_profiles', 'default', {
                    'bio': '',
                    'title': '',
                    'theme': self.default_themes['default'],
                    'badges': [],
                    'created_at': None
                })
            self.logger.info("Profile data initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize profile data: {e}")
            raise

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        if self.session:
            await self.session.close()

    @app_commands.command(name="setbio", description="Set your profile bio")
    async def set_bio(self, interaction: discord.Interaction, bio: str):
        """Set your profile bio."""
        try:
            if len(bio) > 1000:
                await interaction.response.send_message("Bio must be 1000 characters or less!", ephemeral=True)
                return

            await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                bio=bio
            )
            
            await interaction.response.send_message("Bio updated successfully!", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error setting bio: {e}")
            await interaction.response.send_message("Failed to update bio. Please try again later.", ephemeral=True)
            raise e

    @app_commands.command(name="settheme", description="Set your profile theme color")
    async def set_theme(self, interaction: discord.Interaction, color: str):
        """Set your profile theme color."""
        try:
            # Validate color format (hex code)
            if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color):
                await interaction.response.send_message("Invalid color format! Please use hex code (e.g., #FF0000)", ephemeral=True)
                return

            await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                theme=color
            )
            
            await interaction.response.send_message("Theme color updated successfully!", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error setting theme: {e}")
            await interaction.response.send_message("Failed to update theme. Please try again later.", ephemeral=True)
            raise e

    @app_commands.command(name="settitle", description="Set your profile title")
    async def set_title(self, interaction: discord.Interaction, title: str):
        """Set your profile title."""
        try:
            if len(title) > 100:
                await interaction.response.send_message("Title must be 100 characters or less!", ephemeral=True)
                return

            await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                title=title
            )
            
            await interaction.response.send_message("Title updated successfully!", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error setting title: {e}")
            await interaction.response.send_message("Failed to update title. Please try again later.", ephemeral=True)
            raise e

    @app_commands.command(name="profile", description="View your or another user's profile")
    async def view_profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View a user's profile."""
        try:
            target_user = user or interaction.user
            profile_data = await self.data_manager.get_user_profile(target_user.id)

            if not profile_data:
                if target_user == interaction.user:
                    await interaction.response.send_message("You haven't set up your profile yet! Use /setbio, /settheme, or /settitle to get started.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"{target_user.display_name} hasn't set up their profile yet!", ephemeral=True)
                return

            # Create embed
            embed = discord.Embed(
                title=f"{target_user.display_name}'s Profile",
                color=int(profile_data.get('theme', '#FF69B4').lstrip('#'), 16) if profile_data.get('theme') else 0xFF69B4
            )
            
            if profile_data.get('title'):
                embed.add_field(name="Title", value=profile_data['title'], inline=False)
            if profile_data.get('bio'):
                embed.add_field(name="Bio", value=profile_data['bio'], inline=False)
            
            embed.set_thumbnail(url=target_user.display_avatar.url)
            embed.set_footer(text=f"Profile created: {profile_data.get('created_at', 'Unknown')}")

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            self.logger.error(f"Error viewing profile: {e}")
            await interaction.response.send_message("Failed to load profile. Please try again later.", ephemeral=True)
            raise e

    async def create_profile_card(self, user: discord.Member, profile_data: dict) -> BytesIO:
        """Create a profile card image"""
        # Get theme colors
        theme = self.default_themes[profile_data.get("theme", "default")]
        
        # Create base image
        width, height = 600, 400
        image = Image.new("RGB", (width, height), theme["background_color"])
        draw = ImageDraw.Draw(image)
        
        try:
            # Add user avatar
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(str(user.display_avatar.url)) as resp:
                if resp.status == 200:
                    avatar_data = await resp.read()
                    avatar = Image.open(BytesIO(avatar_data))
                    avatar = avatar.resize((100, 100))
                    
                    # Create circular mask for avatar
                    mask = Image.new("L", avatar.size, 0)
                    draw_mask = ImageDraw.Draw(mask)
                    draw_mask.ellipse((0, 0, 100, 100), fill=255)
                    
                    # Apply mask to avatar
                    output = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
                    output.paste(avatar, (0, 0))
                    output.putalpha(mask)
                    
                    # Paste avatar onto card
                    image.paste(output, (50, 50), output)

            # Load font
            try:
                font = ImageFont.truetype(self.font_path, 32)
                font_small = ImageFont.truetype(self.font_path, 24)
                font_smaller = ImageFont.truetype(self.font_path, 20)
            except OSError:
                font = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_smaller = ImageFont.load_default()

            # Add user name
            draw.text(
                (170, 60),
                user.display_name,
                fill=theme["text_color"],
                font=font
            )

            # Add custom title if set
            if profile_data.get("custom_title"):
                draw.text(
                    (170, 100),
                    profile_data["custom_title"],
                    fill=theme["accent_color"],
                    font=font_small
                )

            # Add bio
            draw.text(
                (50, 180),
                profile_data.get("bio", "No bio set"),
                fill=theme["text_color"],
                font=font_smaller
            )

            # Add badges
            badge_x = 50
            for badge in profile_data.get("badges", []):
                if badge in self.available_badges:
                    draw.text(
                        (badge_x, 250),
                        self.available_badges[badge],
                        fill=theme["accent_color"],
                        font=font
                    )
                    badge_x += 40

            # Convert to bytes
            buffer = BytesIO()
            image.save(buffer, "PNG")
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            raise Exception(f"Error creating profile card: {str(e)}")

async def setup(bot):
    await bot.add_cog(Social(bot))

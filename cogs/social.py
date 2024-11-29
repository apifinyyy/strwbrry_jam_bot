import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import json
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiohttp
import os
from utils.data_manager import DataManager

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = DataManager()
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
            "early_supporter": "🌟",
            "active_chatter": "💭",
            "helper": "🤝",
            "event_winner": "🏆",
            "custom_badge": "✨"
        }
        self.font_path = os.path.join(os.getenv('SYSTEMROOT', ''), 'Fonts', 'arial.ttf')
        if not os.path.exists(self.font_path):
            self.font_path = os.path.join(os.getenv('SYSTEMROOT', ''), 'Fonts', 'segoeui.ttf')

    async def cog_load(self):
        """Called when the cog is loaded."""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        if self.session:
            await self.session.close()

    @app_commands.command(name="profile")
    @app_commands.describe(
        user="The user whose profile to view (leave empty for your own)",
    )
    async def view_profile(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        """View a user's profile card"""
        await interaction.response.defer()
        
        try:
            user = user or interaction.user
            
            # Get user profile data
            profile_data = await self.data_manager.get_user_profile(user.id)
            if not profile_data:
                profile_data = {
                    "theme": "default",
                    "badges": [],
                    "bio": "No bio set",
                    "custom_title": None
                }

            # Create profile card
            card = await self.create_profile_card(user, profile_data)
            
            # Send profile card
            await interaction.followup.send(
                file=discord.File(card, "profile.png")
            )
        except Exception as e:
            await interaction.followup.send(
                "An error occurred while creating your profile. Please try again later.",
                ephemeral=True
            )
            raise e

    @app_commands.command(name="settheme")
    @app_commands.describe(
        theme="The theme to apply to your profile"
    )
    @app_commands.choices(theme=[
        app_commands.Choice(name=theme, value=theme)
        for theme in ["default", "night", "sunset"]
    ])
    async def set_theme(
        self,
        interaction: discord.Interaction,
        theme: str
    ):
        """Set your profile theme"""
        if theme not in self.default_themes:
            themes_list = ", ".join(self.default_themes.keys())
            await interaction.response.send_message(
                f"Invalid theme! Available themes: {themes_list}",
                ephemeral=True
            )
            return

        try:
            await self.data_manager.update_user_profile(
                interaction.user.id,
                {"theme": theme}
            )
            
            await interaction.response.send_message(
                f"Successfully set your profile theme to {theme}!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "An error occurred while updating your theme. Please try again later.",
                ephemeral=True
            )
            raise e

    @app_commands.command(name="setbio")
    @app_commands.describe(
        bio="Your new profile bio (max 100 characters)"
    )
    async def set_bio(
        self,
        interaction: discord.Interaction,
        bio: str
    ):
        """Set your profile bio"""
        if len(bio) > 100:
            await interaction.response.send_message(
                "Bio must be 100 characters or less!",
                ephemeral=True
            )
            return

        try:
            await self.data_manager.update_user_profile(
                interaction.user.id,
                {"bio": bio}
            )
            
            await interaction.response.send_message(
                "Successfully updated your bio!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "An error occurred while updating your bio. Please try again later.",
                ephemeral=True
            )
            raise e

    @app_commands.command(name="settitle")
    @app_commands.describe(
        title="Your custom profile title (max 30 characters)"
    )
    async def set_title(
        self,
        interaction: discord.Interaction,
        title: str
    ):
        """Set your custom profile title"""
        if len(title) > 30:
            await interaction.response.send_message(
                "Title must be 30 characters or less!",
                ephemeral=True
            )
            return

        try:
            await self.data_manager.update_user_profile(
                interaction.user.id,
                {"custom_title": title}
            )
            
            await interaction.response.send_message(
                "Successfully updated your title!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "An error occurred while updating your title. Please try again later.",
                ephemeral=True
            )
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

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Union
import logging
import re
from datetime import datetime, timedelta
from io import BytesIO
import json
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import os
import asyncio
import time

class Social(commands.Cog):
    """Social commands for user interaction"""
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logger = bot.logger.getChild('social')
        self.data_manager = bot.data_manager
        self.session = None
        self._profile_cache = {}  # user_id -> (profile_data, timestamp)
        self._cache_ttl = 300  # 5 minutes
        self._profile_lock = asyncio.Lock()  # Lock for thread-safe profile updates
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

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        """Get user data from all relevant systems."""
        data = {}
        
        # Get XP data
        try:
            xp_data = self.bot.data_manager.load_data(guild_id, "xp")
            if str(user_id) in xp_data:
                data.update(xp_data[str(user_id)])
        except FileNotFoundError:
            data.update({
                "chat_xp": 0,
                "voice_xp": 0
            })

        # Get economy data
        try:
            economy_data = self.bot.data_manager.load_data(guild_id, "economy")
            if str(user_id) in economy_data:
                data.update({
                    "balance": economy_data[str(user_id)]["balance"],
                    "inventory": economy_data[str(user_id)].get("inventory", [])
                })
        except FileNotFoundError:
            data.update({
                "balance": 0,
                "inventory": []
            })

        return data

    async def _get_cached_profile(self, user_id: int) -> Optional[dict]:
        """Get cached profile data if available and not expired."""
        if user_id in self._profile_cache:
            data, timestamp = self._profile_cache[user_id]
            if time.time() - timestamp < self._cache_ttl:
                return data
            del self._profile_cache[user_id]
        return None

    async def _cache_profile(self, user_id: int, profile_data: dict):
        """Cache profile data with timestamp."""
        self._profile_cache[user_id] = (profile_data, time.time())

    async def _validate_user_permissions(self, interaction: discord.Interaction, target_user: discord.Member = None) -> bool:
        """Validate user permissions for social commands."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server!", ephemeral=True)
            return False
        
        if target_user and target_user.bot:
            await interaction.response.send_message("You cannot interact with bot users!", ephemeral=True)
            return False

        return True

    @commands.Cog.listener()
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle command errors."""
        if isinstance(error, commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.1f}s",
                ephemeral=True
            )
        elif isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command!",
                ephemeral=True
            )
        else:
            self.logger.error(f"Command error: {str(error)}", exc_info=error)
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True
            )

    social_group = app_commands.Group(name="social", description="Social commands for user interaction")

    @social_group.command(name="profile")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(user="User to view profile of")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View a user's profile"""
        try:
            if not await self._validate_user_permissions(interaction, user):
                return

            target = user or interaction.user
            
            # Try to get cached profile first
            profile_data = await self._get_cached_profile(target.id)
            if not profile_data:
                profile_data = await self.data_manager.get_user_profile(target.id)
                await self._cache_profile(target.id, profile_data)
            
            # Create embed with enhanced styling
            embed = discord.Embed(
                title=f"🎭 {target.name}'s Profile",
                description=profile_data.get("bio", "*No bio set*"),
                color=discord.Color.from_str(profile_data.get("theme_color", "#5865F2"))
            )
            
            # Set thumbnail with fallback
            embed.set_thumbnail(url=target.display_avatar.url)
            
            # Add enhanced fields with emojis and formatting
            if profile_data.get("title"):
                embed.add_field(
                    name="📜 Title",
                    value=profile_data["title"],
                    inline=False
                )

            # Add level and XP with progress bar
            level = profile_data.get("level", 1)
            xp = profile_data.get("xp", 0)
            xp_needed = (level * 100)  # Simple XP calculation
            progress = min(xp / xp_needed * 10, 10)
            progress_bar = "▰" * int(progress) + "▱" * (10 - int(progress))
            
            embed.add_field(
                name="📊 Level Progress",
                value=f"Level {level} | {progress_bar} | {xp}/{xp_needed} XP",
                inline=False
            )

            # Add badges with proper formatting
            if badges := profile_data.get("badges", []):
                embed.add_field(
                    name="🏆 Badges",
                    value=" ".join(self.available_badges.get(badge, "❔") for badge in badges),
                    inline=False
                )

            # Add member information
            joined_at = discord.utils.format_dt(target.joined_at, style="R")
            created_at = discord.utils.format_dt(target.created_at, style="R")
            embed.add_field(name="📅 Joined", value=joined_at, inline=True)
            embed.add_field(name="🎂 Created", value=created_at, inline=True)

            # Add footer with last update time
            embed.set_footer(text=f"Last updated {discord.utils.format_dt(datetime.now(), style='R')}")
            
            await interaction.response.send_message(embed=embed)
            self.logger.info(f"Profile displayed for {target.name} (ID: {target.id})")

        except Exception as e:
            self.logger.error(f"Error displaying profile: {str(e)}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while displaying the profile. Please try again later.",
                ephemeral=True
            )

    async def create_profile_card(self, user: discord.Member, profile_data: dict) -> BytesIO:
        """Create an enhanced profile card image with error handling and retries."""
        async def get_avatar_with_retry(retries=3):
            for attempt in range(retries):
                try:
                    if not self.session:
                        self.session = aiohttp.ClientSession()
                    async with self.session.get(str(user.display_avatar.url)) as resp:
                        if resp.status == 200:
                            return await resp.read()
                except Exception as e:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(1)
            return None

        try:
            # Get theme with fallback
            theme = self.default_themes.get(
                profile_data.get("theme", "default"),
                self.default_themes["default"]
            )
            
            # Create base image with gradient background
            width, height = 600, 400
            image = Image.new("RGB", (width, height))
            gradient = self._create_gradient(
                width, height,
                theme["background_color"],
                self._adjust_color(theme["background_color"], -30)
            )
            image.paste(gradient, (0, 0))
            draw = ImageDraw.Draw(image)

            # Add avatar with enhanced error handling
            avatar_data = await get_avatar_with_retry()
            if avatar_data:
                avatar = await asyncio.to_thread(self._process_avatar, avatar_data)
                if avatar:
                    image.paste(avatar, (50, 50), avatar)

            # Load fonts with fallback
            fonts = await self._load_fonts()
            
            # Add user information with enhanced styling
            self._add_text_with_shadow(
                draw,
                (170, 60),
                user.display_name,
                fonts["large"],
                theme["text_color"]
            )

            if title := profile_data.get("custom_title"):
                self._add_text_with_shadow(
                    draw,
                    (170, 100),
                    title,
                    fonts["medium"],
                    theme["accent_color"]
                )

            # Add bio with word wrap
            bio = profile_data.get("bio", "No bio set")
            wrapped_bio = self._wrap_text(bio, fonts["small"], 400)
            y = 180
            for line in wrapped_bio:
                self._add_text_with_shadow(
                    draw,
                    (50, y),
                    line,
                    fonts["small"],
                    theme["text_color"]
                )
                y += 25

            # Add badges with enhanced visuals
            badge_x = 50
            for badge in profile_data.get("badges", []):
                if badge in self.available_badges:
                    self._add_badge(
                        draw,
                        (badge_x, 250),
                        self.available_badges[badge],
                        fonts["large"],
                        theme["accent_color"]
                    )
                    badge_x += 40

            # Add decorative elements
            self._add_decorative_elements(draw, width, height, theme)

            # Convert to bytes with optimization
            buffer = BytesIO()
            image.save(buffer, "PNG", optimize=True)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            self.logger.error(f"Error creating profile card: {str(e)}", exc_info=True)
            raise

    def _create_gradient(self, width: int, height: int, start_color: str, end_color: str) -> Image:
        """Create a gradient background."""
        gradient = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(gradient)
        
        r1, g1, b1 = self._hex_to_rgb(start_color)
        r2, g2, b2 = self._hex_to_rgb(end_color)
        
        for y in range(height):
            r = int(r1 + (r2 - r1) * y / height)
            g = int(g1 + (g2 - g1) * y / height)
            b = int(b1 + (b2 - b1) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
            
        return gradient

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _adjust_color(self, hex_color: str, adjustment: int) -> str:
        """Adjust a hex color by a value."""
        r, g, b = self._hex_to_rgb(hex_color)
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, r + adjustment)),
            max(0, min(255, g + adjustment)),
            max(0, min(255, b + adjustment))
        )

    async def _load_fonts(self) -> dict:
        """Load fonts with fallback options."""
        try:
            return {
                "large": ImageFont.truetype(self.font_path, 32),
                "medium": ImageFont.truetype(self.font_path, 24),
                "small": ImageFont.truetype(self.font_path, 20)
            }
        except OSError:
            return {
                "large": ImageFont.load_default(),
                "medium": ImageFont.load_default(),
                "small": ImageFont.load_default()
            }

    def _add_text_with_shadow(self, draw: ImageDraw, pos: tuple, text: str, font: ImageFont, color: str):
        """Add text with a shadow effect."""
        shadow_color = self._adjust_color(color, -50)
        x, y = pos
        draw.text((x+2, y+2), text, font=font, fill=shadow_color)
        draw.text((x, y), text, font=font, fill=color)

    def _wrap_text(self, text: str, font: ImageFont, max_width: int) -> list:
        """Wrap text to fit within a given width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            current_line.append(word)
            line = " ".join(current_line)
            if font.getlength(line) > max_width:
                if len(current_line) == 1:
                    lines.append(current_line.pop())
                else:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return lines[:4]  # Limit to 4 lines

    def _add_badge(self, draw: ImageDraw, pos: tuple, badge: str, font: ImageFont, color: str):
        """Add a badge with enhanced visuals."""
        x, y = pos
        size = font.getsize(badge)[0] + 20
        draw.ellipse([x, y, x+size, y+size], outline=color, width=2)
        self._add_text_with_shadow(
            draw,
            (x + 10, y + 10),
            badge,
            font,
            color
        )

    def _add_decorative_elements(self, draw: ImageDraw, width: int, height: int, theme: dict):
        """Add decorative elements to the profile card."""
        # Add corner accents
        accent_color = theme["accent_color"]
        draw.line([(0, 0), (20, 0), (0, 20)], fill=accent_color, width=2)
        draw.line([(width-20, 0), (width, 0), (width, 20)], fill=accent_color, width=2)
        draw.line([(0, height-20), (0, height), (20, height)], fill=accent_color, width=2)
        draw.line([(width-20, height), (width, height), (width, height-20)], fill=accent_color, width=2)

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
        """Cleanup when cog is unloaded."""
        if self.session:
            await self.session.close()
        self._profile_cache.clear()
        self.logger.info("Social cog unloaded and cleaned up successfully")

    @social_group.command(name="setbio")
    @app_commands.describe(bio="Your new profile bio (max 200 characters)")
    async def setbio(self, interaction: discord.Interaction, bio: app_commands.Range[str, 1, 200]):
        """Set your profile bio"""
        try:
            if len(bio) > 200:
                await interaction.response.send_message("Bio must be 200 characters or less!", ephemeral=True)
                return

            success = await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                bio=bio
            )
            
            if success:
                await interaction.response.send_message("Bio updated successfully!", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to update bio. Please try again later.", ephemeral=True)
                
        except Exception as e:
            self.logger.error(f"Error setting bio: {e}", exc_info=True)
            await interaction.response.send_message("Failed to update bio. Please try again later.", ephemeral=True)

    @social_group.command(name="settheme")
    @app_commands.describe(color="Hex color code (e.g., #FF0000 for red)")
    async def settheme(self, interaction: discord.Interaction, color: str):
        """Set your profile theme color"""
        try:
            # Validate color format
            if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color):
                await interaction.response.send_message("Invalid color format! Please use a hex color code (e.g., #FF0000)", ephemeral=True)
                return

            success = await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                theme_color=color
            )
            
            if success:
                await interaction.response.send_message(f"Theme color updated to {color}!", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to update theme. Please try again later.", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error setting theme: {e}", exc_info=True)
            await interaction.response.send_message("Failed to update theme. Please try again later.", ephemeral=True)

    @social_group.command(name="settitle")
    @app_commands.describe(title="Your profile title (max 100 characters)")
    async def settitle(self, interaction: discord.Interaction, title: app_commands.Range[str, 1, 100]):
        """Set your profile title"""
        try:
            success = await self.data_manager.update_user_profile(
                user_id=interaction.user.id,
                title=title
            )
            
            if success:
                await interaction.response.send_message("Title updated successfully!", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to update title. Please try again later.", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error setting title: {e}", exc_info=True)
            await interaction.response.send_message("Failed to update title. Please try again later.", ephemeral=True)

    @social_group.command(name="leaderboard")
    @app_commands.describe(category="What to show on the leaderboard")
    @app_commands.choices(category=[
        app_commands.Choice(name="XP", value="xp"),
        app_commands.Choice(name="Level", value="level")
    ])
    async def leaderboard(self, interaction: discord.Interaction, category: str = "xp"):
        """View the server leaderboard"""
        try:
            # Get leaderboard data from database
            leaderboard_data = await self.data_manager.get_leaderboard(interaction.guild_id, category)
            
            # Create embed
            embed = discord.Embed(
                title=f"🏆 Server Leaderboard ({category.upper()})",
                color=discord.Color.gold()
            )
            
            # Add fields for top 10 users
            for i, entry in enumerate(leaderboard_data[:10], 1):
                user = interaction.guild.get_member(entry["user_id"])
                if user:
                    embed.add_field(
                        name=f"#{i} {user.name}",
                        value=f"{entry[category]} {category.upper()}",
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error viewing leaderboard: {e}", exc_info=True)
            await interaction.response.send_message("Failed to load leaderboard. Please try again later.", ephemeral=True)

    @social_group.command(name="rep")
    @app_commands.describe(user="User to give reputation to")
    async def rep(self, interaction: discord.Interaction, user: discord.Member):
        """Give reputation to a user"""
        try:
            # Check if user is trying to rep themselves
            if user.id == interaction.user.id:
                await interaction.response.send_message("You cannot give reputation to yourself!", ephemeral=True)
                return
            
            # Check cooldown
            cooldown = await self.data_manager.check_rep_cooldown(interaction.user.id)
            if cooldown:
                await interaction.response.send_message(f"You can give reputation again {cooldown}", ephemeral=True)
                return
            
            # Give reputation
            await self.data_manager.give_rep(interaction.user.id, user.id)
            
            # Get updated rep count
            rep_count = await self.data_manager.get_rep_count(user.id)
            
            await interaction.response.send_message(f"You gave +1 reputation to {user.mention}! They now have {rep_count} reputation points.")

        except Exception as e:
            self.logger.error(f"Error giving reputation: {e}", exc_info=True)
            await interaction.response.send_message("Failed to give reputation. Please try again later.", ephemeral=True)

    @social_group.command(name="marry")
    @app_commands.describe(user="User to propose to")
    async def marry(self, interaction: discord.Interaction, user: discord.Member):
        """Propose marriage to another user"""
        try:
            # Check if user is trying to marry themselves
            if user.id == interaction.user.id:
                await interaction.response.send_message("You cannot marry yourself!", ephemeral=True)
                return
            
            # Check if either user is already married
            proposer_married = await self.data_manager.check_marriage(interaction.user.id)
            target_married = await self.data_manager.check_marriage(user.id)
            
            if proposer_married:
                await interaction.response.send_message("You are already married!", ephemeral=True)
                return
                
            if target_married:
                await interaction.response.send_message(f"{user.mention} is already married!", ephemeral=True)
                return
            
            # Create proposal embed
            embed = discord.Embed(
                title="💍 Marriage Proposal",
                description=f"{interaction.user.mention} has proposed to {user.mention}!",
                color=discord.Color.pink()
            )
            
            # Create buttons for accept/decline
            class ProposalView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60.0)
                    self.value = None
                
                @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
                async def accept(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = True
                    self.stop()
                
                @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
                async def decline(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = False
                    self.stop()
            
            # Send proposal
            view = ProposalView()
            await interaction.response.send_message(embed=embed, view=view)
            
            # Wait for response
            await view.wait()
            
            if view.value is None:
                await interaction.edit_original_response(content="The proposal has timed out.", embed=None, view=None)
            elif view.value:
                # Create marriage
                await self.data_manager.create_marriage(interaction.user.id, user.id)
                
                success_embed = discord.Embed(
                    title="💝 Marriage Successful",
                    description=f"Congratulations to the happy couple: {interaction.user.mention} and {user.mention}!",
                    color=discord.Color.pink()
                )
                
                await interaction.edit_original_response(embed=success_embed, view=None)
            else:
                decline_embed = discord.Embed(
                    title="💔 Proposal Declined",
                    description=f"{user.mention} has declined the proposal.",
                    color=discord.Color.red()
                )
                
                await interaction.edit_original_response(embed=decline_embed, view=None)

        except Exception as e:
            self.logger.error(f"Error proposing marriage: {e}", exc_info=True)
            await interaction.response.send_message("Failed to propose marriage. Please try again later.", ephemeral=True)

    @social_group.command(name="divorce")
    async def divorce(self, interaction: discord.Interaction):
        """Divorce your current partner"""
        try:
            # Check if user is married
            partner_id = await self.data_manager.check_marriage(interaction.user.id)
            if not partner_id:
                await interaction.response.send_message("You are not married!", ephemeral=True)
                return
            
            # Get partner
            partner = interaction.guild.get_member(partner_id)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="💔 Divorce Confirmation",
                description="Are you sure you want to proceed with the divorce?",
                color=discord.Color.red()
            )
            
            # Create buttons for confirm/cancel
            class DivorceView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60.0)
                    self.value = None
                
                @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red)
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = True
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = False
                    self.stop()
            
            # Send confirmation
            view = DivorceView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            # Wait for response
            await view.wait()
            
            if view.value is None:
                await interaction.edit_original_response(content="The divorce request has timed out.", embed=None, view=None)
            elif view.value:
                # Process divorce
                await self.data_manager.process_divorce(interaction.user.id, partner_id)
                
                divorce_embed = discord.Embed(
                    title="💔 Divorce Finalized",
                    description=f"{interaction.user.mention} and {partner.mention} are now divorced.",
                    color=discord.Color.red()
                )
                
                await interaction.edit_original_response(embed=divorce_embed, view=None)
            else:
                cancel_embed = discord.Embed(
                    title="💝 Divorce Cancelled",
                    description="The divorce has been cancelled.",
                    color=discord.Color.green()
                )
                
                await interaction.edit_original_response(embed=cancel_embed, view=None)

        except Exception as e:
            self.logger.error(f"Error divorcing: {e}", exc_info=True)
            await interaction.response.send_message("Failed to divorce. Please try again later.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Social(bot))

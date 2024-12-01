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
        self.data_manager = bot.data_manager
        self.data_type = "social"
        self.logger = bot.logger.getChild('social')
        self.marriage_data = {}  # guild_id -> {user_id -> partner_id}
        self.marriage_proposals = {}  # user_id -> {target_id, timestamp}
        self.proposal_timeout = 60  # seconds
        self.marriage_cost = 1000  # coins cost to marry
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
        self.rep_cooldowns = {}  # Store reputation cooldowns
        self.default_user_data = {
            "reputation": 0,
            "given_reputation": 0,
            "last_rep_given": None,
            "reputation_received_from": []  # List of user IDs who gave rep
        }

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

        # Get social data
        try:
            social_data = self.bot.data_manager.load_data(guild_id, self.data_type)
            if str(user_id) in social_data:
                data.update(social_data[str(user_id)])
        except FileNotFoundError:
            data.update(self.default_user_data.copy())

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
        """Initialize profile data"""
        try:
            # Initialize user profiles if they don't exist
            if not await self.bot.data_manager.exists('user_profiles'):
                await self.bot.data_manager.save('user_profiles', 'default', {})
                self.logger.info("Created user_profiles data structure")
            
            # Load existing profiles
            self._profile_cache = {}  # Reset cache
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

    async def _load_marriage_data(self, guild_id: int) -> dict:
        """Load marriage data for a guild"""
        try:
            data = await self.bot.data_manager.load_data(guild_id, self.data_type) or {}
            if 'marriages' not in data:
                data['marriages'] = {}
            return data
        except Exception as e:
            self.logger.error(f"Error loading marriage data: {e}")
            return {'marriages': {}}

    async def _save_marriage_data(self, guild_id: int, data: dict) -> bool:
        """Save marriage data for a guild"""
        try:
            await self.bot.data_manager.save_data(guild_id, self.data_type, data)
            return True
        except Exception as e:
            self.logger.error(f"Error saving marriage data: {e}")
            return False

    async def check_marriage(self, guild_id: int, user_id: int) -> Optional[int]:
        """Check if a user is married. Returns partner ID if married, None if not."""
        data = await self._load_marriage_data(guild_id)
        return data['marriages'].get(str(user_id))

    @social_group.command(name="marry")
    @app_commands.describe(user="User to propose to")
    async def marry(self, interaction: discord.Interaction, user: discord.Member):
        """Propose marriage to another user"""
        try:
            # Basic validation
            if user.id == interaction.user.id:
                await interaction.response.send_message("💔 You cannot marry yourself!", ephemeral=True)
                return

            if user.bot:
                await interaction.response.send_message("💔 You cannot marry a bot!", ephemeral=True)
                return

            # Check existing marriages
            data = await self._load_marriage_data(interaction.guild_id)
            proposer_partner = data['marriages'].get(str(interaction.user.id))
            target_partner = data['marriages'].get(str(user.id))

            if proposer_partner:
                partner = interaction.guild.get_member(proposer_partner)
                partner_mention = partner.mention if partner else "someone"
                await interaction.response.send_message(
                    f"💔 You are already married to {partner_mention}!",
                    ephemeral=True
                )
                return

            if target_partner:
                partner = interaction.guild.get_member(target_partner)
                partner_mention = partner.mention if partner else "someone"
                await interaction.response.send_message(
                    f"💔 {user.mention} is already married to {partner_mention}!",
                    ephemeral=True
                )
                return

            # Check if user has enough coins
            economy_cog = interaction.client.get_cog("Economy")
            if economy_cog:
                user_data = economy_cog._get_user_data(interaction.guild_id, interaction.user.id)
                if user_data["balance"] < self.marriage_cost:
                    await interaction.response.send_message(
                        f"💔 Marriage costs 🪙 {self.marriage_cost:,} coins! You only have 🪙 {user_data['balance']:,}.",
                        ephemeral=True
                    )
                    return

            # Create proposal embed
            embed = discord.Embed(
                title="💝 Marriage Proposal",
                description=(
                    f"{interaction.user.mention} has proposed to {user.mention}!\n\n"
                    f"Marriage will cost 🪙 {self.marriage_cost:,} coins.\n"
                    "The proposal will expire in 60 seconds."
                ),
                color=discord.Color.pink()
            )

            # Create buttons for accept/decline
            class ProposalView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60.0)
                    self.value = None

                @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="💍")
                async def accept(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user.id != user.id:
                        await button_interaction.response.send_message(
                            "💔 Only the person being proposed to can accept!",
                            ephemeral=True
                        )
                        return
                    self.value = True
                    for item in self.children:
                        item.disabled = True
                    await button_interaction.response.edit_message(view=self)
                    self.stop()

                @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="💔")
                async def decline(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user.id != user.id:
                        await button_interaction.response.send_message(
                            "💔 Only the person being proposed to can decline!",
                            ephemeral=True
                        )
                        return
                    self.value = False
                    for item in self.children:
                        item.disabled = True
                    await button_interaction.response.edit_message(view=self)
                    self.stop()

            # Send proposal
            view = ProposalView()
            await interaction.response.send_message(embed=embed, view=view)

            # Wait for response
            await view.wait()

            if view.value is None:
                timeout_embed = discord.Embed(
                    title="💔 Proposal Expired",
                    description="The marriage proposal has timed out.",
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=timeout_embed, view=None)
            
            elif view.value:
                # Deduct coins
                if economy_cog:
                    user_data = economy_cog._get_user_data(interaction.guild_id, interaction.user.id)
                    user_data["balance"] -= self.marriage_cost
                    economy_cog._save_user_data(interaction.guild_id, interaction.user.id, user_data)

                # Create marriage
                data['marriages'][str(interaction.user.id)] = user.id
                data['marriages'][str(user.id)] = interaction.user.id
                await self._save_marriage_data(interaction.guild_id, data)

                success_embed = discord.Embed(
                    title="💝 Marriage Successful",
                    description=(
                        f"Congratulations to the happy couple!\n"
                        f"👰‍♀️ {interaction.user.mention} & {user.mention} 🤵‍♂️\n\n"
                        f"Marriage cost: 🪙 {self.marriage_cost:,} coins"
                    ),
                    color=discord.Color.pink()
                )
                success_embed.set_footer(text="Use /divorce if you ever need to end the marriage")
                
                await interaction.edit_original_response(embed=success_embed, view=None)
            
            else:
                decline_embed = discord.Embed(
                    title="💔 Proposal Declined",
                    description=f"{user.mention} has declined the proposal.",
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=decline_embed, view=None)

        except Exception as e:
            self.logger.error(f"Error in marriage command: {e}")
            await interaction.response.send_message(
                "💔 An error occurred with the marriage command. Please try again.",
                ephemeral=True
            )

    @social_group.command(name="divorce")
    async def divorce(self, interaction: discord.Interaction):
        """Divorce your current partner"""
        try:
            # Check if user is married
            data = await self._load_marriage_data(interaction.guild_id)
            partner_id = data['marriages'].get(str(interaction.user.id))
            
            if not partner_id:
                await interaction.response.send_message(
                    "💔 You are not married!",
                    ephemeral=True
                )
                return

            # Get partner
            partner = interaction.guild.get_member(partner_id)
            partner_mention = partner.mention if partner else "your partner"

            # Create confirmation embed
            embed = discord.Embed(
                title="💔 Divorce Confirmation",
                description=f"Are you sure you want to divorce {partner_mention}?",
                color=discord.Color.red()
            )

            # Create buttons for confirm/cancel
            class DivorceView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60.0)
                    self.value = None

                @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red, emoji="💔")
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = True
                    for item in self.children:
                        item.disabled = True
                    await button_interaction.response.edit_message(view=self)
                    self.stop()

                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="❌")
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.value = False
                    for item in self.children:
                        item.disabled = True
                    await button_interaction.response.edit_message(view=self)
                    self.stop()

            # Send confirmation
            view = DivorceView()
            await interaction.response.send_message(embed=embed, view=view)

            # Wait for response
            await view.wait()

            if view.value is None:
                timeout_embed = discord.Embed(
                    title="💔 Divorce Cancelled",
                    description="The divorce request has timed out.",
                    color=discord.Color.grey()
                )
                await interaction.edit_original_response(embed=timeout_embed, view=None)

            elif view.value:
                # Process divorce
                if str(interaction.user.id) in data['marriages']:
                    del data['marriages'][str(interaction.user.id)]
                if str(partner_id) in data['marriages']:
                    del data['marriages'][str(partner_id)]
                
                await self._save_marriage_data(interaction.guild_id, data)

                divorce_embed = discord.Embed(
                    title="💔 Divorce Finalized",
                    description=f"{interaction.user.mention} and {partner_mention} are now divorced.",
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
            self.logger.error(f"Error in divorce command: {e}")
            await interaction.response.send_message(
                "💔 An error occurred with the divorce command. Please try again.",
                ephemeral=True
            )

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
                await interaction.response.send_message(
                    "❌ You cannot give reputation to yourself!",
                    ephemeral=True
                )
                return

            # Check if user is a bot
            if user.bot:
                await interaction.response.send_message(
                    "❌ You cannot give reputation to bots!",
                    ephemeral=True
                )
                return

            # Get giver's data
            giver_data = self._get_user_data(interaction.guild_id, interaction.user.id)

            # Check cooldown
            if giver_data["last_rep_given"]:
                last_rep = datetime.fromisoformat(giver_data["last_rep_given"])
                time_since_last = datetime.now() - last_rep
                if time_since_last < timedelta(hours=24):
                    time_left = timedelta(hours=24) - time_since_last
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    await interaction.response.send_message(
                        f"⏰ You can give reputation again in {hours}h {minutes}m",
                        ephemeral=True
                    )
                    return

            # Get receiver's data
            receiver_data = self._get_user_data(interaction.guild_id, user.id)

            # Check if already given rep to this user today
            if interaction.user.id in receiver_data["reputation_received_from"]:
                await interaction.response.send_message(
                    "❌ You have already given reputation to this user!",
                    ephemeral=True
                )
                return

            # Update receiver's data
            receiver_data["reputation"] += 1
            receiver_data["reputation_received_from"].append(interaction.user.id)

            # Update giver's data
            giver_data["given_reputation"] += 1
            giver_data["last_rep_given"] = datetime.now().isoformat()

            # Save both users' data
            if not (self._save_user_data(interaction.guild_id, user.id, receiver_data) and 
                   self._save_user_data(interaction.guild_id, interaction.user.id, giver_data)):
                await interaction.response.send_message(
                    "❌ An error occurred while saving reputation data",
                    ephemeral=True
                )
                return

            # Send success message with embed
            embed = discord.Embed(
                title="⭐ Reputation Given!",
                description=f"{interaction.user.mention} gave a reputation point to {user.mention}!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="New Reputation",
                value=f"✨ {receiver_data['reputation']} points",
                inline=True
            )
            embed.add_field(
                name="Total Given",
                value=f"🎁 {giver_data['given_reputation']} points",
                inline=True
            )
            embed.set_footer(text="You can give reputation again in 24 hours")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in rep command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while giving reputation",
                ephemeral=True
            )

    @social_group.command(name="toprep")
    async def toprep(self, interaction: discord.Interaction):
        """Display the server's reputation leaderboard"""
        try:
            data = self.bot.data_manager.load_data(interaction.guild_id, self.data_type)
            if not data:
                await interaction.response.send_message(
                    "❌ No reputation data found for this server!",
                    ephemeral=True
                )
                return

            # Sort users by reputation
            sorted_users = sorted(
                [(int(uid), udata["reputation"]) for uid, udata in data.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]  # Top 10

            if not sorted_users:
                await interaction.response.send_message(
                    "❌ No users have received reputation yet!",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="✨ Reputation Leaderboard",
                color=discord.Color.gold()
            )

            # Add server stats
            total_rep = sum(udata["reputation"] for udata in data.values())
            active_users = len([u for u in data.values() if u["reputation"] > 0])
            embed.description = (
                f"**Server Stats**\n"
                f"Total Rep Points: ✨ {total_rep:,}\n"
                f"Users with Rep: 👥 {active_users:,}\n"
            )

            # Create leaderboard text
            medals = ["🥇", "🥈", "🥉"]
            leaderboard = []
            
            for idx, (user_id, rep) in enumerate(sorted_users, 1):
                user = interaction.guild.get_member(user_id)
                if user:
                    medal = medals[idx-1] if idx <= 3 else f"`{idx}.`"
                    leaderboard.append(
                        f"{medal} **{user.display_name}**\n"
                        f"└ ✨ {rep:,} reputation points"
                    )

            embed.add_field(
                name="🏆 Top 10 Most Reputable",
                value="\n".join(leaderboard) or "No ranked users found",
                inline=False
            )

            # Show requester's position if not in top 10
            if interaction.user.id not in [uid for uid, _ in sorted_users]:
                user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
                all_users = sorted(
                    [(int(uid), udata["reputation"]) for uid, udata in data.items()],
                    key=lambda x: x[1],
                    reverse=True
                )
                user_position = next(
                    (idx for idx, (uid, _) in enumerate(all_users, 1) if uid == interaction.user.id),
                    None
                )
                if user_position:
                    embed.add_field(
                        name="📊 Your Ranking",
                        value=f"You are ranked #{user_position} with ✨ {user_data['reputation']:,} points",
                        inline=False
                    )

            embed.set_footer(text="💡 Use /rep to give reputation to others!")
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in toprep command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching the leaderboard",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Social(bot))

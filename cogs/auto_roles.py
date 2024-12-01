import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, Dict, List, Optional
import logging
import asyncio
from datetime import datetime

class AutoRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_roles_key = "auto_roles"
        self.logger = logging.getLogger('strwbrry_jam.auto_roles')
        self._config_cache = {}
        self._cache_lock = asyncio.Lock()
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update = {}

    def get_safe_default_config(self) -> dict:
        """Return safe default configuration"""
        return {
            'join_roles': [],
            'reaction_roles': {},
            'last_updated': datetime.utcnow().isoformat()
        }

    async def get_auto_role_config(self, guild_id: int) -> dict:
        """Get auto role configuration for a guild with caching."""
        try:
            str_guild_id = str(guild_id)
            
            # Check cache first
            async with self._cache_lock:
                if str_guild_id in self._config_cache:
                    if datetime.utcnow().timestamp() - self._last_cache_update.get(str_guild_id, 0) < self._cache_ttl:
                        return self._config_cache[str_guild_id].copy()

            # Load from database
            config = await self.bot.data_manager.load_json("roles", self.auto_roles_key) or {}
            
            if str_guild_id not in config:
                config[str_guild_id] = self.get_safe_default_config()
                await self.bot.data_manager.save_json("roles", self.auto_roles_key, config)
            
            # Update cache
            async with self._cache_lock:
                self._config_cache[str_guild_id] = config[str_guild_id].copy()
                self._last_cache_update[str_guild_id] = datetime.utcnow().timestamp()
            
            return config[str_guild_id]
        except Exception as e:
            self.logger.error(f"Error loading auto role config: {e}")
            return self.get_safe_default_config()

    async def save_auto_role_config(self, guild_id: int, auto_role_config: dict):
        """Save auto role configuration for a guild."""
        try:
            config = await self.bot.data_manager.load_json("roles", self.auto_roles_key)
            config[str(guild_id)] = auto_role_config
            await self.bot.data_manager.save_json("roles", self.auto_roles_key, config)
        except Exception as e:
            self.logger.error(f"Error saving auto role config: {e}")
            raise

    async def verify_role_hierarchy(self, guild: discord.Guild, role: discord.Role) -> bool:
        """Verify that the bot can manage the given role."""
        bot_member = guild.get_member(self.bot.user.id)
        return bot_member.top_role > role if bot_member else False

    async def verify_roles(self, guild: discord.Guild, config: dict) -> dict:
        """Verify and clean up invalid roles from config."""
        # Verify join roles
        config['join_roles'] = [
            role_id for role_id in config['join_roles']
            if guild.get_role(role_id) is not None
        ]
        
        # Verify reaction roles
        invalid_messages = []
        for msg_id, data in config['reaction_roles'].items():
            if not guild.get_role(data['role_id']):
                invalid_messages.append(msg_id)
        
        for msg_id in invalid_messages:
            del config['reaction_roles'][msg_id]
        
        return config

    @app_commands.command(name="autorole")
    @app_commands.describe(
        role="The role to add or remove from auto-assignment",
        action="Whether to add or remove the role from auto-assignment"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add role to auto-assign list", value="add"),
        app_commands.Choice(name="Remove role from auto-assign list", value="remove")
    ])
    @app_commands.default_permissions(manage_roles=True)
    async def autorole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        action: Literal["add", "remove"]
    ):
        """Configure roles to be automatically assigned to new members"""
        try:
            # Verify bot permissions first
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ I don't have the 'Manage Roles' permission in this server",
                    ephemeral=True
                )
                return

            # Check role hierarchy
            if not await self.verify_role_hierarchy(interaction.guild, role):
                await interaction.response.send_message(
                    f"❌ I cannot manage the role {role.mention} because it's higher than my highest role",
                    ephemeral=True
                )
                return

            config = await self.get_auto_role_config(interaction.guild_id)
            
            if action == "add":
                if role.id in config['join_roles']:
                    await interaction.response.send_message(
                        f"ℹ️ {role.mention} is already being auto-assigned to new members",
                        ephemeral=True
                    )
                else:
                    config['join_roles'].append(role.id)
                    await self.save_auto_role_config(interaction.guild_id, config)
                    await interaction.response.send_message(
                        f"✅ {role.mention} will now be automatically assigned to new members",
                        ephemeral=True
                    )
            else:
                if role.id in config['join_roles']:
                    config['join_roles'].remove(role.id)
                    await self.save_auto_role_config(interaction.guild_id, config)
                    await interaction.response.send_message(
                        f"✅ {role.mention} will no longer be auto-assigned to new members",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"ℹ️ {role.mention} is not in the auto-assign list",
                        ephemeral=True
                    )
        except Exception as e:
            self.logger.error(f"Error in autorole command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your request. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(name="reactionrole")
    @app_commands.describe(
        role="The role to assign when members react",
        emoji="The emoji that members should react with",
        message="Custom message to display (default: 'React to get a role!')",
        channel="Channel to send the message in (default: current channel)"
    )
    @app_commands.default_permissions(manage_roles=True)
    async def reactionrole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        emoji: str,
        message: str = "React to get a role!",
        channel: Optional[discord.TextChannel] = None
    ):
        """Create a message that assigns roles when members react to it"""
        try:
            # Verify bot permissions
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ I don't have the 'Manage Roles' permission in this server",
                    ephemeral=True
                )
                return

            # Check role hierarchy
            if not await self.verify_role_hierarchy(interaction.guild, role):
                await interaction.response.send_message(
                    f"❌ I cannot manage the role {role.mention} because it's higher than my highest role",
                    ephemeral=True
                )
                return

            # Validate emoji
            try:
                await interaction.guild.fetch_emoji(emoji) if emoji.isdigit() else emoji
            except (discord.NotFound, discord.HTTPException):
                if not any(emoji == e for e in interaction.guild.emojis):
                    await interaction.response.send_message(
                        "❌ Please provide a valid emoji or emoji ID",
                        ephemeral=True
                    )
                    return

            channel = channel or interaction.channel

            # Create embed
            embed = discord.Embed(
                title="Role Assignment",
                description=f"{message}\n\nReact with {emoji} to get the {role.mention} role!",
                color=role.color or discord.Color.blue()
            )
            embed.set_footer(text="Remove your reaction to remove the role")
            
            # Send message and add reaction
            await interaction.response.defer(ephemeral=True)
            msg = await channel.send(embed=embed)
            await msg.add_reaction(emoji)

            # Save configuration
            config = await self.get_auto_role_config(interaction.guild_id)
            config['reaction_roles'][str(msg.id)] = {
                'role_id': role.id,
                'emoji': emoji,
                'channel_id': channel.id
            }
            await self.save_auto_role_config(interaction.guild_id, config)
            
            await interaction.followup.send(
                f"✅ Reaction role message created in {channel.mention}! Members can now react with {emoji} to get the {role.mention} role.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error in reactionrole command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating the reaction role. Please try again later.",
                ephemeral=True
            )

    @app_commands.command(name="listroles")
    @app_commands.default_permissions(manage_roles=True)
    async def listroles(self, interaction: discord.Interaction):
        """List all auto-roles and reaction roles"""
        try:
            config = await self.get_auto_role_config(interaction.guild_id)
            
            embed = discord.Embed(
                title="Server Role Configuration",
                color=discord.Color.blue()
            )

            # Add auto-roles section
            auto_roles = []
            for role_id in config['join_roles']:
                role = interaction.guild.get_role(role_id)
                if role:
                    auto_roles.append(role.mention)
            
            embed.add_field(
                name="Auto-Roles",
                value="\n".join(auto_roles) if auto_roles else "No auto-roles configured",
                inline=False
            )

            # Add reaction roles section
            reaction_roles = []
            for msg_id, data in config['reaction_roles'].items():
                role = interaction.guild.get_role(data['role_id'])
                if role:
                    reaction_roles.append(f"{data['emoji']} → {role.mention}")
            
            embed.add_field(
                name="Reaction Roles",
                value="\n".join(reaction_roles) if reaction_roles else "No reaction roles configured",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error in listroles command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while listing roles. Please try again later.",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Assign auto-roles when a member joins"""
        if member.bot:
            return

        try:
            # Verify bot permissions
            if not member.guild.me.guild_permissions.manage_roles:
                self.logger.warning(f"Missing 'Manage Roles' permission in guild {member.guild.id}")
                return

            config = await self.get_auto_role_config(member.guild.id)
            config = await self.verify_roles(member.guild, config)
            
            roles_added = []
            roles_failed = []
            
            for role_id in config['join_roles']:
                role = member.guild.get_role(role_id)
                if role and await self.verify_role_hierarchy(member.guild, role):
                    try:
                        await member.add_roles(role, reason="Auto-role on join")
                        roles_added.append(role.name)
                    except discord.HTTPException as e:
                        roles_failed.append(role.name)
                        self.logger.error(f"Failed to add role {role.id} to member {member.id}: {e}")

            if roles_failed:
                self.logger.warning(
                    f"Failed to add some roles to {member} in {member.guild}: {', '.join(roles_failed)}"
                )

        except Exception as e:
            self.logger.error(f"Error in on_member_join event: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role assignments"""
        if payload.user_id == self.bot.user.id:
            return

        try:
            config = await self.get_auto_role_config(payload.guild_id)
            
            reaction_role = config['reaction_roles'].get(str(payload.message_id))
            if reaction_role and str(payload.emoji) == reaction_role['emoji']:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                member = guild.get_member(payload.user_id)
                role = guild.get_role(reaction_role['role_id'])
                
                if member and role:
                    await member.add_roles(role, reason="Reaction role assignment")
        except Exception as e:
            self.logger.error(f"Error in on_raw_reaction_add event: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role removals"""
        if payload.user_id == self.bot.user.id:
            return

        try:
            config = await self.get_auto_role_config(payload.guild_id)
            
            reaction_role = config['reaction_roles'].get(str(payload.message_id))
            if reaction_role and str(payload.emoji) == reaction_role['emoji']:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                member = guild.get_member(payload.user_id)
                role = guild.get_role(reaction_role['role_id'])
                
                if member and role:
                    await member.remove_roles(role, reason="Reaction role removal")
        except Exception as e:
            self.logger.error(f"Error in on_raw_reaction_remove event: {e}")

async def setup(bot):
    await bot.add_cog(AutoRoles(bot))

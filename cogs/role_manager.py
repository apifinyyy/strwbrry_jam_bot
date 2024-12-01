import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List, Literal
from datetime import datetime, timedelta
import logging
import json
import asyncio

class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_key = "roles_config"
        self.xp_key = "user_xp"
        self.logger = logging.getLogger('strwbrry_jam.role_manager')
        self.role_lock = asyncio.Lock()  # Add lock for thread safety
        self.check_xp_roles.start()  # Start the task loop

    def cog_unload(self):
        self.check_xp_roles.cancel()

    async def init_data(self):
        """Initialize role data"""
        try:
            data = await self.bot.data_manager.load_json("roles", self.roles_key)
        except FileNotFoundError:
            data = {
                "xp_roles": {},
                "persistent_roles": {}
            }
            await self.bot.data_manager.save_json("roles", self.roles_key, data)
        return data

    @tasks.loop(minutes=5.0)
    async def check_xp_roles(self):
        """Check and update roles based on XP periodically"""
        try:
            xp_data = await self.bot.data_manager.load_json("xp", self.xp_key)
            roles_config = await self.init_data()
            
            for guild_id, guild_data in xp_data.items():
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue
                    
                xp_roles = roles_config.get("xp_roles", {}).get(str(guild_id), {})
                if not xp_roles:
                    continue

                for user_id, user_xp in guild_data.items():
                    member = guild.get_member(int(user_id))
                    if not member:
                        continue

                    # Sort roles by XP requirement
                    sorted_roles = sorted(xp_roles.items(), key=lambda x: int(x[1]["xp_required"]))
                    
                    # Find the highest role the user qualifies for
                    highest_role = None
                    for role_id, role_data in sorted_roles:
                        if user_xp >= role_data["xp_required"]:
                            role = guild.get_role(int(role_id))
                            if role:
                                highest_role = role

                    if highest_role:
                        # Remove other XP roles
                        roles_to_remove = [
                            guild.get_role(int(role_id)) 
                            for role_id in xp_roles.keys() 
                            if int(role_id) != highest_role.id
                        ]
                        roles_to_remove = [r for r in roles_to_remove if r]
                        
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove, reason="XP role update")
                        
                        # Add highest qualified role if not present
                        if highest_role not in member.roles:
                            await member.add_roles(highest_role, reason="XP role update")
        except Exception as e:
            self.logger.error(f"Error in check_xp_roles: {e}")

    async def _check_role_hierarchy(self, interaction: discord.Interaction, role: discord.Role) -> bool:
        """Check if the bot and user have permission to manage the role"""
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I cannot manage this role as it is higher than my highest role.", ephemeral=True)
            return False
        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot manage this role as it is higher than your highest role.", ephemeral=True)
            return False
        return True

    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.command(name="xprole")
    @app_commands.describe(
        action="Whether to add, remove, or list XP roles",
        role="The role to manage (not needed for 'list')",
        xp_required="Amount of XP required for the role (only for 'add')"
    )
    @app_commands.default_permissions(manage_roles=True)
    async def xprole(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove", "list"],
        role: Optional[discord.Role] = None,
        xp_required: Optional[int] = None
    ):
        """Manage XP-based roles"""
        try:
            if not interaction.guild:
                await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
                return

            if action == "list":
                return await self._list_xp_roles(interaction)
            
            if not role:
                await interaction.response.send_message("❌ You must specify a role!", ephemeral=True)
                return

            # Check role hierarchy
            if not await self._check_role_hierarchy(interaction, role):
                return

            async with self.role_lock:  # Use lock for thread safety
                config = await self.init_data()
                guild_id = str(interaction.guild_id)
                
                if guild_id not in config["xp_roles"]:
                    config["xp_roles"][guild_id] = {}

                if action == "add":
                    if not xp_required:
                        await interaction.response.send_message("❌ You must specify the required XP!", ephemeral=True)
                        return
                    
                    if xp_required < 0:
                        await interaction.response.send_message("❌ XP requirement cannot be negative!", ephemeral=True)
                        return

                    # Check for role conflicts
                    for existing_role_id, existing_data in config["xp_roles"][guild_id].items():
                        if existing_data["xp_required"] == xp_required:
                            existing_role = interaction.guild.get_role(int(existing_role_id))
                            if existing_role:
                                await interaction.response.send_message(
                                    f"❌ There's already a role ({existing_role.mention}) with {xp_required} XP requirement!",
                                    ephemeral=True
                                )
                                return
                    
                    config["xp_roles"][guild_id][str(role.id)] = {
                        "xp_required": xp_required,
                        "name": role.name
                    }
                    await self.bot.data_manager.save_json("roles", self.roles_key, config)
                    await interaction.response.send_message(
                        f"✅ Added {role.mention} as an XP role (requires {xp_required:,} XP)",
                        ephemeral=True
                    )
                
                elif action == "remove":
                    if str(role.id) in config["xp_roles"][guild_id]:
                        del config["xp_roles"][guild_id][str(role.id)]
                        await self.bot.data_manager.save_json("roles", self.roles_key, config)
                        
                        # Remove the role from all members who have it
                        for member in interaction.guild.members:
                            if role in member.roles:
                                try:
                                    await member.remove_roles(role, reason="XP role removed from configuration")
                                except discord.HTTPException:
                                    continue
                        
                        await interaction.response.send_message(
                            f"✅ Removed {role.mention} from XP roles and removed it from all members",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ {role.mention} is not an XP role",
                            ephemeral=True
                        )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles. Please check my role permissions.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error in xprole command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing XP roles. Please try again later.",
                ephemeral=True
            )

    async def _list_xp_roles(self, interaction: discord.Interaction):
        """List all XP roles"""
        try:
            config = await self.init_data()
            guild_id = str(interaction.guild_id)
            
            if guild_id not in config["xp_roles"] or not config["xp_roles"][guild_id]:
                await interaction.response.send_message("No XP roles configured!", ephemeral=True)
                return

            embed = discord.Embed(
                title="XP Roles Configuration",
                color=discord.Color.blue()
            )

            # Sort roles by XP requirement
            sorted_roles = sorted(
                config["xp_roles"][guild_id].items(),
                key=lambda x: x[1]["xp_required"]
            )

            for role_id, role_data in sorted_roles:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    embed.add_field(
                        name=role.name,
                        value=f"Required XP: {role_data['xp_required']}",
                        inline=False
                    )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error in _list_xp_roles: {e}")
            await interaction.response.send_message("❌ An error occurred while listing XP roles", ephemeral=True)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @app_commands.command(name="persistentrole")
    @app_commands.describe(
        action="Whether to add, remove, or list persistent roles",
        role="The role to manage (not needed for 'list')"
    )
    @app_commands.default_permissions(manage_roles=True)
    async def persistentrole(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove", "list"],
        role: Optional[discord.Role] = None
    ):
        """Manage roles that persist through member leaves/joins"""
        try:
            if not interaction.guild:
                await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
                return

            if action == "list":
                return await self._list_persistent_roles(interaction)
            
            if not role:
                await interaction.response.send_message("❌ You must specify a role!", ephemeral=True)
                return

            # Check role hierarchy
            if not await self._check_role_hierarchy(interaction, role):
                return

            async with self.role_lock:  # Use lock for thread safety
                config = await self.init_data()
                guild_id = str(interaction.guild_id)
                
                if guild_id not in config.get("persistent_roles", {}):
                    config.setdefault("persistent_roles", {})[guild_id] = []

                if action == "add":
                    if role.managed:
                        await interaction.response.send_message(
                            "❌ Cannot make managed roles (like bot roles) persistent!",
                            ephemeral=True
                        )
                        return

                    if role.id not in config["persistent_roles"][guild_id]:
                        config["persistent_roles"][guild_id].append(role.id)
                        await self.bot.data_manager.save_json("roles", self.roles_key, config)
                        await interaction.response.send_message(
                            f"✅ Added {role.mention} as a persistent role. This role will be restored when members rejoin.",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ {role.mention} is already a persistent role",
                            ephemeral=True
                        )
                
                elif action == "remove":
                    if role.id in config["persistent_roles"][guild_id]:
                        config["persistent_roles"][guild_id].remove(role.id)
                        
                        # Clean up stored roles for this role
                        if "stored_roles" in config and guild_id in config["stored_roles"]:
                            for user_id in config["stored_roles"][guild_id]:
                                if role.id in config["stored_roles"][guild_id][user_id]:
                                    config["stored_roles"][guild_id][user_id].remove(role.id)
                        
                        await self.bot.data_manager.save_json("roles", self.roles_key, config)
                        await interaction.response.send_message(
                            f"✅ Removed {role.mention} from persistent roles and cleaned up stored role data",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ {role.mention} is not a persistent role",
                            ephemeral=True
                        )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles. Please check my role permissions.",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error in persistentrole command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing persistent roles. Please try again later.",
                ephemeral=True
            )

    async def _list_persistent_roles(self, interaction: discord.Interaction):
        """List all persistent roles"""
        try:
            config = await self.init_data()
            guild_id = str(interaction.guild_id)
            
            if guild_id not in config.get("persistent_roles", {}) or not config["persistent_roles"][guild_id]:
                await interaction.response.send_message("No persistent roles configured!", ephemeral=True)
                return

            embed = discord.Embed(
                title="Persistent Roles",
                description="These roles will be restored when members rejoin",
                color=discord.Color.blue()
            )

            roles_list = []
            for role_id in config["persistent_roles"][guild_id]:
                role = interaction.guild.get_role(role_id)
                if role:
                    roles_list.append(role.mention)

            embed.add_field(
                name="Roles",
                value="\n".join(roles_list) if roles_list else "No persistent roles found",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error in _list_persistent_roles: {e}")
            await interaction.response.send_message("❌ An error occurred while listing persistent roles", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Store roles when a member leaves"""
        try:
            config = await self.init_data()
            guild_id = str(member.guild.id)
            
            if guild_id not in config.get("persistent_roles", {}):
                return

            # Get the member's persistent roles
            persistent_roles = [
                role.id for role in member.roles
                if role.id in config["persistent_roles"][guild_id]
            ]

            if persistent_roles:
                if "stored_roles" not in config:
                    config["stored_roles"] = {}
                if guild_id not in config["stored_roles"]:
                    config["stored_roles"][guild_id] = {}
                
                config["stored_roles"][guild_id][str(member.id)] = persistent_roles
                await self.bot.data_manager.save_json("roles", self.roles_key, config)
        except Exception as e:
            self.logger.error(f"Error in on_member_remove event: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Restore roles when a member rejoins"""
        try:
            config = await self.init_data()
            guild_id = str(member.guild.id)
            
            if (
                "stored_roles" in config
                and guild_id in config["stored_roles"]
                and str(member.id) in config["stored_roles"][guild_id]
            ):
                stored_roles = config["stored_roles"][guild_id][str(member.id)]
                roles_to_add = []
                
                for role_id in stored_roles:
                    role = member.guild.get_role(role_id)
                    if role and role.id in config.get("persistent_roles", {}).get(guild_id, []):
                        roles_to_add.append(role)

                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason="Restoring persistent roles")
                    
                # Clean up stored roles
                del config["stored_roles"][guild_id][str(member.id)]
                await self.bot.data_manager.save_json("roles", self.roles_key, config)
        except Exception as e:
            self.logger.error(f"Error in on_member_join event: {e}")

async def setup(bot):
    await bot.add_cog(RoleManager(bot))

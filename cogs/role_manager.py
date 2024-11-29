import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import json
import asyncio

class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_key = "roles_config"
        self.xp_key = "user_xp"
        # Don't start the task here, it will be started in cog_load
        self.check_xp_roles = tasks.loop(minutes=5.0)(self._check_xp_roles)

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self.init_data()
        self.check_xp_roles.start()

    def cog_unload(self):
        """Called when the cog is unloaded"""
        self.check_xp_roles.cancel()

    async def _check_xp_roles(self):
        """Check and update roles based on XP periodically"""
        try:
            xp_data = await self.bot.data_manager.load_json("xp", self.xp_key)
            roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
            
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
                        
                    await self.update_member_roles(member, user_xp, xp_roles)
                    
        except Exception as e:
            self.bot.logger.error(f"Error in XP role check task: {e}")

    async def init_data(self):
        """Initialize role configuration data"""
        if not await self.bot.data_manager.exists("roles", "key = ?", self.roles_key):
            await self.bot.data_manager.save_json("roles", self.roles_key, {
                "reaction_roles": {},  # message_id -> {emoji: role_id}
                "role_groups": {},     # group_name -> [role_ids]
                "xp_roles": {},        # guild_id -> {role_id: required_xp}
                "role_paths": {},      # role_id -> required_role_id
                "temp_roles": {},      # role_id -> duration
                "exclusive_groups": {}, # group_name -> [role_ids] (mutually exclusive roles)
                "role_hierarchy": {},  # guild_id -> {tier: [role_ids]}
                "role_analytics": {},  # guild_id -> {role_id: {assignments: int, removals: int, active: int}}
                "settings": {
                    "xp_per_message": 1,
                    "xp_cooldown": 60,  # seconds
                    "level_multiplier": 1.5
                }
            })
        
        if not await self.bot.data_manager.exists("xp", "key = ?", self.xp_key):
            await self.bot.data_manager.save_json("xp", self.xp_key, {})  # guild_id -> user_id -> xp

    async def get_user_xp(self, guild_id: str, user_id: str) -> int:
        """Get user's XP in a guild"""
        xp_data = await self.bot.data_manager.load_json("xp", self.xp_key)
        return xp_data.get(str(guild_id), {}).get(str(user_id), 0)

    async def add_xp(self, guild_id: str, user_id: str, amount: int):
        """Add XP to a user and check for role upgrades"""
        xp_data = await self.bot.data_manager.load_json("xp", self.xp_key)
        if str(guild_id) not in xp_data:
            xp_data[str(guild_id)] = {}
        
        user_data = xp_data[str(guild_id)]
        current_xp = user_data.get(str(user_id), 0)
        user_data[str(user_id)] = current_xp + amount
        
        await self.bot.data_manager.save_json("xp", self.xp_key, xp_data)
        await self.check_user_roles(guild_id, user_id)

    async def check_user_roles(self, guild_id: str, user_id: str):
        """Check and update a user's roles based on XP"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        xp_roles = roles_config.get("xp_roles", {}).get(str(guild_id), {})
        if not xp_roles:
            return
            
        guild = self.bot.get_guild(int(guild_id))
        member = guild.get_member(int(user_id))
        if not member:
            return
            
        user_xp = await self.get_user_xp(guild_id, user_id)
        
        # Sort roles by XP requirement
        sorted_roles = sorted(
            xp_roles.items(),
            key=lambda x: int(x[1])
        )
        
        # Find highest eligible role
        highest_role = None
        for role_id, required_xp in sorted_roles:
            if user_xp >= int(required_xp):
                highest_role = role_id
            else:
                break
        
        if highest_role:
            # Remove other XP roles
            for role_id in xp_roles.keys():
                role = guild.get_role(int(role_id))
                if role and role in member.roles and role_id != highest_role:
                    await member.remove_roles(role)
            
            # Add highest eligible role
            role = guild.get_role(int(highest_role))
            if role and role not in member.roles:
                await member.add_roles(role)

    @app_commands.command(
        name="setreactionrole",
        description="Create a reaction role message"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_reaction_role(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        role: discord.Role,
        emoji: str
    ):
        """Create a reaction role message"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction(emoji)
        
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        if str(msg.id) not in roles_config["reaction_roles"]:
            roles_config["reaction_roles"][str(msg.id)] = {}
        
        roles_config["reaction_roles"][str(msg.id)][emoji] = role.id
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        await interaction.response.send_message(
            "✅ Reaction role created!",
            ephemeral=True
        )

    @app_commands.command(
        name="setxprole",
        description="Set an XP-based role"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_xp_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        required_xp: int,
        required_role: Optional[discord.Role] = None
    ):
        """Set an XP-based role with requirements"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        guild_id = str(interaction.guild_id)
        
        if "xp_roles" not in roles_config:
            roles_config["xp_roles"] = {}
        if guild_id not in roles_config["xp_roles"]:
            roles_config["xp_roles"][guild_id] = {}
        
        roles_config["xp_roles"][guild_id][str(role.id)] = required_xp
        
        if required_role:
            if "role_paths" not in roles_config:
                roles_config["role_paths"] = {}
            roles_config["role_paths"][str(role.id)] = required_role.id
        
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        response = f"✅ Set {role.mention} as XP role (Required XP: {required_xp})"
        if required_role:
            response += f"\nRequires: {required_role.mention}"
        
        await interaction.response.send_message(
            response,
            ephemeral=True
        )

    @app_commands.command(
        name="settemprole",
        description="Set a temporary role duration"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_temp_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        duration: int  # hours
    ):
        """Set a role to be temporary"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        
        if "temp_roles" not in roles_config:
            roles_config["temp_roles"] = {}
        
        roles_config["temp_roles"][str(role.id)] = duration * 3600  # convert to seconds
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        await interaction.response.send_message(
            f"✅ Set {role.mention} as temporary role ({duration} hours)",
            ephemeral=True
        )

    @app_commands.command(
        name="setexclusivegroup",
        description="Create a group of mutually exclusive roles"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_exclusive_group(
        self,
        interaction: discord.Interaction,
        group_name: str,
        roles: str  # Comma-separated role mentions or IDs
    ):
        """Create a group of mutually exclusive roles"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        
        if "exclusive_groups" not in roles_config:
            roles_config["exclusive_groups"] = {}
        
        # Parse roles from the input string
        role_ids = []
        for role_str in roles.split(','):
            role_str = role_str.strip()
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_id = role_str[3:-1]
            else:
                role_id = role_str
            
            try:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    role_ids.append(str(role.id))
            except ValueError:
                continue
        
        if not role_ids:
            await interaction.response.send_message(
                "❌ No valid roles provided",
                ephemeral=True
            )
            return
        
        roles_config["exclusive_groups"][group_name] = role_ids
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        role_mentions = [f"<@&{role_id}>" for role_id in role_ids]
        await interaction.response.send_message(
            f"✅ Created exclusive group '{group_name}' with roles: {', '.join(role_mentions)}",
            ephemeral=True
        )

    async def handle_exclusive_roles(self, member: discord.Member, new_role: discord.Role):
        """Handle mutually exclusive roles when adding a new role"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        
        # Find groups containing the new role
        for group_name, role_ids in roles_config.get("exclusive_groups", {}).items():
            if str(new_role.id) in role_ids:
                # Remove other roles in the same group
                roles_to_remove = []
                for role_id in role_ids:
                    if role_id != str(new_role.id):
                        role = member.guild.get_role(int(role_id))
                        if role and role in member.roles:
                            roles_to_remove.append(role)
                
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove)
                    
                    # Trigger auto-role system
                    auto_roles = self.bot.get_cog('AutoRoles')
                    if auto_roles:
                        for role in roles_to_remove:
                            config = auto_roles.get_auto_role_config(member.guild.id)
                            if str(role.id) in config.get('auto_remove_roles', {}):
                                roles_to_remove = config['auto_remove_roles'][str(role.id)]
                                roles = [discord.Object(id=int(r)) for r in roles_to_remove]
                                try:
                                    await member.remove_roles(*roles, reason="Auto role removal")
                                except discord.Forbidden:
                                    pass

    @app_commands.command(
        name="sethierarchy",
        description="Set up role hierarchy tiers"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_hierarchy(
        self,
        interaction: discord.Interaction,
        tier: int,
        roles: str  # Comma-separated role mentions or IDs
    ):
        """Set up role hierarchy tiers"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        guild_id = str(interaction.guild_id)
        
        if "role_hierarchy" not in roles_config:
            roles_config["role_hierarchy"] = {}
        if guild_id not in roles_config["role_hierarchy"]:
            roles_config["role_hierarchy"][guild_id] = {}
        
        # Parse roles
        role_ids = []
        for role_str in roles.split(','):
            role_str = role_str.strip()
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_id = role_str[3:-1]
            else:
                role_id = role_str
            
            try:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    role_ids.append(str(role.id))
            except ValueError:
                continue
        
        if not role_ids:
            await interaction.response.send_message(
                "❌ No valid roles provided",
                ephemeral=True
            )
            return
        
        roles_config["role_hierarchy"][guild_id][str(tier)] = role_ids
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        role_mentions = [f"<@&{role_id}>" for role_id in role_ids]
        await interaction.response.send_message(
            f"✅ Set tier {tier} with roles: {', '.join(role_mentions)}",
            ephemeral=True
        )

    async def check_hierarchy_requirements(
        self,
        member: discord.Member,
        role: discord.Role
    ) -> tuple[bool, str]:
        """Check if a member meets hierarchy requirements for a role"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        guild_id = str(member.guild.id)
        
        if guild_id not in roles_config.get("role_hierarchy", {}):
            return True, ""
        
        # Find role's tier
        role_tier = None
        hierarchy = roles_config["role_hierarchy"][guild_id]
        for tier, role_ids in hierarchy.items():
            if str(role.id) in role_ids:
                role_tier = int(tier)
                break
        
        if role_tier is None:
            return True, ""
        
        # Check if user has roles from previous tier
        if role_tier > 0:
            prev_tier = str(role_tier - 1)
            if prev_tier in hierarchy:
                has_prev_tier = any(
                    str(r.id) in hierarchy[prev_tier] for r in member.roles
                )
                if not has_prev_tier:
                    prev_roles = [
                        member.guild.get_role(int(r_id))
                        for r_id in hierarchy[prev_tier]
                    ]
                    prev_roles = [r.name for r in prev_roles if r]
                    return False, f"You need a role from tier {prev_tier} first: {', '.join(prev_roles)}"
        
        return True, ""

    @app_commands.command(
        name="roleanalytics",
        description="View role assignment analytics"
    )
    @app_commands.default_permissions(administrator=True)
    async def role_analytics(
        self,
        interaction: discord.Interaction,
        role: Optional[discord.Role] = None
    ):
        """View role assignment analytics"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        guild_id = str(interaction.guild_id)
        
        if "role_analytics" not in roles_config:
            roles_config["role_analytics"] = {}
        if guild_id not in roles_config["role_analytics"]:
            roles_config["role_analytics"][guild_id] = {}
        
        analytics = roles_config["role_analytics"][guild_id]
        
        embed = discord.Embed(
            title="Role Analytics",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if role:
            # Single role analytics
            role_stats = analytics.get(str(role.id), {
                "assignments": 0,
                "removals": 0,
                "active": len([m for m in interaction.guild.members if role in m.roles])
            })
            
            embed.add_field(
                name=role.name,
                value=f"Assignments: {role_stats['assignments']}\n"
                      f"Removals: {role_stats['removals']}\n"
                      f"Currently Active: {role_stats['active']}"
            )
        else:
            # Top 10 most active roles
            sorted_roles = sorted(
                analytics.items(),
                key=lambda x: x[1].get('active', 0),
                reverse=True
            )[:10]
            
            for role_id, stats in sorted_roles:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    embed.add_field(
                        name=role.name,
                        value=f"Assignments: {stats.get('assignments', 0)}\n"
                              f"Removals: {stats.get('removals', 0)}\n"
                              f"Currently Active: {stats.get('active', 0)}",
                        inline=True
                    )
        
        await interaction.response.send_message(embed=embed)

    async def update_role_analytics(
        self,
        guild_id: int,
        role_id: int,
        action: str
    ):
        """Update role analytics"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        guild_id = str(guild_id)
        role_id = str(role_id)
        
        if "role_analytics" not in roles_config:
            roles_config["role_analytics"] = {}
        if guild_id not in roles_config["role_analytics"]:
            roles_config["role_analytics"][guild_id] = {}
        if role_id not in roles_config["role_analytics"][guild_id]:
            roles_config["role_analytics"][guild_id][role_id] = {
                "assignments": 0,
                "removals": 0,
                "active": 0
            }
        
        stats = roles_config["role_analytics"][guild_id][role_id]
        if action == "add":
            stats["assignments"] += 1
            stats["active"] += 1
        elif action == "remove":
            stats["removals"] += 1
            stats["active"] = max(0, stats["active"] - 1)
        
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)

    @app_commands.command(
        name="xpconfig",
        description="Configure XP settings"
    )
    @app_commands.default_permissions(administrator=True)
    async def xp_config(
        self,
        interaction: discord.Interaction,
        xp_per_message: Optional[int] = None,
        xp_cooldown: Optional[int] = None,
        level_multiplier: Optional[float] = None
    ):
        """Configure XP settings"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        
        if xp_per_message is not None:
            roles_config["settings"]["xp_per_message"] = xp_per_message
        if xp_cooldown is not None:
            roles_config["settings"]["xp_cooldown"] = xp_cooldown
        if level_multiplier is not None:
            roles_config["settings"]["level_multiplier"] = level_multiplier
        
        await self.bot.data_manager.save_json("roles", self.roles_key, roles_config)
        
        await interaction.response.send_message(
            "✅ XP settings updated!",
            ephemeral=True
        )

    @app_commands.command(
        name="checkxp",
        description="Check your or another user's XP"
    )
    async def check_xp(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        """Check XP progress"""
        user = user or interaction.user
        xp = await self.get_user_xp(str(interaction.guild_id), str(user.id))
        
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        xp_roles = roles_config.get("xp_roles", {}).get(
            str(interaction.guild_id),
            {}
        )
        
        embed = discord.Embed(
            title=f"XP Progress - {user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current XP", value=str(xp))
        
        if xp_roles:
            # Show next role target
            sorted_roles = sorted(
                xp_roles.items(),
                key=lambda x: int(x[1])
            )
            next_role = None
            for role_id, required_xp in sorted_roles:
                if int(required_xp) > xp:
                    next_role = (role_id, required_xp)
                    break
            
            if next_role:
                role = interaction.guild.get_role(int(next_role[0]))
                if role:
                    embed.add_field(
                        name="Next Role",
                        value=f"{role.mention} ({next_role[1] - xp} XP needed)"
                    )
        
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle XP gain from messages"""
        if message.author.bot or not message.guild:
            return
            
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        settings = roles_config["settings"]
        
        # Check cooldown
        xp_data = await self.bot.data_manager.load_json("xp", self.xp_key)
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        
        if guild_id in xp_data and user_id in xp_data[guild_id]:
            last_xp = xp_data[guild_id].get(f"{user_id}_last", 0)
            if datetime.utcnow().timestamp() - last_xp < settings["xp_cooldown"]:
                return
        
        # Add XP
        await self.add_xp(
            guild_id,
            user_id,
            settings["xp_per_message"]
        )
        
        # Update last XP time
        if guild_id not in xp_data:
            xp_data[guild_id] = {}
        xp_data[guild_id][f"{user_id}_last"] = datetime.utcnow().timestamp()
        await self.bot.data_manager.save_json("xp", self.xp_key, xp_data)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Track role changes for analytics"""
        if before.roles == after.roles:
            return
        
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)
        
        for role in added_roles:
            await self.update_role_analytics(after.guild.id, role.id, "add")
        
        for role in removed_roles:
            await self.update_role_analytics(after.guild.id, role.id, "remove")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role addition"""
        if payload.user_id == self.bot.user.id:
            return
            
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        message_roles = roles_config["reaction_roles"].get(str(payload.message_id))
        
        if not message_roles:
            return
            
        role_id = message_roles.get(str(payload.emoji))
        if not role_id:
            return
            
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(int(role_id))
        member = guild.get_member(payload.user_id)
        
        if role and member:
            # Check role path requirements
            if str(role_id) in roles_config.get("role_paths", {}):
                required_role_id = roles_config["role_paths"][str(role_id)]
                required_role = guild.get_role(int(required_role_id))
                if required_role not in member.roles:
                    await payload.member.send(
                        f"You need the {required_role.name} role first!"
                    )
                    return
            
            # Check hierarchy requirements
            can_have_role, reason = await self.check_hierarchy_requirements(member, role)
            if not can_have_role:
                await payload.member.send(reason)
                return
            
            # Handle exclusive roles before adding the new role
            await self.handle_exclusive_roles(member, role)
            
            await member.add_roles(role)
            await self.update_role_analytics(guild.id, role.id, "add")
            
            # Trigger auto-role system
            auto_roles = self.bot.get_cog('AutoRoles')
            if auto_roles:
                config = auto_roles.get_auto_role_config(guild.id)
                if str(role.id) in config.get('auto_roles', {}):
                    roles_to_add = config['auto_roles'][str(role.id)]
                    roles = [discord.Object(id=int(r)) for r in roles_to_add]
                    try:
                        await member.add_roles(*roles, reason="Auto role addition")
                    except discord.Forbidden:
                        pass
            
            # Handle temporary roles
            if str(role_id) in roles_config.get("temp_roles", {}):
                duration = roles_config["temp_roles"][str(role_id)]
                await asyncio.sleep(duration)
                if role in member.roles:
                    await member.remove_roles(role)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role removal"""
        roles_config = await self.bot.data_manager.load_json("roles", self.roles_key)
        message_roles = roles_config["reaction_roles"].get(str(payload.message_id))
        
        if not message_roles:
            return
            
        role_id = message_roles.get(str(payload.emoji))
        if not role_id:
            return
            
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(int(role_id))
        member = guild.get_member(payload.user_id)
        
        if role and member and role in member.roles:
            await member.remove_roles(role)
            await self.update_role_analytics(guild.id, role.id, "remove")

    async def _cleanup_warnings(self):
        """Background task to clean up expired warnings"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                infractions = await self.bot.data_manager.load_json("infractions", "infractions_key")
                current_time = datetime.utcnow()
                modified = False

                for guild_id, guild_infractions in list(infractions.items()):
                    for user_id, user_infractions in list(guild_infractions.items()):
                        active_infractions = [
                            inf for inf in user_infractions 
                            if not inf.get("expires_at") or 
                            datetime.fromisoformat(inf["expires_at"]) > current_time
                        ]
                        if len(active_infractions) != len(user_infractions):
                            guild_infractions[user_id] = active_infractions
                            modified = True

                if modified:
                    await self.bot.data_manager.save_json("infractions", "infractions_key", infractions)
                    self.logger.info("Cleaned up expired warnings")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in warning cleanup task: {e}")

            try:
                await asyncio.sleep(3600)  # Check every hour
            except asyncio.CancelledError:
                break

async def setup(bot):
    await bot.add_cog(RoleManager(bot))

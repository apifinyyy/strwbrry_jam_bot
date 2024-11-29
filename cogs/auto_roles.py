import discord
from discord import app_commands
from discord.ext import commands

class AutoRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_auto_role_config(self, guild_id: int) -> dict:
        """Get auto role configuration for a guild."""
        config = self.bot.config_manager.get_guild_config(guild_id)
        return config.get('auto_roles', {
            'role_messages': {},
            'auto_roles': {},
            'auto_remove_roles': {}
        })

    def save_auto_role_config(self, guild_id: int, auto_role_config: dict):
        """Save auto role configuration for a guild."""
        config = self.bot.config_manager.get_guild_config(guild_id)
        config['auto_roles'] = auto_role_config
        self.bot.config_manager.set_guild_config(guild_id, config)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        config = self.get_auto_role_config(before.guild.id)
        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        # Handle role messages
        for role in added_roles:
            role_id = str(role.id)
            if role_id in config.get('role_messages', {}):
                message_config = config['role_messages'][role_id]
                channel = after.guild.get_channel(int(message_config['channel_id']))
                if channel:
                    await channel.send(
                        message_config['message'].format(user=after.mention, role=role.name)
                    )

        # Handle auto roles
        for role in added_roles:
            role_id = str(role.id)
            if role_id in config.get('auto_roles', {}):
                roles_to_add = config['auto_roles'][role_id]
                roles = [discord.Object(id=int(r)) for r in roles_to_add]
                try:
                    await after.add_roles(*roles, reason="Auto role addition")
                except discord.Forbidden:
                    pass  # Bot doesn't have permission

        # Handle auto remove roles
        for role in removed_roles:
            role_id = str(role.id)
            if role_id in config.get('auto_remove_roles', {}):
                roles_to_remove = config['auto_remove_roles'][role_id]
                roles = [discord.Object(id=int(r)) for r in roles_to_remove]
                try:
                    await after.remove_roles(*roles, reason="Auto role removal")
                except discord.Forbidden:
                    pass  # Bot doesn't have permission

    @app_commands.command(name="setrole_message", description="Set a message to be sent when a role is given")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_role_message(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        channel: discord.TextChannel,
        message: str
    ):
        config = self.get_auto_role_config(interaction.guild.id)
        if 'role_messages' not in config:
            config['role_messages'] = {}
        config['role_messages'][str(role.id)] = {
            'channel_id': str(channel.id),
            'message': message
        }
        self.save_auto_role_config(interaction.guild.id, config)
        await interaction.response.send_message(
            f"Message will be sent in {channel.mention} when {role.name} is given to a user"
        )

    @app_commands.command(name="setauto_role", description="Set a role to be automatically given when another role is added")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_auto_role(
        self,
        interaction: discord.Interaction,
        trigger_role: discord.Role,
        auto_role: discord.Role
    ):
        config = self.get_auto_role_config(interaction.guild.id)
        if 'auto_roles' not in config:
            config['auto_roles'] = {}
        trigger_id = str(trigger_role.id)
        if trigger_id not in config['auto_roles']:
            config['auto_roles'][trigger_id] = []
        auto_role_id = str(auto_role.id)
        if auto_role_id not in config['auto_roles'][trigger_id]:
            config['auto_roles'][trigger_id].append(auto_role_id)
            self.save_auto_role_config(interaction.guild.id, config)
            await interaction.response.send_message(
                f"{auto_role.name} will be automatically given when {trigger_role.name} is added"
            )
        else:
            await interaction.response.send_message(
                f"{auto_role.name} is already set to be given with {trigger_role.name}",
                ephemeral=True
            )

    @app_commands.command(name="setauto_remove", description="Set a role to be automatically removed when another role is removed")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_auto_remove(
        self,
        interaction: discord.Interaction,
        trigger_role: discord.Role,
        remove_role: discord.Role
    ):
        config = self.get_auto_role_config(interaction.guild.id)
        if 'auto_remove_roles' not in config:
            config['auto_remove_roles'] = {}
        trigger_id = str(trigger_role.id)
        if trigger_id not in config['auto_remove_roles']:
            config['auto_remove_roles'][trigger_id] = []
        remove_role_id = str(remove_role.id)
        if remove_role_id not in config['auto_remove_roles'][trigger_id]:
            config['auto_remove_roles'][trigger_id].append(remove_role_id)
            self.save_auto_role_config(interaction.guild.id, config)
            await interaction.response.send_message(
                f"{remove_role.name} will be automatically removed when {trigger_role.name} is removed"
            )
        else:
            await interaction.response.send_message(
                f"{remove_role.name} is already set to be removed with {trigger_role.name}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(AutoRoles(bot))

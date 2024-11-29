import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Dict, Optional
import json

class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.command_history: Dict[str, Dict[str, str]] = {}
        self.data_type = "debug"

    def _get_debug_data(self, guild_id: int) -> dict:
        """Get debug data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {"command_history": {}}
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
        return data

    def _save_debug_data(self, guild_id: int, data: dict) -> None:
        """Save debug data for a specific guild."""
        self.bot.data_manager.save_data(guild_id, self.data_type, data)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        """Log command usage when a command completes successfully."""
        if not interaction.guild:
            return

        # Get debug data
        debug_data = self._get_debug_data(interaction.guild.id)
        command_history = debug_data.get("command_history", {})

        # Create command entry
        command_entry = {
            "command": command.name,
            "user": str(interaction.user),
            "user_id": str(interaction.user.id),
            "channel": str(interaction.channel),
            "channel_id": str(interaction.channel_id),
            "timestamp": datetime.utcnow().isoformat(),
            "options": str(interaction.data.get("options", [])),
            "success": True
        }

        # Update command history
        command_key = f"{interaction.user.id}_{command.name}"
        command_history[command_key] = command_entry

        # Keep only the last 100 commands per guild
        if len(command_history) > 100:
            oldest_key = min(command_history.keys(), key=lambda k: command_history[k]["timestamp"])
            del command_history[oldest_key]

        # Save updated data
        debug_data["command_history"] = command_history
        self._save_debug_data(interaction.guild.id, debug_data)

    @app_commands.command(name="lastcommand", description="Show the last command usage for a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def last_command(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        command_name: Optional[str] = None
    ):
        """Show the last command usage for a user."""
        try:
            debug_data = self._get_debug_data(interaction.guild.id)
            command_history = debug_data.get("command_history", {})

            if not command_history:
                await interaction.response.send_message(
                    "❌ No command history found.",
                    ephemeral=True
                )
                return

            # Filter command history
            filtered_history = command_history
            if user:
                filtered_history = {
                    k: v for k, v in command_history.items()
                    if v["user_id"] == str(user.id)
                }
            if command_name:
                filtered_history = {
                    k: v for k, v in filtered_history.items()
                    if v["command"] == command_name
                }

            if not filtered_history:
                await interaction.response.send_message(
                    f"❌ No matching command history found{' for ' + user.mention if user else ''}.",
                    ephemeral=True
                )
                return

            # Get the most recent command
            latest_command = max(filtered_history.values(), key=lambda x: x["timestamp"])
            
            # Format timestamp
            timestamp = datetime.fromisoformat(latest_command["timestamp"])
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

            # Create embed
            embed = discord.Embed(
                title="🔍 Last Command Usage",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Command",
                value=f"`/{latest_command['command']}`",
                inline=True
            )
            embed.add_field(
                name="User",
                value=latest_command["user"],
                inline=True
            )
            embed.add_field(
                name="Channel",
                value=latest_command["channel"],
                inline=True
            )
            embed.add_field(
                name="Options",
                value=latest_command["options"] or "None",
                inline=False
            )
            embed.add_field(
                name="Timestamp",
                value=time_str,
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="commandstats", description="Show command usage statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def command_stats(self, interaction: discord.Interaction):
        """Show command usage statistics."""
        try:
            debug_data = self._get_debug_data(interaction.guild.id)
            command_history = debug_data.get("command_history", {})

            if not command_history:
                await interaction.response.send_message(
                    "❌ No command history found.",
                    ephemeral=True
                )
                return

            # Calculate statistics
            command_counts = {}
            user_counts = {}
            for entry in command_history.values():
                # Command usage count
                cmd = entry["command"]
                command_counts[cmd] = command_counts.get(cmd, 0) + 1
                
                # User usage count
                user = entry["user"]
                user_counts[user] = user_counts.get(user, 0) + 1

            # Sort by usage
            top_commands = sorted(command_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            # Create embed
            embed = discord.Embed(
                title="📊 Command Usage Statistics",
                color=discord.Color.blue()
            )

            # Add top commands
            cmd_str = "\n".join([f"`/{cmd}`: {count} uses" for cmd, count in top_commands])
            embed.add_field(
                name="Top Commands",
                value=cmd_str or "No data",
                inline=False
            )

            # Add top users
            user_str = "\n".join([f"{user}: {count} commands" for user, count in top_users])
            embed.add_field(
                name="Top Users",
                value=user_str or "No data",
                inline=False
            )

            # Add total statistics
            embed.add_field(
                name="Total Statistics",
                value=f"Total Commands: {len(command_history)}\n"
                      f"Unique Commands: {len(command_counts)}\n"
                      f"Unique Users: {len(user_counts)}",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Debug(bot))

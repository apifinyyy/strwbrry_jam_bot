import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal, Union, List
import logging
import re
from datetime import datetime, timedelta
import asyncio
from discord.ui import View, Select, Modal, TextInput
import math

class CommandModal(discord.ui.Modal):
    def __init__(self, title: str, fields: List[dict]):
        super().__init__(title=title)
        for field in fields:
            self.add_item(
                discord.ui.TextInput(
                    label=field["label"],
                    placeholder=field.get("placeholder", ""),
                    required=field.get("required", True),
                    min_length=field.get("min_length", 1),
                    max_length=field.get("max_length", 4000)
                )
            )

class CommandSelect(discord.ui.Select):
    def __init__(self, category: str, options: List[dict]):
        super().__init__(
            placeholder=f"Select {category} Command",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=opt["name"],
                    description=opt["description"]
                ) for opt in options
            ]
        )
        self.category = category
        self.command_info = {opt["name"]: opt for opt in options}

    async def callback(self, interaction: discord.Interaction):
        command = self.values[0]
        cmd_info = self.command_info[command]

        if command == "warn":
            modal = CommandModal("Warn User", [
                {"label": "User", "placeholder": "Enter user ID or mention"},
                {"label": "Reason", "placeholder": "Enter reason for warning", "max_length": 1000},
                {"label": "Severity", "placeholder": "1, 2, or 3", "max_length": 1}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        await interaction.response.send_message(f"❌ User with ID {user_id} not found in this server!", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}. Make sure they are in the server!", ephemeral=True)
                        return

                    reason = modal.children[1].value
                    try:
                        severity = int(modal.children[2].value)
                        if severity not in [1, 2, 3]:
                            await interaction.response.send_message("❌ Severity must be 1, 2, or 3!", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Severity must be a number (1, 2, or 3)!", ephemeral=True)
                        return

                    mod_cog = interaction.client.get_cog("Moderation")
                    if not mod_cog:
                        await interaction.response.send_message("❌ Moderation module not loaded!", ephemeral=True)
                        return

                    try:
                        await mod_cog.warn.callback(mod_cog, interaction, user, reason, severity)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "mute":
            modal = CommandModal("Timeout User", [
                {"label": "User", "placeholder": "Enter user ID or mention"},
                {"label": "Duration", "placeholder": "Duration in minutes (1-43200)"},
                {"label": "Reason", "placeholder": "Enter reason for timeout", "max_length": 1000}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        await interaction.response.send_message(f"❌ User with ID {user_id} not found in this server!", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}. Make sure they are in the server!", ephemeral=True)
                        return

                    try:
                        duration = int(modal.children[1].value)
                        if duration < 1 or duration > 43200:  # 43200 minutes = 30 days (Discord's limit)
                            await interaction.response.send_message("❌ Duration must be between 1 and 43200 minutes!", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Duration must be a number!", ephemeral=True)
                        return

                    reason = modal.children[2].value or None

                    mod_cog = interaction.client.get_cog("Moderation")
                    if not mod_cog:
                        await interaction.response.send_message("❌ Moderation module not loaded!", ephemeral=True)
                        return

                    try:
                        await mod_cog.mute.callback(mod_cog, interaction, user, duration, reason)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "kick":
            modal = CommandModal("Kick User", [
                {"label": "User", "placeholder": "Enter user ID or mention"},
                {"label": "Reason", "placeholder": "Enter reason for kick", "max_length": 1000}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        await interaction.response.send_message(f"❌ User with ID {user_id} not found in this server!", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}. Make sure they are in the server!", ephemeral=True)
                        return

                    reason = modal.children[1].value

                    # Check permissions
                    if not interaction.user.guild_permissions.kick_members:
                        await interaction.response.send_message("❌ You don't have permission to kick members!", ephemeral=True)
                        return

                    if not interaction.guild.me.guild_permissions.kick_members:
                        await interaction.response.send_message("❌ I don't have permission to kick members!", ephemeral=True)
                        return

                    # Perform the kick
                    try:
                        await user.kick(reason=reason)
                        
                        # Create embed response
                        embed = discord.Embed(
                            title="User Kicked",
                            description=f"{user.mention} has been kicked.",
                            color=discord.Color.red()
                        )
                        if reason:
                            embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Moderator", value=interaction.user.mention)
                        
                        await interaction.response.send_message(embed=embed)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to kick this user!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "ban":
            modal = CommandModal("Ban User", [
                {"label": "User", "placeholder": "Enter user ID or mention"},
                {"label": "Reason", "placeholder": "Enter reason for ban", "max_length": 1000},
                {"label": "Delete Days", "placeholder": "Number of days of messages to delete (0-7)", "max_length": 1}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        # For bans, we can also try to get the user object if they're not in the server
                        try:
                            user = await interaction.client.fetch_user(int(user_id))
                        except:
                            await interaction.response.send_message(f"❌ User with ID {user_id} not found!", ephemeral=True)
                            return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}!", ephemeral=True)
                        return

                    reason = modal.children[1].value
                    try:
                        delete_days = int(modal.children[2].value)
                        if delete_days < 0 or delete_days > 7:
                            await interaction.response.send_message("❌ Delete days must be between 0 and 7!", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Delete days must be a number between 0 and 7!", ephemeral=True)
                        return

                    # Check permissions
                    if not interaction.user.guild_permissions.ban_members:
                        await interaction.response.send_message("❌ You don't have permission to ban members!", ephemeral=True)
                        return

                    if not interaction.guild.me.guild_permissions.ban_members:
                        await interaction.response.send_message("❌ I don't have permission to ban members!", ephemeral=True)
                        return

                    # Perform the ban
                    try:
                        await interaction.guild.ban(user, reason=reason, delete_message_days=delete_days)
                        
                        # Create embed response
                        embed = discord.Embed(
                            title="User Banned",
                            description=f"{user.mention} has been banned.",
                            color=discord.Color.red()
                        )
                        if reason:
                            embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Message Deletion", value=f"{delete_days} days")
                        embed.add_field(name="Moderator", value=interaction.user.mention)
                        
                        await interaction.response.send_message(embed=embed)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to ban this user!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "clean":
            modal = CommandModal("Clean Messages", [
                {"label": "Amount", "placeholder": "Number of messages to delete (1-100)"},
                {"label": "User", "placeholder": "Optional: Only delete messages from this user", "required": False},
                {"label": "Contains", "placeholder": "Optional: Only delete messages containing this text", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    try:
                        amount = int(modal.children[0].value)
                        if amount < 1 or amount > 100:
                            await interaction.response.send_message("❌ Amount must be between 1 and 100!", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Amount must be a number!", ephemeral=True)
                        return

                    user = None
                    if modal.children[1].value:
                        user_input = modal.children[1].value
                        user_id = ''.join(filter(str.isdigit, user_input))
                        try:
                            user = interaction.guild.get_member(int(user_id))
                            if user is None:
                                user = await interaction.guild.fetch_member(int(user_id))
                        except:
                            await interaction.response.send_message("❌ User not found!", ephemeral=True)
                            return

                    contains = modal.children[2].value if modal.children[2].value else None

                    # Check permissions
                    if not interaction.user.guild_permissions.manage_messages:
                        await interaction.response.send_message("❌ You don't have permission to delete messages!", ephemeral=True)
                        return

                    if not interaction.guild.me.guild_permissions.manage_messages:
                        await interaction.response.send_message("❌ I don't have permission to delete messages!", ephemeral=True)
                        return

                    # Delete messages
                    try:
                        deleted = await interaction.channel.purge(
                            limit=amount,
                            check=lambda msg: (
                                (user is None or msg.author == user) and
                                (contains is None or contains in msg.content)
                            )
                        )
                        
                        # Create embed response
                        embed = discord.Embed(
                            title="Messages Deleted",
                            description=f"{len(deleted)} messages deleted.",
                            color=discord.Color.orange()
                        )
                        if user:
                            embed.add_field(name="User Filter", value=user.mention)
                        if contains:
                            embed.add_field(name="Content Filter", value=contains)
                        
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to delete messages!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "setwelcome":
            modal = CommandModal("Set Welcome Message", [
                {"label": "Channel", "placeholder": "Enter channel ID or #channel"},
                {"label": "Message", "placeholder": "Enter welcome message (use {user} for mention, {server} for server name)", "required": False},
                {"label": "Use Embed", "placeholder": "true/false", "required": False},
                {"label": "Color", "placeholder": "#2ecc71 (optional)", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse channel ID or mention
                    channel_input = modal.children[0].value
                    channel_id = ''.join(filter(str.isdigit, channel_input))
                    
                    try:
                        channel = interaction.guild.get_channel(int(channel_id))
                        if not channel:
                            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
                            return
                    except (ValueError, TypeError):
                        await interaction.response.send_message("❌ Invalid channel format!", ephemeral=True)
                        return

                    # Get optional parameters
                    message = modal.children[1].value if modal.children[1].value else None
                    use_embed = modal.children[2].value.lower() in ['true', 'yes', '1'] if modal.children[2].value else None
                    color = modal.children[3].value if modal.children[3].value else None

                    welcome_cog = interaction.client.get_cog("Welcome")
                    if not welcome_cog:
                        await interaction.response.send_message("❌ Welcome module not loaded!", ephemeral=True)
                        return

                    try:
                        await welcome_cog.set_welcome.callback(welcome_cog, interaction, channel, message, use_embed, color)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "setgoodbye":
            modal = CommandModal("Set Goodbye Message", [
                {"label": "Channel", "placeholder": "Enter channel ID or #channel"},
                {"label": "Message", "placeholder": "Enter goodbye message (use {user} for mention, {server} for server name)", "required": False},
                {"label": "Use Embed", "placeholder": "true/false", "required": False},
                {"label": "Color", "placeholder": "#e74c3c (optional)", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse channel ID or mention
                    channel_input = modal.children[0].value
                    channel_id = ''.join(filter(str.isdigit, channel_input))
                    
                    try:
                        channel = interaction.guild.get_channel(int(channel_id))
                        if not channel:
                            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
                            return
                    except (ValueError, TypeError):
                        await interaction.response.send_message("❌ Invalid channel format!", ephemeral=True)
                        return

                    # Get optional parameters
                    message = modal.children[1].value if modal.children[1].value else None
                    use_embed = modal.children[2].value.lower() in ['true', 'yes', '1'] if modal.children[2].value else None
                    color = modal.children[3].value if modal.children[3].value else None

                    welcome_cog = interaction.client.get_cog("Welcome")
                    if not welcome_cog:
                        await interaction.response.send_message("❌ Welcome module not loaded!", ephemeral=True)
                        return

                    try:
                        await welcome_cog.set_goodbye.callback(welcome_cog, interaction, channel, message, use_embed, color)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "setprefix":
            modal = CommandModal("Set Server Prefix", [
                {"label": "Prefix", "placeholder": "Enter new prefix"}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    prefix = modal.children[0].value
                    config_cog = interaction.client.get_cog("Config")
                    if not config_cog:
                        await interaction.response.send_message("❌ Config module not loaded!", ephemeral=True)
                        return
                    try:
                        await config_cog.config.callback(config_cog, interaction, "bot", "prefix", prefix)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "setlogs":
            modal = CommandModal("Set Logging Channel", [
                {"label": "Channel", "placeholder": "Enter channel ID or #channel"}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse channel ID or mention
                    channel_input = modal.children[0].value
                    channel_id = ''.join(filter(str.isdigit, channel_input))
                    
                    try:
                        channel = interaction.guild.get_channel(int(channel_id))
                        if not channel:
                            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
                            return
                    except (ValueError, TypeError):
                        await interaction.response.send_message("❌ Invalid channel format!", ephemeral=True)
                        return

                    config_cog = interaction.client.get_cog("Config")
                    if not config_cog:
                        await interaction.response.send_message("❌ Config module not loaded!", ephemeral=True)
                        return
                    try:
                        await config_cog.config.callback(config_cog, interaction, "moderation", "log_channel", str(channel.id))
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "viewconfig":
            config_cog = interaction.client.get_cog("Config")
            if not config_cog:
                await interaction.response.send_message("❌ Config module not loaded!", ephemeral=True)
                return
            try:
                await config_cog.view_config.callback(config_cog, interaction)
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

        elif command == "unmute":
            modal = CommandModal("Unmute User", [
                {"label": "User", "placeholder": "Enter user ID or mention"},
                {"label": "Reason", "placeholder": "Enter reason for unmuting (optional)", "max_length": 1000}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        await interaction.response.send_message(f"❌ User with ID {user_id} not found in this server!", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}. Make sure they are in the server!", ephemeral=True)
                        return

                    reason = modal.children[1].value if len(modal.children) > 1 and modal.children[1].value else None

                    mod_cog = interaction.client.get_cog("Moderation")
                    if not mod_cog:
                        await interaction.response.send_message("❌ Moderation module not loaded!", ephemeral=True)
                        return

                    try:
                        # Call the unmute function directly instead of through the command
                        if not user.is_timed_out():
                            await interaction.response.send_message("❌ This user is not muted!", ephemeral=True)
                            return
                        
                        await user.timeout(None, reason=reason or f"Unmuted by {interaction.user}")
                        
                        embed = discord.Embed(
                            title="User Unmuted",
                            description=f"{user.mention} has been unmuted.",
                            color=discord.Color.green()
                        )
                        if reason:
                            embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Moderator", value=interaction.user.mention)
                        
                        await interaction.response.send_message(embed=embed)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to unmute this user!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "unban":
            modal = CommandModal("Unban User", [
                {"label": "User ID", "placeholder": "Enter user ID"}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    user_id = int(modal.children[0].value)
                    bans = [ban async for ban in interaction.guild.bans()]
                    user_ban = next((ban for ban in bans if ban.user.id == user_id), None)
                    
                    if not user_ban:
                        await interaction.response.send_message("❌ User not found in ban list!", ephemeral=True)
                        return
                        
                    await interaction.guild.unban(user_ban.user, reason=f"Unbanned by {interaction.user}")
                    await interaction.response.send_message(f"✅ Successfully unbanned user {user_ban.user}", ephemeral=True)
                    
                except ValueError:
                    await interaction.response.send_message("❌ Invalid user ID!", ephemeral=True)
                except Exception as e:
                    self.logger.error(f"Error in unban modal: {e}")
                    await interaction.response.send_message("❌ An error occurred while unbanning the user.", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "infractions":
            modal = CommandModal("View Infractions", [
                {"label": "User", "placeholder": "Enter user ID or mention"}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    # Parse user ID or mention
                    user_input = modal.children[0].value
                    user_id = ''.join(filter(str.isdigit, user_input))
                    
                    # Try multiple ways to get the user
                    user = None
                    try:
                        # Try getting member from cache first
                        user = interaction.guild.get_member(int(user_id))
                        if user is None:
                            # If not in cache, try fetching from API
                            user = await interaction.guild.fetch_member(int(user_id))
                    except discord.NotFound:
                        await interaction.response.send_message(f"❌ User with ID {user_id} not found in this server!", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error fetching user: {str(e)}", ephemeral=True)
                        return
                    except ValueError:
                        await interaction.response.send_message("❌ Invalid user ID format!", ephemeral=True)
                        return

                    if user is None:
                        await interaction.response.send_message(f"❌ Could not find user with ID {user_id}. Make sure they are in the server!", ephemeral=True)
                        return

                    mod_cog = interaction.client.get_cog("Moderation")
                    if not mod_cog:
                        await interaction.response.send_message("❌ Moderation module not loaded!", ephemeral=True)
                        return

                    try:
                        await mod_cog.infractions.callback(mod_cog, interaction, user)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "lock":
            modal = CommandModal("Lock Channel", [
                {"label": "Channel", "placeholder": "Enter channel ID or name (leave empty for current channel)", "required": False},
                {"label": "Reason", "placeholder": "Reason for locking the channel", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    channel = interaction.channel
                    if modal.children[0].value:
                        channel_input = modal.children[0].value
                        channel_id = ''.join(filter(str.isdigit, channel_input))
                        try:
                            new_channel = interaction.guild.get_channel(int(channel_id))
                            if new_channel:
                                channel = new_channel
                        except:
                            await interaction.response.send_message("❌ Invalid channel!", ephemeral=True)
                            return

                    reason = modal.children[1].value if modal.children[1].value else None

                    # Check permissions
                    if not interaction.user.guild_permissions.manage_channels:
                        await interaction.response.send_message("❌ You don't have permission to manage channels!", ephemeral=True)
                        return

                    if not interaction.guild.me.guild_permissions.manage_channels:
                        await interaction.response.send_message("❌ I don't have permission to manage channels!", ephemeral=True)
                        return

                    # Lock the channel
                    try:
                        await channel.set_permissions(
                            interaction.guild.default_role,
                            send_messages=False,
                            reason=reason
                        )
                        
                        # Create embed response
                        embed = discord.Embed(
                            title="Channel Locked",
                            description=f"{channel.mention} has been locked.",
                            color=discord.Color.orange()
                        )
                        if reason:
                            embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Moderator", value=interaction.user.mention)
                        
                        await interaction.response.send_message(embed=embed)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to lock this channel!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "unlock":
            modal = CommandModal("Unlock Channel", [
                {"label": "Channel", "placeholder": "Enter channel ID or name (leave empty for current channel)", "required": False},
                {"label": "Reason", "placeholder": "Reason for unlocking the channel", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    channel = interaction.channel
                    if modal.children[0].value:
                        channel_input = modal.children[0].value
                        channel_id = ''.join(filter(str.isdigit, channel_input))
                        try:
                            new_channel = interaction.guild.get_channel(int(channel_id))
                            if new_channel:
                                channel = new_channel
                        except:
                            await interaction.response.send_message("❌ Invalid channel!", ephemeral=True)
                            return

                    reason = modal.children[1].value if modal.children[1].value else None

                    # Check permissions
                    if not interaction.user.guild_permissions.manage_channels:
                        await interaction.response.send_message("❌ You don't have permission to manage channels!", ephemeral=True)
                        return

                    if not interaction.guild.me.guild_permissions.manage_channels:
                        await interaction.response.send_message("❌ I don't have permission to manage channels!", ephemeral=True)
                        return

                    # Unlock the channel
                    try:
                        await channel.set_permissions(
                            interaction.guild.default_role,
                            send_messages=None,
                            reason=reason
                        )
                        
                        # Create embed response
                        embed = discord.Embed(
                            title="Channel Unlocked",
                            description=f"{channel.mention} has been unlocked.",
                            color=discord.Color.green()
                        )
                        if reason:
                            embed.add_field(name="Reason", value=reason)
                        embed.add_field(name="Moderator", value=interaction.user.mention)
                        
                        await interaction.response.send_message(embed=embed)
                        
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to unlock this channel!", ephemeral=True)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "remind":
            modal = CommandModal("Set Reminder", [
                {"label": "Duration", "placeholder": "Duration in minutes (1-10080)"},
                {"label": "Reminder", "placeholder": "What to remind you about"},
                {"label": "Repeats", "placeholder": "Number of times to repeat (1-5, optional)", "required": False}
            ])
            async def modal_callback(interaction: discord.Interaction):
                try:
                    try:
                        duration = int(modal.children[0].value)
                        if duration < 1 or duration > 10080:  # 1 week max
                            await interaction.response.send_message("❌ Duration must be between 1 and 10080 minutes!", ephemeral=True)
                            return
                    except ValueError:
                        await interaction.response.send_message("❌ Duration must be a number!", ephemeral=True)
                        return

                    reminder = modal.children[1].value
                    
                    repeats = 1
                    if modal.children[2].value:
                        try:
                            repeats = int(modal.children[2].value)
                            if repeats < 1 or repeats > 5:
                                await interaction.response.send_message("❌ Repeats must be between 1 and 5!", ephemeral=True)
                                return
                        except ValueError:
                            await interaction.response.send_message("❌ Repeats must be a number!", ephemeral=True)
                            return

                    utilities_cog = interaction.client.get_cog("Utilities")
                    if not utilities_cog:
                        await interaction.response.send_message("❌ Utilities module not loaded!", ephemeral=True)
                        return
                    try:
                        await utilities_cog.remind.callback(utilities_cog, interaction, duration, reminder, repeats)
                    except Exception as e:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                        else:
                            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "calculate":
            modal = CommandModal("Calculate", [
                {"label": "Expression", "placeholder": "Enter mathematical expression"}
            ])
            async def modal_callback(interaction: discord.Interaction):
                expression = modal.children[0].value
                utilities_cog = interaction.client.get_cog("Utilities")
                if not utilities_cog:
                    await interaction.response.send_message("❌ Utilities module not loaded!", ephemeral=True)
                    return
                try:
                    await utilities_cog.calculate.callback(utilities_cog, interaction, expression)
                except Exception as e:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                    else:
                        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

        elif command == "serverinfo":
            utilities_cog = interaction.client.get_cog("Utilities")
            if not utilities_cog:
                await interaction.response.send_message("❌ Utilities module not loaded!", ephemeral=True)
                return
            try:
                await utilities_cog.serverinfo.callback(utilities_cog, interaction)
            except Exception as e:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

class CommandPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # Add command dropdowns
        self.add_item(CommandSelect("Moderation", [
            {"name": "warn", "description": "Warn a user"},
            {"name": "mute", "description": "Timeout a user"},
            {"name": "unmute", "description": "Remove timeout from a user"},
            {"name": "kick", "description": "Kick a user"},
            {"name": "ban", "description": "Ban a user"},
            {"name": "unban", "description": "Unban a user"},
            {"name": "clean", "description": "Delete messages"},
            {"name": "infractions", "description": "View user infractions"}
        ]))

        self.add_item(CommandSelect("Server Management", [
            {"name": "setwelcome", "description": "Set welcome message"},
            {"name": "setgoodbye", "description": "Set goodbye message"},
            {"name": "setprefix", "description": "Set server prefix"},
            {"name": "setlogs", "description": "Set logging channel"},
            {"name": "viewconfig", "description": "View server settings"},
            {"name": "lock", "description": "Lock a channel"},
            {"name": "unlock", "description": "Unlock a channel"}
        ]))

        self.add_item(CommandSelect("Utilities", [
            {"name": "remind", "description": "Set a reminder"},
            {"name": "calculate", "description": "Calculate math expression"},
            {"name": "serverinfo", "description": "View server information"}
        ]))

        # Add quick action buttons
        lock_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            label="Lock"
        )
        lock_button.callback = self.lock_channel
        self.add_item(lock_button)

        unlock_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            emoji="🔓",
            label="Unlock"
        )
        unlock_button.callback = self.unlock_channel
        self.add_item(unlock_button)

        info_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="ℹ️",
            label="Info"
        )
        info_button.callback = self.server_info
        self.add_item(info_button)

    async def lock_channel(self, interaction: discord.Interaction):
        try:
            # Check permissions
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message("❌ You don't have permission to manage channels!", ephemeral=True)
                return

            if not interaction.guild.me.guild_permissions.manage_channels:
                await interaction.response.send_message("❌ I don't have permission to manage channels!", ephemeral=True)
                return

            # Lock the channel
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                send_messages=False,
                reason=f"Channel locked by {interaction.user}"
            )
            
            # Create embed response
            embed = discord.Embed(
                title="Channel Locked",
                description=f"{interaction.channel.mention} has been locked.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Moderator", value=interaction.user.mention)
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to lock this channel!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    async def unlock_channel(self, interaction: discord.Interaction):
        try:
            # Check permissions
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message("❌ You don't have permission to manage channels!", ephemeral=True)
                return

            if not interaction.guild.me.guild_permissions.manage_channels:
                await interaction.response.send_message("❌ I don't have permission to manage channels!", ephemeral=True)
                return

            # Unlock the channel
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                send_messages=None,
                reason=f"Channel unlocked by {interaction.user}"
            )
            
            # Create embed response
            embed = discord.Embed(
                title="Channel Unlocked",
                description=f"{interaction.channel.mention} has been unlocked.",
                color=discord.Color.green()
            )
            embed.add_field(name="Moderator", value=interaction.user.mention)
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unlock this channel!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    async def server_info(self, interaction: discord.Interaction):
        utilities_cog = interaction.client.get_cog("Utilities")
        if not utilities_cog:
            await interaction.response.send_message("❌ Utilities module not loaded!", ephemeral=True)
            return
        try:
            await utilities_cog.serverinfo.callback(utilities_cog, interaction)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class Utilities(commands.Cog):
    """Utility commands for server management and information"""
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('utilities')
        self.active_reminders = []
        self.max_reminder_duration = 10080  # 1 week in minutes
        self.max_poll_options = 4
        self.max_poll_length = 1000  # characters
        self.panel_view = CommandPanelView()

    @app_commands.command(name="panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction):
        """Open the admin control panel"""
        try:
            embed = discord.Embed(
                title="🎛️ Admin Control Panel",
                description="Select a command category from the dropdowns below or use the quick action buttons.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=self.panel_view, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error showing admin panel: {e}")
            await interaction.response.send_message("❌ Failed to open admin panel. Please try again later.", ephemeral=True)

    @app_commands.command(name="serverinfo")
    async def serverinfo(self, interaction: discord.Interaction):
        """Get information about the server"""
        guild = interaction.guild
        
        embed = discord.Embed(
            title=f"{guild.name} Server Information",
            color=discord.Color.blue()
        )
        
        # Server icon
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Basic info
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Created At", value=discord.utils.format_dt(guild.created_at), inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        
        # Member counts
        total_members = len(guild.members)
        humans = len([m for m in guild.members if not m.bot])
        bots = total_members - humans
        embed.add_field(name="Total Members", value=total_members, inline=True)
        embed.add_field(name="Humans", value=humans, inline=True)
        embed.add_field(name="Bots", value=bots, inline=True)
        
        # Channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        embed.add_field(name="Text Channels", value=text_channels, inline=True)
        embed.add_field(name="Voice Channels", value=voice_channels, inline=True)
        embed.add_field(name="Categories", value=categories, inline=True)
        
        # Other info
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Emojis", value=len(guild.emojis), inline=True)
        embed.add_field(name="Boost Level", value=guild.premium_tier, inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remind")
    @app_commands.describe(
        duration="Duration in minutes (max 1 week)",
        reminder="What to remind you about",
        repeat="Number of times to repeat (max 5)"
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        duration: app_commands.Range[int, 1, 10080],
        reminder: str,
        repeat: Optional[app_commands.Range[int, 1, 5]] = 1
    ):
        """Set a reminder with optional repeats"""
        try:
            if len(reminder) > 1000:
                await interaction.response.send_message(
                    "❌ Reminder text too long! Please keep it under 1000 characters.",
                    ephemeral=True
                )
                return

            remind_time = datetime.utcnow() + timedelta(minutes=duration)
            
            reminder_data = {
                "user_id": interaction.user.id,
                "channel_id": interaction.channel_id,
                "reminder": reminder,
                "time": remind_time.isoformat(),
                "repeat": repeat,
                "repeat_count": 0
            }
            
            self.active_reminders.append(reminder_data)
            
            embed = discord.Embed(
                title="⏰ Reminder Set",
                color=discord.Color.blue(),
                description=f"I'll remind you about: {reminder}"
            )
            embed.add_field(
                name="First Reminder",
                value=discord.utils.format_dt(remind_time, "R")
            )
            if repeat > 1:
                embed.add_field(
                    name="Repeats",
                    value=f"This reminder will repeat {repeat} times every {duration} minutes"
                )
            
            await interaction.response.send_message(embed=embed)
            
            for i in range(repeat):
                await asyncio.sleep(duration * 60)
                await self._send_reminder(
                    interaction.user.id,
                    interaction.channel_id,
                    reminder,
                    i + 1,
                    repeat
                )

        except Exception as e:
            self.logger.error(f"Error setting reminder: {e}")
            await interaction.response.send_message(
                "❌ Failed to set reminder. Please try again.",
                ephemeral=True
            )

    async def _send_reminder(
        self,
        user_id: int,
        channel_id: int,
        reminder: str,
        current_repeat: int,
        total_repeats: int
    ):
        """Send a reminder with repeat information"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
                
            user = channel.guild.get_member(user_id)
            if not user:
                return
                
            embed = discord.Embed(
                title="⏰ Reminder",
                description=reminder,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if total_repeats > 1:
                embed.set_footer(text=f"Reminder {current_repeat} of {total_repeats}")
            
            await channel.send(
                content=user.mention,
                embed=embed
            )
        except Exception as e:
            self.logger.error(f"Failed to send reminder: {e}")

    @app_commands.command(name="calculate")
    @app_commands.describe(
        expression="Mathematical expression to evaluate"
    )
    async def calculate(
        self,
        interaction: discord.Interaction,
        expression: str
    ):
        """Calculate a mathematical expression"""
        try:
            # Remove any dangerous functions or imports
            if any(x in expression.lower() for x in ['import', 'eval', 'exec', 'os', 'sys', '__']):
                await interaction.response.send_message("❌ Invalid expression!", ephemeral=True)
                return
            
            # Evaluate the expression safely
            result = eval(expression, {"__builtins__": {}}, {"math": math})
            
            embed = discord.Embed(
                title="🔢 Calculator",
                description=f"Expression: `{expression}`\nResult: `{result}`",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
            self.logger.error(f"Error in calculate command: {e}")

async def setup(bot):
    await bot.add_cog(Utilities(bot))

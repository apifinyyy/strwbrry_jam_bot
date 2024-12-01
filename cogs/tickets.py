import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import json
import asyncio
from datetime import datetime
import io

class TicketDropdown(discord.ui.Select):
    def __init__(self, options: List[str]):
        super().__init__(
            placeholder="Select Ticket Category",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=option, emoji="🎫", description=f"Create a {option} ticket") for option in options]
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        category = self.values[0]
        guild = interaction.guild
        
        try:
            data = interaction.client.data_manager.load("tickets", str(guild.id))
            if not data:
                data = {
                    "ticket_counter": 0,
                    "active_tickets": {},
                    "categories": ["General Support", "Technical Issue", "Billing", "Other"]
                }
                interaction.client.data_manager.save("tickets", str(guild.id), data)
        except Exception as e:
            interaction.client.logger.error(f"Error loading ticket data: {e}")
            data = {
                "ticket_counter": 0,
                "active_tickets": {},
                "categories": ["General Support", "Technical Issue", "Billing", "Other"]
            }
        
        ticket_number = data.get("ticket_counter", 0) + 1
        
        # Update ticket data
        data["ticket_counter"] = ticket_number
        data["active_tickets"][str(ticket_number)] = {
            "user_id": interaction.user.id,
            "category": category,
            "created_at": datetime.utcnow().isoformat(),
            "status": "open"
        }
        await interaction.client.data_manager.save("tickets", str(guild.id), data)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        support_role = discord.utils.get(guild.roles, name="Support Team")
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel_name = f"ticket-{ticket_number:04d}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Ticket created by {interaction.user}"
            )
            
            embed = discord.Embed(
                title=f"Ticket #{ticket_number:04d} - {category}",
                description=(
                    f"Welcome {interaction.user.mention}!\n\n"
                    f"**Category:** {category}\n"
                    f"**Created:** <t:{int(datetime.utcnow().timestamp())}:R>\n\n"
                    "Please describe your issue and wait for a support team member to assist you.\n"
                    "A support team member will claim this ticket when they're available."
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Use the buttons below to manage this ticket")
            
            class TicketButtons(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(style=discord.ButtonStyle.primary, emoji="🔒", label="Close", custom_id="close_ticket")
                async def close_ticket(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user.id != interaction.user.id and not button_interaction.user.guild_permissions.manage_channels:
                        await button_interaction.response.send_message("❌ Only the ticket creator or staff can close this ticket!", ephemeral=True)
                        return

                    await button_interaction.response.defer()
                    
                    # Create transcript
                    transcript = []
                    async for message in channel.history(limit=None, oldest_first=True):
                        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        content = message.content or "*[No content]*"
                        transcript.append(f"[{timestamp}] {message.author}: {content}")
                    
                    transcript_file = discord.File(
                        io.StringIO("\n".join(transcript)),
                        filename=f"ticket-{ticket_number:04d}-transcript.txt"
                    )
                    
                    # Send transcript to user
                    try:
                        await interaction.user.send(
                            f"Here's the transcript of your ticket #{ticket_number:04d}",
                            file=transcript_file
                        )
                    except:
                        pass
                    
                    await channel.send("🔒 Closing ticket in 5 seconds...")
                    await asyncio.sleep(5)
                    await channel.delete()
                    
                    # Update ticket data
                    data = interaction.client.data_manager.load("tickets", str(guild.id))
                    if str(ticket_number) in data["active_tickets"]:
                        data["active_tickets"][str(ticket_number)]["status"] = "closed"
                        await interaction.client.data_manager.save("tickets", str(guild.id), data)

                @discord.ui.button(style=discord.ButtonStyle.success, emoji="👋", label="Claim", custom_id="claim_ticket")
                async def claim_ticket(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if not support_role or support_role not in button_interaction.user.roles:
                        await button_interaction.response.send_message("❌ Only support team members can claim tickets!", ephemeral=True)
                        return
                    
                    await button_interaction.response.defer()
                    
                    claim_embed = discord.Embed(
                        title="Ticket Claimed",
                        description=f"This ticket has been claimed by {button_interaction.user.mention}",
                        color=discord.Color.green()
                    )
                    await channel.send(embed=claim_embed)
                    
                    # Update embed to show claimed status
                    embed.add_field(name="Claimed By", value=button_interaction.user.mention)
                    await message.edit(embed=embed)
                    button.disabled = True
                    await message.edit(view=self)
            
            message = await channel.send(embed=embed, view=TicketButtons())
            await interaction.followup.send(f"✅ Created ticket channel: {channel.mention}", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels! Please contact a server administrator.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}\nPlease contact a server administrator.", ephemeral=True)

class TicketDropdownView(discord.ui.View):
    def __init__(self, options: List[str]):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(options))

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "tickets"

    def _get_ticket_data(self, guild_id: int):
        """Get ticket data for a specific guild."""
        try:
            data = self.bot.data_manager.load("tickets", str(guild_id))
            if not data:
                data = {
                    "ticket_counter": 0,
                    "active_tickets": {},
                    "categories": ["General Support", "Technical Issue", "Billing", "Other"]
                }
                self.bot.data_manager.save("tickets", str(guild_id), data)
            return data
        except Exception as e:
            self.bot.logger.error(f"Error loading ticket data: {e}")
            return {
                "ticket_counter": 0,
                "active_tickets": {},
                "categories": ["General Support", "Technical Issue", "Billing", "Other"]
            }

    async def save_ticket_data(self, guild_id: int, data: dict):
        """Save ticket data for a specific guild."""
        try:
            await self.bot.data_manager.save("tickets", str(guild_id), data)
        except Exception as e:
            self.bot.logger.error(f"Error saving ticket data: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Load ticket data for all guilds on startup."""
        for guild in self.bot.guilds:
            await self._get_ticket_data(guild.id)

    @app_commands.command(name="ticketsetup", description="Set up the ticket system with a dropdown menu")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str = "🎫 Support Tickets",
        description: str = "Click the dropdown below to create a support ticket.",
        color: str = "blue"
    ):
        """Set up the ticket system with a dropdown menu in the specified channel."""
        try:
            # Validate color
            try:
                color_value = getattr(discord.Color, color)()
            except AttributeError:
                color_value = discord.Color.blue()

            # Get ticket categories
            data = self._get_ticket_data(interaction.guild_id)
            categories = data.get("categories", ["General Support", "Technical Issue", "Billing", "Other"])

            # Create embed
            embed = discord.Embed(
                title=title,
                description=description,
                color=color_value
            )
            embed.set_footer(text=f"Ticket System • {interaction.guild.name}")

            # Create dropdown view
            view = TicketDropdownView(categories)

            # Send the message
            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ Ticket system has been set up successfully!", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="ticketcategories", description="Manage ticket categories")
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_categories(
        self,
        interaction: discord.Interaction,
        action: str,
        category: Optional[str] = None
    ):
        """Manage ticket categories."""
        try:
            data = self._get_ticket_data(interaction.guild_id)
            categories = data.get("categories", ["General Support", "Technical Issue", "Billing", "Other"])

            if action.lower() == "list":
                embed = discord.Embed(
                    title="Ticket Categories",
                    description="\n".join(f"• {cat}" for cat in categories),
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not category:
                await interaction.response.send_message("❌ Please provide a category name!", ephemeral=True)
                return

            if action.lower() == "add":
                if category in categories:
                    await interaction.response.send_message("❌ This category already exists!", ephemeral=True)
                    return
                categories.append(category)
                data["categories"] = categories
                await self.save_ticket_data(interaction.guild_id, data)
                await interaction.response.send_message(f"✅ Added category: {category}", ephemeral=True)

            elif action.lower() == "remove":
                if category not in categories:
                    await interaction.response.send_message("❌ This category doesn't exist!", ephemeral=True)
                    return
                categories.remove(category)
                data["categories"] = categories
                await self.save_ticket_data(interaction.guild_id, data)
                await interaction.response.send_message(f"✅ Removed category: {category}", ephemeral=True)

            else:
                await interaction.response.send_message("❌ Invalid action! Use 'list', 'add', or 'remove'", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

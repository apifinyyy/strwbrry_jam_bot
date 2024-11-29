import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import json

class TicketDropdown(discord.ui.Select):
    def __init__(self, options: List[str]):
        super().__init__(
            placeholder="Create a Support Ticket",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=option, emoji="🎫") for option in options]
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Get category name from selection
        category = self.values[0]
        
        # Create ticket channel
        guild = interaction.guild
        
        # Get ticket number
        try:
            data = interaction.client.data_manager.load_data(guild.id, "tickets")
        except FileNotFoundError:
            data = {"ticket_counter": 0, "active_tickets": {}}
        
        ticket_number = data.get("ticket_counter", 0) + 1
        
        # Update ticket counter
        data["ticket_counter"] = ticket_number
        interaction.client.data_manager.save_data(guild.id, "tickets", data)
        
        # Set up permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        # Try to find support role and add permissions
        support_role = discord.utils.get(guild.roles, name="Support Team")
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Create the ticket channel
        channel_name = f"ticket-{ticket_number:04d}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Ticket created by {interaction.user}"
            )
            
            # Create embed for the ticket channel
            embed = discord.Embed(
                title=f"Ticket #{ticket_number:04d} - {category}",
                description=f"Welcome {interaction.user.mention}! Support will be with you shortly.\n\nTicket Category: **{category}**",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Use 🔒 to close the ticket")
            
            # Create close button
            class CloseButton(discord.ui.Button):
                def __init__(self):
                    super().__init__(style=discord.ButtonStyle.danger, emoji="🔒", label="Close Ticket")
                
                async def callback(self, button_interaction: discord.Interaction):
                    await button_interaction.response.defer()
                    await channel.send("🔒 Ticket will be closed in 5 seconds...")
                    await channel.delete()
            
            # Create view with close button
            view = discord.ui.View(timeout=None)
            view.add_item(CloseButton())
            
            await channel.send(embed=embed, view=view)
            await interaction.followup.send(f"✅ Created ticket channel: {channel.mention}", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

class TicketDropdownView(discord.ui.View):
    def __init__(self, options: List[str]):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(options))

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "tickets"

    def _get_ticket_data(self, guild_id: int) -> dict:
        """Get ticket data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {
                "ticket_counter": 0,
                "active_tickets": {},
                "categories": ["General Support", "Technical Issue", "Billing", "Other"]
            }
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
        return data

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
                self.bot.data_manager.save_data(interaction.guild_id, self.data_type, data)
                await interaction.response.send_message(f"✅ Added category: {category}", ephemeral=True)

            elif action.lower() == "remove":
                if category not in categories:
                    await interaction.response.send_message("❌ This category doesn't exist!", ephemeral=True)
                    return
                categories.remove(category)
                data["categories"] = categories
                self.bot.data_manager.save_data(interaction.guild_id, self.data_type, data)
                await interaction.response.send_message(f"✅ Removed category: {category}", ephemeral=True)

            else:
                await interaction.response.send_message("❌ Invalid action! Use 'list', 'add', or 'remove'", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

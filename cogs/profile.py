import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @app_commands.command(name="profile", description="View your or another user's profile")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View a user's profile with XP and economy information."""
        try:
            target = user or interaction.user
            
            # Get user data
            user_data = self._get_user_data(interaction.guild_id, target.id)
            
            # Create embed
            embed = discord.Embed(
                title=f"{target.name}'s Profile",
                color=discord.Color.blue()
            )

            # Set thumbnail to user's avatar
            embed.set_thumbnail(url=target.display_avatar.url)

            # Add XP information
            chat_xp = user_data.get("chat_xp", 0)
            voice_xp = user_data.get("voice_xp", 0)
            total_xp = chat_xp + voice_xp

            embed.add_field(
                name="💬 Chat XP",
                value=f"{chat_xp:,}",
                inline=True
            )
            embed.add_field(
                name="🎤 Voice XP",
                value=f"{voice_xp:,}",
                inline=True
            )
            embed.add_field(
                name="✨ Total XP",
                value=f"{total_xp:,}",
                inline=True
            )

            # Add economy information
            balance = user_data.get("balance", 0)
            inventory = user_data.get("inventory", [])

            embed.add_field(
                name="🪙 Balance",
                value=f"{balance:,} coins",
                inline=True
            )

            if inventory:
                embed.add_field(
                    name="🎒 Inventory",
                    value="\n".join(f"• {item}" for item in inventory[:5]) + 
                          (f"\n...and {len(inventory) - 5} more" if len(inventory) > 5 else ""),
                    inline=False
                )

            # Add member information
            member_since = discord.utils.format_dt(target.joined_at, style="R")
            embed.add_field(
                name="📅 Member Since",
                value=member_since,
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Profile(bot))

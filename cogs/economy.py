import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import asyncio
from datetime import datetime, timedelta

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "economy"

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        """Get user's economy data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {}
            
        if str(user_id) not in data:
            data[str(user_id)] = {
                "balance": self.bot.config_manager.get_value(guild_id, "economy", "starting_balance", default=0),
                "last_daily": None,
                "last_weekly": None,
                "inventory": []
            }
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
        return data[str(user_id)]

    def _save_user_data(self, guild_id: int, user_id: int, user_data: dict) -> None:
        """Save user's economy data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {}
        data[str(user_id)] = user_data
        self.bot.data_manager.save_data(guild_id, self.data_type, data)

    @app_commands.command(name="balance", description="Check your or another user's balance")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Check balance command."""
        target = user or interaction.user
        user_data = self._get_user_data(interaction.guild_id, target.id)
        
        embed = discord.Embed(title="💰 Balance", color=discord.Color.green())
        embed.add_field(name=f"{target.display_name}'s Balance", value=f"🪙 {user_data['balance']:,} coins")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily reward")
    @app_commands.checks.cooldown(1, 86400)  # 1 use per 24 hours (86400 seconds)
    async def daily(self, interaction: discord.Interaction):
        """Daily reward command."""
        try:
            # Get reward amount from config
            amount = self.bot.config_manager.get_value(
                interaction.guild_id,
                "economy",
                "daily_amount",
                default=100
            )

            # Get user data
            user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
            
            # Give reward
            user_data["balance"] += amount
            self._save_user_data(interaction.guild_id, interaction.user.id, user_data)
            
            embed = discord.Embed(
                title="✨ Daily Reward",
                description=f"You received 🪙 **{amount:,}** coins!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="New Balance",
                value=f"🪙 {user_data['balance']:,} coins"
            )
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while processing your daily reward. Please try again.",
                ephemeral=True
            )
            print(f"Error in daily command: {str(e)}")

    @daily.error
    async def daily_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            hours = int(error.retry_after // 3600)
            minutes = int((error.retry_after % 3600) // 60)
            seconds = int(error.retry_after % 60)
            
            await interaction.response.send_message(
                f"⏰ You can claim your daily reward in {hours} hours, {minutes} minutes, and {seconds} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.",
                ephemeral=True
            )

    @app_commands.command(name="weekly", description="Claim your weekly reward")
    async def weekly(self, interaction: discord.Interaction):
        """Weekly reward command."""
        user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
        
        # Check cooldown
        if user_data["last_weekly"]:
            last_claim = datetime.fromisoformat(user_data["last_weekly"])
            if datetime.now() - last_claim < timedelta(weeks=1):
                time_left = timedelta(weeks=1) - (datetime.now() - last_claim)
                days = time_left.days
                hours = time_left.seconds // 3600
                await interaction.response.send_message(
                    f"⏰ You can claim your weekly reward in {days} days and {hours} hours.",
                    ephemeral=True
                )
                return

        # Get reward amount from config
        amount = self.bot.config_manager.get_value(
            interaction.guild_id,
            "economy",
            "weekly_amount",
            default=1000
        )

        # Give reward
        user_data["balance"] += amount
        user_data["last_weekly"] = datetime.now().isoformat()
        self._save_user_data(interaction.guild_id, interaction.user.id, user_data)
        
        embed = discord.Embed(
            title="🎉 Weekly Reward",
            description=f"You received 🪙 **{amount:,}** coins!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="New Balance",
            value=f"🪙 {user_data['balance']:,} coins"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="give", description="Give coins to another user")
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Admin command to give coins."""
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return

        user_data = self._get_user_data(interaction.guild_id, user.id)
        max_balance = self.bot.config_manager.get_value(
            interaction.guild_id,
            "economy",
            "max_balance",
            default=1000000
        )

        if user_data["balance"] + amount > max_balance:
            await interaction.response.send_message(
                f"❌ This would exceed the maximum balance of 🪙 {max_balance:,}!",
                ephemeral=True
            )
            return

        user_data["balance"] += amount
        self._save_user_data(interaction.guild_id, user.id, user_data)

        embed = discord.Embed(
            title="💸 Coins Given",
            description=f"Gave 🪙 **{amount:,}** coins to {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="New Balance",
            value=f"🪙 {user_data['balance']:,} coins"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="take", description="Take coins from a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def take(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Admin command to take coins."""
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return
        
        user_data = self._get_user_data(interaction.guild_id, user.id)
        
        if user_data["balance"] < amount:
            await interaction.response.send_message(
                f"❌ User only has 🪙 {user_data['balance']:,} coins!",
                ephemeral=True
            )
            return
        
        user_data["balance"] -= amount
        self._save_user_data(interaction.guild_id, user.id, user_data)
        
        embed = discord.Embed(
            title="💸 Coins Taken",
            description=f"Took 🪙 **{amount:,}** coins from {user.mention}",
            color=discord.Color.red()
        )
        embed.add_field(
            name="New Balance",
            value=f"🪙 {user_data['balance']:,} coins"
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="richest", description="View the richest users")
    async def richest(self, interaction: discord.Interaction):
        """Show economy leaderboard."""
        try:
            data = self.bot.data_manager.load_data(interaction.guild_id, self.data_type)
        except FileNotFoundError:
            await interaction.response.send_message(
                "❌ No economy data found for this server!",
                ephemeral=True
            )
            return
        
        # Sort users by balance
        sorted_users = sorted(
            [(int(uid), udata["balance"]) for uid, udata in data.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]  # Top 10
        
        if not sorted_users:
            await interaction.response.send_message(
                "❌ No users found in the economy system!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🏆 Richest Users",
            description="Top 10 wealthiest members of the server",
            color=discord.Color.gold()
        )
        
        medals = ["🥇", "🥈", "🥉"]
        for idx, (user_id, balance) in enumerate(sorted_users, 1):
            user = interaction.guild.get_member(user_id)
            if user:
                medal = medals[idx-1] if idx <= 3 else f"{idx}."
                embed.add_field(
                    name=f"{medal} {user.display_name}",
                    value=f"🪙 {balance:,} coins",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Economy(bot))

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import asyncio
from datetime import datetime, timedelta
import random
import logging

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_type = "economy"
        self.active_giveaways = {}
        self.logger = logging.getLogger(__name__)
        self._cache = {}  # guild_id -> {user_id -> (data, timestamp)}
        self.cache_ttl = 300  # 5 minutes

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        """Get user's economy data for a specific guild with caching."""
        cache_key = f"{guild_id}_{user_id}"
        current_time = datetime.now().timestamp()

        # Check cache first
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if current_time - timestamp < self.cache_ttl:
                return data.copy()  # Return copy to prevent mutations

        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            self.logger.error(f"Error loading economy data: {e}")
            data = {}
            
        if str(user_id) not in data:
            starting_balance = self.bot.config_manager.get_value(
                guild_id,
                "economy",
                "starting_balance",
                default=100
            )
            data[str(user_id)] = {
                "balance": starting_balance,
                "last_daily": None,
                "last_weekly": None,
                "inventory": [],
                "transactions": []  # New: track recent transactions
            }
            try:
                self.bot.data_manager.save_data(guild_id, self.data_type, data)
            except Exception as e:
                self.logger.error(f"Error saving initial economy data: {e}")

        user_data = data[str(user_id)]
        self._cache[cache_key] = (user_data.copy(), current_time)
        return user_data

    def _save_user_data(self, guild_id: int, user_id: int, user_data: dict) -> bool:
        """Save user's economy data for a specific guild. Returns success status."""
        try:
            data = self.bot.data_manager.load_data(guild_id, self.data_type)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            self.logger.error(f"Error loading economy data for save: {e}")
            return False

        try:
            data[str(user_id)] = user_data
            self.bot.data_manager.save_data(guild_id, self.data_type, data)
            
            # Update cache
            cache_key = f"{guild_id}_{user_id}"
            self._cache[cache_key] = (user_data.copy(), datetime.now().timestamp())
            return True
        except Exception as e:
            self.logger.error(f"Error saving economy data: {e}")
            return False

    def _add_transaction(self, user_data: dict, amount: int, description: str):
        """Add a transaction to user's history"""
        if "transactions" not in user_data:
            user_data["transactions"] = []
            
        user_data["transactions"].append({
            "amount": amount,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 10 transactions
        user_data["transactions"] = user_data["transactions"][-10:]

    async def _end_giveaway(self, channel_id: int, message_id: int):
        """End a giveaway and select winner(s)"""
        if channel_id not in self.active_giveaways or message_id not in self.active_giveaways[channel_id]:
            return

        giveaway = self.active_giveaways[channel_id][message_id]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
            if not message:
                return

            # Get reaction users
            reaction = next((r for r in message.reactions if str(r.emoji) == "🎉"), None)
            if not reaction:
                await channel.send("No one entered the giveaway 😔")
                return

            users = [user async for user in reaction.users() if not user.bot]
            if not users:
                await channel.send("No valid entries for the giveaway 😔")
                return

            # Select winner(s)
            winners = []
            winner_count = min(giveaway["winners"], len(users))
            for _ in range(winner_count):
                if not users:
                    break
                winner = random.choice(users)
                winners.append(winner)
                users.remove(winner)

            # Award prizes
            for winner in winners:
                user_data = self._get_user_data(channel.guild.id, winner.id)
                user_data["balance"] += giveaway["prize"]
                self._save_user_data(channel.guild.id, winner.id, user_data)

            # Announce winners
            winners_text = ", ".join(winner.mention for winner in winners)
            embed = discord.Embed(
                title="🎉 Giveaway Ended!",
                description=f"**Prize**: {giveaway['prize']:,} 🪙\n**Winners**: {winners_text}",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await message.edit(embed=embed)
            await channel.send(f"Congratulations {winners_text}! You won {giveaway['prize']:,} 🪙 each!")

        except Exception as e:
            await channel.send(f"An error occurred while ending the giveaway: {str(e)}")
        finally:
            # Clean up
            del self.active_giveaways[channel_id][message_id]
            if not self.active_giveaways[channel_id]:
                del self.active_giveaways[channel_id]

    @app_commands.command(name="balance", description="Check your or another user's balance")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Check balance command with transaction history."""
        try:
            target = user or interaction.user
            user_data = self._get_user_data(interaction.guild_id, target.id)
            
            embed = discord.Embed(
                title="💰 Balance Overview",
                color=discord.Color.green()
            )
            
            # Main balance
            embed.add_field(
                name=f"{target.display_name}'s Balance",
                value=f"🪙 {user_data['balance']:,} coins",
                inline=False
            )
            
            # Recent transactions
            if "transactions" in user_data and user_data["transactions"]:
                transactions = []
                for tx in reversed(user_data["transactions"][-5:]):  # Show last 5
                    amount = tx["amount"]
                    symbol = "+" if amount >= 0 else "-"
                    transactions.append(
                        f"`{symbol}🪙 {abs(amount):,}` • {tx['description']}"
                    )
                embed.add_field(
                    name="📝 Recent Transactions",
                    value="\n".join(transactions),
                    inline=False
                )
            
            # Cooldowns
            cooldowns = []
            
            # Daily reward
            if "last_daily" in user_data and user_data["last_daily"]:
                last_daily = datetime.fromisoformat(user_data["last_daily"])
                if datetime.now() - last_daily < timedelta(days=1):
                    time_left = timedelta(days=1) - (datetime.now() - last_daily)
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    cooldowns.append(f"Daily: {hours}h {minutes}m")
                else:
                    cooldowns.append("Daily: ✅ Ready!")
            else:
                cooldowns.append("Daily: ✅ Ready!")
            
            # Weekly reward
            if "last_weekly" in user_data and user_data["last_weekly"]:
                last_weekly = datetime.fromisoformat(user_data["last_weekly"])
                if datetime.now() - last_weekly < timedelta(weeks=1):
                    time_left = timedelta(weeks=1) - (datetime.now() - last_weekly)
                    days = time_left.days
                    hours = int((time_left.total_seconds() % 86400) // 3600)
                    cooldowns.append(f"Weekly: {days}d {hours}h")
                else:
                    cooldowns.append("Weekly: ✅ Ready!")
            else:
                cooldowns.append("Weekly: ✅ Ready!")
            
            if cooldowns:
                embed.add_field(
                    name="⏰ Reward Cooldowns",
                    value="\n".join(cooldowns),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in balance command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching the balance. Please try again.",
                ephemeral=True
            )

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
            self._add_transaction(user_data, amount, "Daily Reward")
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
        self._add_transaction(user_data, amount, "Weekly Reward")
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

    @app_commands.command(name="giveaway", description="Start a coin giveaway")
    @app_commands.describe(
        prize="Amount of coins to give away per winner",
        duration="Duration in minutes",
        winners="Number of winners (default: 1)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway(
        self,
        interaction: discord.Interaction,
        prize: app_commands.Range[int, 100, 1000000],
        duration: app_commands.Range[int, 1, 10080],  # 1 minute to 1 week
        winners: app_commands.Range[int, 1, 10] = 1
    ):
        """Start a coin giveaway"""
        try:
            # Check if user has enough balance
            user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
            total_prize = prize * winners

            if user_data["balance"] < total_prize:
                await interaction.response.send_message(
                    f"❌ You don't have enough coins! You need 🪙 **{total_prize:,}** but have 🪙 **{user_data['balance']:,}**",
                    ephemeral=True
                )
                return

            # Check bot permissions
            if not interaction.channel.permissions_for(interaction.guild.me).add_reactions:
                await interaction.response.send_message(
                    "❌ I need permission to add reactions in this channel!",
                    ephemeral=True
                )
                return

            # Format duration for display
            duration_text = ""
            hours = duration // 60
            minutes = duration % 60
            if hours > 0:
                duration_text += f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                if duration_text:
                    duration_text += " and "
                duration_text += f"{minutes} minute{'s' if minutes != 1 else ''}"

            # Deduct coins from host
            user_data["balance"] -= total_prize
            self._add_transaction(user_data, -total_prize, f"Hosted Giveaway ({winners} winner(s))")
            if not self._save_user_data(interaction.guild_id, interaction.user.id, user_data):
                await interaction.response.send_message(
                    "❌ Failed to start giveaway due to a data error. Please try again.",
                    ephemeral=True
                )
                return

            # Create giveaway embed
            end_time = datetime.utcnow() + timedelta(minutes=duration)
            embed = discord.Embed(
                title="🎉 Coin Giveaway!",
                description=(
                    f"React with 🎉 to enter!\n\n"
                    f"**Prize per Winner**: 🪙 {prize:,}\n"
                    f"**Number of Winners**: {winners}\n"
                    f"**Total Prize Pool**: 🪙 {total_prize:,}\n"
                    f"**Duration**: {duration_text}\n"
                    f"**Ends**: {discord.utils.format_dt(end_time, 'R')}"
                ),
                color=discord.Color.blue(),
                timestamp=end_time
            )
            embed.set_footer(text=f"Hosted by {interaction.user.display_name} • Ends at {discord.utils.format_dt(end_time)}")

            await interaction.response.send_message("🎉 Creating giveaway...", ephemeral=True)
            message = await interaction.channel.send(embed=embed)
            await message.add_reaction("🎉")

            # Store giveaway data
            if interaction.channel.id not in self.active_giveaways:
                self.active_giveaways[interaction.channel.id] = {}
            
            self.active_giveaways[interaction.channel.id][message.id] = {
                "prize": prize,
                "winners": winners,
                "end_time": end_time,
                "host": interaction.user.id,
                "message_id": message.id,
                "channel_id": interaction.channel.id
            }

            # Schedule end
            await asyncio.sleep(duration * 60)
            await self._end_giveaway(interaction.channel.id, message.id)

        except Exception as e:
            self.logger.error(f"Error in giveaway command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the giveaway. Please try again.",
                ephemeral=True
            )

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
        self._add_transaction(user_data, amount, f"Received from {interaction.user.name} (Admin)")
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
        try:
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
            self._add_transaction(user_data, -amount, f"Taken by {interaction.user.name} (Admin)")
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
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command. Please try again.",
                ephemeral=True
            )
            print(f"Error in take command: {str(e)}")

    @app_commands.command(name="richest", description="View the server's wealthiest members")
    async def richest(self, interaction: discord.Interaction):
        """Show economy leaderboard with detailed stats."""
        try:
            data = self.bot.data_manager.load_data(interaction.guild_id, self.data_type)
            if not data:
                await interaction.response.send_message(
                    "❌ No economy data found for this server!",
                    ephemeral=True
                )
                return

            # Get server stats
            total_coins = sum(udata["balance"] for udata in data.values())
            active_users = len(data)
            avg_balance = total_coins // active_users if active_users > 0 else 0
            
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
                title="🏆 Wealthiest Members",
                description=(
                    f"**Server Economy Stats**\n"
                    f"Total Coins: 🪙 {total_coins:,}\n"
                    f"Active Users: 👥 {active_users:,}\n"
                    f"Average Balance: 🪙 {avg_balance:,}\n"
                ),
                color=discord.Color.gold()
            )
            
            # Leaderboard
            medals = ["🥇", "🥈", "🥉"]
            leaderboard = []
            user_position = None
            
            for idx, (user_id, balance) in enumerate(sorted_users, 1):
                user = interaction.guild.get_member(user_id)
                if user:
                    medal = medals[idx-1] if idx <= 3 else f"`{idx}.`"
                    percentage = (balance / total_coins * 100) if total_coins > 0 else 0
                    leaderboard.append(
                        f"{medal} **{user.display_name}**\n"
                        f"└ 🪙 {balance:,} coins ({percentage:.1f}% of total)"
                    )
                    
                    if user.id == interaction.user.id:
                        user_position = idx

            embed.add_field(
                name="🎖️ Top 10 Leaderboard",
                value="\n".join(leaderboard) or "No ranked users found",
                inline=False
            )
            
            # Show requester's position if not in top 10
            if interaction.user.id not in [uid for uid, _ in sorted_users]:
                user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
                all_users = sorted(
                    [(int(uid), udata["balance"]) for uid, udata in data.items()],
                    key=lambda x: x[1],
                    reverse=True
                )
                user_position = next(
                    (idx for idx, (uid, _) in enumerate(all_users, 1) if uid == interaction.user.id),
                    None
                )
                if user_position:
                    embed.add_field(
                        name="📊 Your Ranking",
                        value=f"You are ranked #{user_position} with 🪙 {user_data['balance']:,} coins",
                        inline=False
                    )
            
            embed.set_footer(text="💡 Use /balance to see your detailed stats")
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in richest command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching the leaderboard. Please try again.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Economy(bot))

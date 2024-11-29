import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from utils.data_manager import DataManager

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = DataManager()
        self.active_polls = {}
        self.active_giveaways = {}

    @app_commands.command(name="poll")
    @app_commands.describe(
        title="The title/question of your poll",
        duration="Duration in minutes (default: 5)",
        blind="Hide results until poll ends (default: False)",
        options="Options separated by | (max 5)"
    )
    async def create_poll(
        self, 
        interaction: discord.Interaction, 
        title: str,
        options: str,
        duration: Optional[int] = 5,
        blind: Optional[bool] = False
    ):
        """Create a poll with customizable options and settings"""
        # Split options and validate
        poll_options = [opt.strip() for opt in options.split("|")]
        if len(poll_options) < 2 or len(poll_options) > 5:
            await interaction.response.send_message("Please provide 2-5 options separated by |", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title=f"📊 {title}",
            description="React with the corresponding emoji to vote!",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add options to embed
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for idx, option in enumerate(poll_options):
            embed.add_field(name=f"{emojis[idx]} {option}", value="0 votes", inline=False)
        
        embed.set_footer(text=f"Poll ends in {duration} minutes | Blind voting: {blind}")
        
        # Send poll message
        await interaction.response.send_message("Creating poll...", ephemeral=True)
        poll_msg = await interaction.channel.send(embed=embed)
        
        # Add reaction options
        for idx in range(len(poll_options)):
            await poll_msg.add_reaction(emojis[idx])
        
        # Store poll data
        self.active_polls[poll_msg.id] = {
            "options": poll_options,
            "votes": {emoji: [] for emoji in emojis[:len(poll_options)]},
            "blind": blind,
            "end_time": datetime.now() + timedelta(minutes=duration)
        }
        
        # Schedule poll end
        self.bot.loop.create_task(self.end_poll(poll_msg.id, duration * 60))

    async def end_poll(self, poll_id: int, delay: int):
        """End the poll after specified duration"""
        await asyncio.sleep(delay)
        if poll_id not in self.active_polls:
            return
            
        poll_data = self.active_polls.pop(poll_id)
        channel = self.bot.get_channel(poll_id)
        if not channel:
            return
            
        try:
            message = await channel.fetch_message(poll_id)
            embed = message.embeds[0]
            
            # Update results
            results = []
            for idx, (emoji, voters) in enumerate(poll_data["votes"].items()):
                vote_count = len(voters)
                option = poll_data["options"][idx]
                results.append(f"{emoji} {option}: {vote_count} votes")
            
            embed.description = "Poll ended!\n\n" + "\n".join(results)
            await message.edit(embed=embed)
            
        except discord.NotFound:
            pass

    @app_commands.command(name="giveaway")
    @app_commands.describe(
        prize="What are you giving away?",
        duration="Duration in minutes",
        winners="Number of winners (default: 1)",
        requirement="Optional entry requirement (e.g., 'level 10')"
    )
    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: int,
        winners: Optional[int] = 1,
        requirement: Optional[str] = None
    ):
        """Start a giveaway with optional requirements"""
        if winners < 1 or winners > 10:
            await interaction.response.send_message("Number of winners must be between 1 and 10", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎉 New Giveaway!",
            description=f"**Prize:** {prize}\n\n"
                       f"React with 🎉 to enter!\n\n"
                       f"Winners: {winners}\n"
                       f"Ends: <t:{int((datetime.now() + timedelta(minutes=duration)).timestamp())}:R>",
            color=discord.Color.green()
        )
        
        if requirement:
            embed.add_field(name="Requirement", value=requirement, inline=False)
            
        await interaction.response.send_message("Creating giveaway...", ephemeral=True)
        giveaway_msg = await interaction.channel.send(embed=embed)
        await giveaway_msg.add_reaction("🎉")
        
        self.active_giveaways[giveaway_msg.id] = {
            "prize": prize,
            "winners": winners,
            "requirement": requirement,
            "end_time": datetime.now() + timedelta(minutes=duration)
        }
        
        self.bot.loop.create_task(self.end_giveaway(giveaway_msg.id, duration * 60))

    async def end_giveaway(self, giveaway_id: int, delay: int):
        """End the giveaway after specified duration"""
        await asyncio.sleep(delay)
        if giveaway_id not in self.active_giveaways:
            return
            
        giveaway_data = self.active_giveaways.pop(giveaway_id)
        channel = self.bot.get_channel(giveaway_id)
        if not channel:
            return
            
        try:
            message = await channel.fetch_message(giveaway_id)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            
            if not reaction:
                await channel.send("No one entered the giveaway!")
                return
                
            # Get all users who reacted
            users = [user async for user in reaction.users() if not user.bot]
            
            if not users:
                await channel.send("No valid entries for the giveaway!")
                return
                
            # Select winners
            winner_count = min(giveaway_data["winners"], len(users))
            winners = random.sample(users, winner_count)
            
            # Announce winners
            winner_mentions = ", ".join(winner.mention for winner in winners)
            await channel.send(
                f"🎉 Congratulations {winner_mentions}!\n"
                f"You won: **{giveaway_data['prize']}**\n"
                "Please contact the host to claim your prize!"
            )
            
        except discord.NotFound:
            pass

async def setup(bot):
    await bot.add_cog(Utility(bot))

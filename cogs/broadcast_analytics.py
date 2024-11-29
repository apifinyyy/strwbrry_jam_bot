import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from datetime import datetime, timedelta

class BroadcastAnalytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.analytics_key = "broadcast_analytics"
        self._init_data_structure()

    def _init_data_structure(self):
        """Initialize analytics data structure if it doesn't exist"""
        if not self.bot.data_manager.exists(self.analytics_key):
            self.bot.data_manager.save(self.analytics_key, {
                "broadcasts": {},
                "server_stats": {},
                "global_stats": {
                    "total_broadcasts": 0,
                    "total_reach": 0,
                    "most_active_hour": None,
                    "avg_engagement": 0
                }
            })

    def update_stats(self, guild_id: str, success: bool, member_count: int):
        """Update broadcast statistics"""
        analytics = self.bot.data_manager.load(self.analytics_key)
        
        # Update server stats
        if guild_id not in analytics["server_stats"]:
            analytics["server_stats"][guild_id] = {
                "total_received": 0,
                "successful": 0,
                "failed": 0,
                "last_success": None,
                "members_reached": 0
            }
        
        server_stats = analytics["server_stats"][guild_id]
        server_stats["total_received"] += 1
        if success:
            server_stats["successful"] += 1
            server_stats["last_success"] = datetime.utcnow().isoformat()
            server_stats["members_reached"] += member_count
        else:
            server_stats["failed"] += 1

        # Update global stats
        analytics["global_stats"]["total_broadcasts"] += 1
        if success:
            analytics["global_stats"]["total_reach"] += member_count

        # Update hourly stats
        hour = str(datetime.utcnow().hour)
        if "hourly_stats" not in analytics["global_stats"]:
            analytics["global_stats"]["hourly_stats"] = {str(i): 0 for i in range(24)}
        analytics["global_stats"]["hourly_stats"][hour] += 1
        
        # Calculate most active hour
        most_active = max(analytics["global_stats"]["hourly_stats"].items(), 
                         key=lambda x: x[1])[0]
        analytics["global_stats"]["most_active_hour"] = most_active

        # Calculate average engagement
        active_servers = sum(1 for s in analytics["server_stats"].values() 
                           if s["successful"] > 0)
        if active_servers > 0:
            total_engagement = sum(s["successful"] for s in 
                                 analytics["server_stats"].values())
            analytics["global_stats"]["avg_engagement"] = total_engagement / active_servers

        self.bot.data_manager.save(self.analytics_key, analytics)

    @app_commands.command(
        name="broadcaststats",
        description="View broadcast statistics"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def broadcast_stats(
        self,
        interaction: discord.Interaction,
        timeframe: Optional[str] = "all"  # all, day, week, month
    ):
        """View broadcast statistics"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "❌ Only the bot owner can view broadcast statistics.",
                ephemeral=True
            )
            return

        analytics = self.bot.data_manager.load(self.analytics_key)
        global_stats = analytics["global_stats"]

        # Calculate timeframe
        cutoff = None
        if timeframe == "day":
            cutoff = datetime.utcnow() - timedelta(days=1)
        elif timeframe == "week":
            cutoff = datetime.utcnow() - timedelta(weeks=1)
        elif timeframe == "month":
            cutoff = datetime.utcnow() - timedelta(days=30)

        # Create stats embed
        embed = discord.Embed(
            title="📊 Broadcast Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Add overview stats
        embed.add_field(
            name="Overview",
            value=f"📨 Total Broadcasts: {global_stats['total_broadcasts']}\n"
                  f"👥 Total Reach: {global_stats['total_reach']} members\n"
                  f"📊 Average Engagement: {global_stats['avg_engagement']:.1f} broadcasts/server",
            inline=False
        )

        # Add timing stats
        if global_stats["most_active_hour"] is not None:
            hour = int(global_stats["most_active_hour"])
            embed.add_field(
                name="Timing",
                value=f"🕒 Most Active Hour: {hour:02d}:00 UTC",
                inline=False
            )

        # Add top 5 most engaged servers
        top_servers = sorted(
            analytics["server_stats"].items(),
            key=lambda x: x[1]["successful"],
            reverse=True
        )[:5]

        if top_servers:
            server_details = ""
            for guild_id, stats in top_servers:
                guild = self.bot.get_guild(int(guild_id))
                guild_name = guild.name if guild else f"Guild {guild_id}"
                server_details += (f"📨 {guild_name}: {stats['successful']} broadcasts\n"
                                 f"👥 {stats['members_reached']} members reached\n")

            embed.add_field(
                name="Top 5 Most Engaged Servers",
                value=server_details,
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BroadcastAnalytics(bot))

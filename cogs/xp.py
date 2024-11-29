import discord
from discord import app_commands
from discord.ext import commands
import random

class XPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_xp_config(self, guild_id: int):
        guild_id = str(guild_id)
        if guild_id not in self.bot.data.get('config', {}):
            self.bot.data['config'][guild_id] = {}
        
        config = self.bot.data['config'][guild_id]
        return {
            'chat_xp': config.get('chat_xp', {'min': 15, 'max': 25}),
            'voice_xp': config.get('voice_xp', {'per_minute': 10}),
            'enabled_channels': config.get('xp_channels', []),
            'enabled_categories': config.get('xp_categories', []),
            'blocked_users': config.get('xp_blocked_users', [])
        }

    def is_channel_enabled(self, channel: discord.TextChannel | discord.VoiceChannel) -> bool:
        config = self.get_xp_config(channel.guild.id)
        return (
            str(channel.id) in config['enabled_channels'] or
            str(channel.category_id) in config['enabled_categories']
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if not self.is_channel_enabled(message.channel):
            return

        config = self.get_xp_config(message.guild.id)
        if str(message.author.id) in config['blocked_users']:
            return

        user_id = str(message.author.id)
        if user_id not in self.bot.data['users']:
            self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

        xp_gain = random.randint(
            config['chat_xp']['min'],
            config['chat_xp']['max']
        )
        self.bot.data['users'][user_id]['chat_xp'] += xp_gain
        self.bot.save_data()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if after.channel and self.is_channel_enabled(after.channel):
            self.voice_states[member.id] = discord.utils.utcnow()
        elif before.channel and member.id in self.voice_states:
            start_time = self.voice_states.pop(member.id)
            duration = (discord.utils.utcnow() - start_time).total_seconds() / 60

            config = self.get_xp_config(member.guild.id)
            if str(member.id) in config['blocked_users']:
                return

            user_id = str(member.id)
            if user_id not in self.bot.data['users']:
                self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

            xp_gain = int(duration * config['voice_xp']['per_minute'])
            self.bot.data['users'][user_id]['voice_xp'] += xp_gain
            self.bot.save_data()

    @app_commands.command(name="givexp", description="Give XP to a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def give_xp(self, interaction: discord.Interaction, user: discord.User, amount: int, xp_type: str):
        if xp_type not in ['chat', 'voice']:
            await interaction.response.send_message("Invalid XP type. Use 'chat' or 'voice'.", ephemeral=True)
            return

        user_id = str(user.id)
        if user_id not in self.bot.data['users']:
            self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

        self.bot.data['users'][user_id][f'{xp_type}_xp'] += amount
        self.bot.save_data()
        await interaction.response.send_message(f"Gave {amount} {xp_type} XP to {user.name}")

    @app_commands.command(name="takexp", description="Take XP from a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def take_xp(self, interaction: discord.Interaction, user: discord.User, amount: int, xp_type: str):
        if xp_type not in ['chat', 'voice']:
            await interaction.response.send_message("Invalid XP type. Use 'chat' or 'voice'.", ephemeral=True)
            return

        user_id = str(user.id)
        if user_id not in self.bot.data['users']:
            self.bot.data['users'][user_id] = {'chat_xp': 0, 'voice_xp': 0}

        xp_key = f'{xp_type}_xp'
        self.bot.data['users'][user_id][xp_key] = max(0, self.bot.data['users'][user_id][xp_key] - amount)
        self.bot.save_data()
        await interaction.response.send_message(f"Took {amount} {xp_type} XP from {user.name}")

    @app_commands.command(name="blockxp", description="Block a user from gaining XP")
    @app_commands.checks.has_permissions(administrator=True)
    async def block_xp(self, interaction: discord.Interaction, user: discord.User):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.bot.data['config']:
            self.bot.data['config'][guild_id] = {}
        
        if 'xp_blocked_users' not in self.bot.data['config'][guild_id]:
            self.bot.data['config'][guild_id]['xp_blocked_users'] = []

        user_id = str(user.id)
        if user_id not in self.bot.data['config'][guild_id]['xp_blocked_users']:
            self.bot.data['config'][guild_id]['xp_blocked_users'].append(user_id)
            self.bot.save_data()
            await interaction.response.send_message(f"{user.name} has been blocked from gaining XP")
        else:
            await interaction.response.send_message(f"{user.name} is already blocked from gaining XP", ephemeral=True)

    @app_commands.command(name="unblockxp", description="Unblock a user from gaining XP")
    @app_commands.checks.has_permissions(administrator=True)
    async def unblock_xp(self, interaction: discord.Interaction, user: discord.User):
        guild_id = str(interaction.guild.id)
        if guild_id in self.bot.data['config']:
            user_id = str(user.id)
            if user_id in self.bot.data['config'][guild_id].get('xp_blocked_users', []):
                self.bot.data['config'][guild_id]['xp_blocked_users'].remove(user_id)
                self.bot.save_data()
                await interaction.response.send_message(f"{user.name} has been unblocked from gaining XP")
                return

        await interaction.response.send_message(f"{user.name} is not blocked from gaining XP", ephemeral=True)

    @app_commands.command(name="leaderboard", description="View XP leaderboard")
    @app_commands.choices(board_type=[
        app_commands.Choice(name="Chat XP", value="top"),
        app_commands.Choice(name="Voice XP", value="vctop")
    ])
    async def leaderboard(self, interaction: discord.Interaction, board_type: str):
        """View the XP leaderboard for either chat or voice XP."""
        try:
            # Defer the response since we'll be making API calls
            await interaction.response.defer()

            if board_type not in ['top', 'vctop']:
                await interaction.followup.send(
                    "Invalid leaderboard type. Use 'top' for chat XP or 'vctop' for voice XP.",
                    ephemeral=True
                )
                return

            xp_type = 'voice_xp' if board_type == 'vctop' else 'chat_xp'
            
            try:
                data = self.bot.data_manager.load_data(interaction.guild_id, "xp")
            except FileNotFoundError:
                await interaction.followup.send(
                    "❌ No XP data found for this server!",
                    ephemeral=True
                )
                return

            if not data:
                await interaction.followup.send(
                    "❌ No XP data found for this server!",
                    ephemeral=True
                )
                return

            # Sort users by XP
            sorted_users = sorted(
                [(uid, udata.get(xp_type, 0)) for uid, udata in data.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]  # Top 10

            if not sorted_users:
                await interaction.followup.send(
                    "❌ No users have earned XP yet!",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"{'🎤 Voice' if board_type == 'vctop' else '💬 Chat'} XP Leaderboard",
                color=discord.Color.blue()
            )

            for i, (user_id, xp) in enumerate(sorted_users, 1):
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👑"
                    embed.add_field(
                        name=f"{medal} #{i} - {user.name}",
                        value=f"**{xp:,}** XP",
                        inline=False
                    )
                except discord.NotFound:
                    continue
                except Exception as e:
                    print(f"Error fetching user {user_id}: {e}")
                    continue

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in leaderboard command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the leaderboard. Please try again later.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(XPSystem(bot))

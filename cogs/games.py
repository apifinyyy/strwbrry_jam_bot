import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import random
import asyncio
import operator
from datetime import datetime, timedelta
import string
import logging
import json
from collections import defaultdict

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games_key = "games_config"
        self.default_config = {
            "rps_amount": 50,          # Amount for Rock Paper Scissors
            "trivia_amount": {         # Amount for Trivia based on difficulty
                "easy": 50,
                "medium": 100,
                "hard": 200
            },
            "math_amount": {           # Amount for Math based on difficulty
                "easy": 50,
                "medium": 100,
                "hard": 150
            },
            "chat_amount": 25,         # Amount for Chat challenges
            "gamble_amount": {         # Amount for gambling
                "min": 50,            # Minimum bet
                "max": 1000          # Maximum bet
            },
            "gamble_win_chance": 0.4,  # 40% chance to win
            "gamble_multiplier": 2.0,  # Win multiplier
            "cooldown": 60,            # Cooldown between games in seconds
            "max_daily_rewards": 500,  # Maximum daily rewards from games
            "enabled_games": ["rps", "trivia", "math", "chat", "gamble"],  # List of enabled games
            "chat_timeout": 60,        # Timeout for chat challenges in seconds
            "chat_min_length": 5,      # Minimum length for chat challenge text
            "chat_max_length": 10      # Maximum length for chat challenge text
        }
        
        # Initialize logging
        self.logger = logging.getLogger('strwbrry_jam.games')
        self.logger.setLevel(logging.INFO)
        
        # Initialize game stats tracking
        self.game_stats = defaultdict(lambda: {
            "games_played": 0,
            "coins_won": 0,
            "last_played": None,
            "daily_earnings": 0,
            "last_daily_reset": datetime.now().date()
        })
        
        self.trivia_questions = {
            "easy": [
                {"question": "What is the capital of France?", "answer": "Paris"},
                {"question": "What is 2 + 2?", "answer": "4"},
                {"question": "What planet is known as the Red Planet?", "answer": "Mars"},
                {"question": "What is the largest ocean on Earth?", "answer": "Pacific"},
                {"question": "How many continents are there?", "answer": "7"},
                {"question": "What is the chemical symbol for water?", "answer": "H2O"},
                {"question": "What is the opposite of hot?", "answer": "Cold"},
                {"question": "What color is a banana?", "answer": "Yellow"},
                {"question": "How many days are in a week?", "answer": "7"},
                {"question": "What season comes after summer?", "answer": "Fall"}
            ],
            "medium": [
                {"question": "Who wrote Romeo and Juliet?", "answer": "William Shakespeare"},
                {"question": "What is the largest planet in our solar system?", "answer": "Jupiter"},
                {"question": "What is the chemical symbol for gold?", "answer": "Au"},
                {"question": "What year did World War II end?", "answer": "1945"},
                {"question": "Who painted the Mona Lisa?", "answer": "Leonardo da Vinci"},
                {"question": "What is the capital of Japan?", "answer": "Tokyo"},
                {"question": "What is the hardest natural substance on Earth?", "answer": "Diamond"},
                {"question": "Who is known as the father of computers?", "answer": "Charles Babbage"},
                {"question": "What is the speed of light?", "answer": "299792458"},
                {"question": "What is the chemical symbol for silver?", "answer": "Ag"}
            ],
            "hard": [
                {"question": "What is the atomic number of Uranium?", "answer": "92"},
                {"question": "Who discovered penicillin?", "answer": "Alexander Fleming"},
                {"question": "What is the longest river in the world?", "answer": "Nile"},
                {"question": "What year was the first computer mouse invented?", "answer": "1964"},
                {"question": "Who wrote 'The Art of War'?", "answer": "Sun Tzu"},
                {"question": "What is the rarest blood type?", "answer": "AB Negative"},
                {"question": "What is the smallest prime number greater than 100?", "answer": "101"},
                {"question": "What is the half-life of Carbon-14?", "answer": "5730"},
                {"question": "Who discovered the theory of relativity?", "answer": "Albert Einstein"},
                {"question": "What is the deepest point in the ocean?", "answer": "Challenger Deep"}
            ]
        }
        self.math_operators = {
            '+': operator.add,
            '-': operator.sub,
            '*': operator.mul,
            '/': operator.truediv
        }
        self.active_chat_challenges = {}
        self.last_game = {}
        self.active_games = set()  # Track currently active game sessions

    async def get_config(self, guild_id: str) -> dict:
        """Get the games configuration for a guild with error handling"""
        try:
            config = self.bot.data_manager.load_data(guild_id, "games")
            if not config or self.games_key not in config:
                config = {self.games_key: {guild_id: self.default_config.copy()}}
                self.bot.data_manager.save_data(guild_id, "games", config)
            return config[self.games_key][guild_id]
        except Exception as e:
            self.logger.error(f"Error loading game config: {e}")
            return self.default_config.copy()

    async def update_config(self, guild_id: str, setting: str, value: any) -> bool:
        """Update a specific game configuration setting with validation"""
        try:
            config = self.bot.data_manager.load_data(guild_id, "games")
            if not config or self.games_key not in config:
                config = {self.games_key: {guild_id: self.default_config.copy()}}
            
            # Validate setting exists
            if setting not in config[self.games_key][guild_id]:
                raise ValueError(f"Invalid setting: {setting}")
            
            config[self.games_key][guild_id][setting] = value
            self.bot.data_manager.save_data(guild_id, "games", config)
            return True
        except Exception as e:
            self.logger.error(f"Error updating game config: {e}")
            return False

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        """Get user's economy data with error handling"""
        try:
            data = self.bot.data_manager.load_data(guild_id, "economy")
            if str(user_id) not in data:
                data[str(user_id)] = {
                    "balance": self.bot.config_manager.get_value(guild_id, "economy", "starting_balance", default=0),
                    "inventory": [],
                    "transaction_history": []
                }
                self.bot.data_manager.save_data(guild_id, "economy", data)
            return data[str(user_id)]
        except Exception as e:
            self.logger.error(f"Error getting user data: {e}")
            return {"balance": 0, "inventory": [], "transaction_history": []}

    def _save_user_data(self, guild_id: int, user_id: int, user_data: dict) -> bool:
        """Save user's economy data with validation"""
        try:
            if "balance" not in user_data or not isinstance(user_data["balance"], (int, float)):
                raise ValueError("Invalid user data: missing or invalid balance")
            
            data = self.bot.data_manager.load_data(guild_id, "economy")
            data[str(user_id)] = user_data
            self.bot.data_manager.save_data(guild_id, "economy", data)
            return True
        except Exception as e:
            self.logger.error(f"Error saving user data: {e}")
            return False

    async def update_user_stats(self, guild_id: int, user_id: int, game: str, coins_won: int):
        """Update user's game statistics"""
        try:
            stats = self.game_stats[f"{guild_id}:{user_id}"]
            
            # Reset daily earnings if it's a new day
            current_date = datetime.now().date()
            if stats["last_daily_reset"] != current_date:
                stats["daily_earnings"] = 0
                stats["last_daily_reset"] = current_date
            
            stats["games_played"] += 1
            stats["coins_won"] += coins_won
            stats["last_played"] = datetime.now()
            stats["daily_earnings"] += coins_won
            
            # Log significant wins
            if coins_won >= 100:
                self.logger.info(f"User {user_id} won {coins_won} coins in {game}")
                
        except Exception as e:
            self.logger.error(f"Error updating user stats: {e}")

    async def check_game_eligibility(self, interaction: discord.Interaction, game: str) -> tuple[bool, str]:
        """Check if user is eligible to play a game"""
        try:
            config = await self.get_config(str(interaction.guild_id))
            
            # Check if game is enabled
            if game not in config["enabled_games"]:
                return False, f"❌ {game.upper()} is currently disabled on this server."
            
            # Check if user is already in a game
            user_key = f"{interaction.guild_id}:{interaction.user.id}"
            if user_key in self.active_games:
                return False, "❌ You're already in an active game! Please finish or wait for it to timeout."
            
            # Check cooldown
            if user_key in self.last_game:
                time_diff = (datetime.now() - self.last_game[user_key]).total_seconds()
                if time_diff < config["cooldown"]:
                    remaining = int(config["cooldown"] - time_diff)
                    return False, f"⏰ Please wait {remaining} seconds before playing again!"
            
            # Check daily earnings limit
            stats = self.game_stats[user_key]
            if stats["daily_earnings"] >= config["max_daily_rewards"]:
                return False, f"🎮 You've reached the maximum daily earnings of 🪙 {config['max_daily_rewards']}!"
            
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Error checking game eligibility: {e}")
            return False, "❌ An error occurred while checking game eligibility."

    @app_commands.command(name="gamestats", description="View your gaming statistics")
    async def game_stats_command(self, interaction: discord.Interaction):
        """View your gaming statistics"""
        try:
            stats = self.game_stats[f"{interaction.guild_id}:{interaction.user.id}"]
            config = await self.get_config(str(interaction.guild_id))
            
            embed = discord.Embed(
                title="🎮 Your Gaming Stats",
                color=discord.Color.blue()
            )
            
            # General Stats
            embed.add_field(
                name="📊 Overall Stats",
                value=(
                    f"Games Played: {stats['games_played']}\n"
                    f"Total Coins Won: 🪙 {stats['coins_won']:,}\n"
                    f"Average Win: 🪙 {stats['coins_won'] / max(1, stats['games_played']):,.1f}"
                ),
                inline=False
            )
            
            # Daily Progress
            daily_remaining = config["max_daily_rewards"] - stats["daily_earnings"]
            embed.add_field(
                name="📅 Daily Progress",
                value=(
                    f"Today's Earnings: 🪙 {stats['daily_earnings']:,}\n"
                    f"Remaining Today: 🪙 {daily_remaining:,}\n"
                    f"Progress: {(stats['daily_earnings'] / config['max_daily_rewards'] * 100):,.1f}%"
                ),
                inline=False
            )
            
            # Last Played
            if stats["last_played"]:
                embed.add_field(
                    name="⏰ Last Played",
                    value=f"{discord.utils.format_dt(stats['last_played'], 'R')}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error displaying game stats: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching your game stats.",
                ephemeral=True
            )

    @app_commands.command(name="rps", description="Play Rock Paper Scissors")
    @app_commands.checks.cooldown(1, 30)  # 30 seconds cooldown
    async def rps(self, interaction: discord.Interaction, choice: str):
        """Play Rock Paper Scissors for coins."""
        try:
            eligible, message = await self.check_game_eligibility(interaction, "rps")
            if not eligible:
                await interaction.response.send_message(message, ephemeral=True)
                return

            choices = ["rock", "paper", "scissors"]
            if choice.lower() not in choices:
                await interaction.response.send_message(
                    "❌ Invalid choice! Choose rock, paper, or scissors.",
                    ephemeral=True
                )
                return

            bot_choice = random.choice(choices)
            user_choice = choice.lower()

            # Game logic
            if bot_choice == user_choice:
                result = "It's a tie! 🤝"
                winnings = 0
            elif (
                (user_choice == "rock" and bot_choice == "scissors") or
                (user_choice == "paper" and bot_choice == "rock") or
                (user_choice == "scissors" and bot_choice == "paper")
            ):
                result = "You win! 🎉"
                winnings = self.get_winnable_amount(interaction.guild_id, "rps")
            else:
                result = "You lose! 😢"
                winnings = 0

            # Update user balance
            user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
            if winnings > 0:
                user_data["balance"] += winnings
                self._save_user_data(interaction.guild_id, interaction.user.id, user_data)

            embed = discord.Embed(
                title="🎮 Rock Paper Scissors",
                description=f"You chose: {user_choice}\nI chose: {bot_choice}\n\n{result}",
                color=discord.Color.blue()
            )
            if winnings > 0:
                embed.add_field(
                    name="Winnings",
                    value=f"🪙 +{winnings:,} coins"
                )
                embed.add_field(
                    name="New Balance",
                    value=f"🪙 {user_data['balance']:,} coins"
                )
            
            await interaction.response.send_message(embed=embed)
            
            # Update user stats
            await self.update_user_stats(interaction.guild_id, interaction.user.id, "rps", winnings)
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while playing RPS. Please try again.",
                ephemeral=True
            )
            print(f"Error in RPS command: {str(e)}")

    @rps.error
    async def rps_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ You can play RPS again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.",
                ephemeral=True
            )

    @app_commands.command(name="trivia", description="Play a trivia game")
    @app_commands.describe(
        difficulty="Choose difficulty level (easy/medium/hard)"
    )
    async def trivia(
        self,
        interaction: discord.Interaction,
        difficulty: Literal["easy", "medium", "hard"] = "medium"
    ):
        """Play a trivia game for coins."""
        eligible, message = await self.check_game_eligibility(interaction, "trivia")
        if not eligible:
            await interaction.response.send_message(message, ephemeral=True)
            return

        config = await self.get_config(str(interaction.guild_id))
        
        # Select random question based on difficulty
        question_data = random.choice(self.trivia_questions[difficulty])
        
        # Add user to active games
        user_key = f"{interaction.guild_id}:{interaction.user.id}"
        self.active_games.add(user_key)
        
        try:
            embed = discord.Embed(
                title="🎯 Trivia Time!",
                description=f"**Difficulty**: {difficulty.capitalize()}\n**Question**: {question_data['question']}\n\nYou have 30 seconds to answer!",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Reward",
                value=f"🪙 {config['trivia_amount'][difficulty]} coins"
            )
            
            await interaction.response.send_message(embed=embed)

            def check(m):
                # Allow any message from the user in the same channel
                return (
                    m.author.id == interaction.user.id and 
                    m.channel.id == interaction.channel_id and
                    not m.author.bot
                )

            try:
                message = await self.bot.wait_for('message', timeout=30.0, check=check)
                
                # Normalize both answers for comparison
                user_answer = message.content.lower().strip()
                correct_answer = question_data['answer'].lower().strip()
                
                # Case-insensitive answer checking
                if user_answer == correct_answer:
                    # Award coins based on difficulty
                    reward = config['trivia_amount'][difficulty]
                    
                    try:
                        # Get economy cog
                        economy_cog = self.bot.get_cog('Economy')
                        if not economy_cog:
                            await interaction.channel.send("❌ Economy system is not available right now. Please try again later.")
                            return
                            
                        # Get and update user data
                        user_data = economy_cog._get_user_data(interaction.guild_id, interaction.user.id)
                        user_data['balance'] += reward
                        economy_cog._save_user_data(interaction.guild_id, interaction.user.id, user_data)
                        
                        await interaction.channel.send(
                            f"✅ Correct! You won {reward} 🪙\n"
                            f"Your answer: {message.content}"
                        )
                    except Exception as e:
                        self.logger.error(f"Error handling trivia reward: {e}")
                        await interaction.channel.send("❌ Error giving reward. The answer was correct but there was a problem with the economy system.")
                else:
                    # Show both answers for debugging
                    await interaction.channel.send(
                        f"❌ Wrong answer!\n"
                        f"Your answer: '{message.content}'\n"
                        f"Correct answer: '{question_data['answer']}'"
                    )
                
            except asyncio.TimeoutError:
                await interaction.channel.send("⏰ Time's up! The correct answer was: " + question_data['answer'])

            # Update cooldown with correct user key
            self.last_game[user_key] = datetime.now()

            # Update user stats if they won
            if message.content.lower().strip() == question_data['answer'].lower().strip():
                await self.update_user_stats(interaction.guild_id, interaction.user.id, "trivia", config['trivia_amount'][difficulty])
                
        finally:
            # Always remove user from active games, even if an error occurs
            self.active_games.discard(user_key)

    @trivia.error
    async def trivia_error(self, interaction: discord.Interaction, error):
        # Log the full error for debugging
        self.logger.error(f"Trivia command error: {str(error)}")
        
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ You can play trivia again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            # More detailed error message
            await interaction.response.send_message(
                f"❌ An error occurred while processing the command: {str(error)}",
                ephemeral=True
            )

    @app_commands.command(name="math", description="Solve a math problem")
    @app_commands.describe(
        difficulty="Choose difficulty level (easy/medium/hard)"
    )
    async def math(
        self,
        interaction: discord.Interaction,
        difficulty: Literal["easy", "medium", "hard"] = "medium"
    ):
        """Solve a math problem for coins."""
        eligible, message = await self.check_game_eligibility(interaction, "math")
        if not eligible:
            await interaction.response.send_message(message, ephemeral=True)
            return

        # Generate random numbers and operator
        num1 = random.randint(1, 100)
        num2 = random.randint(1, 100)
        operator = random.choice(['+', '-', '*'])  # Removed division to avoid decimal answers
        
        # Calculate answer
        answer = self.math_operators[operator](num1, num2)
        
        # Create problem string
        problem = f"{num1} {operator} {num2}"
        
        embed = discord.Embed(
            title="🎮 Math Challenge",
            description=f"**Difficulty**: {difficulty.capitalize()}\n**Problem**: {problem}\n\nYou have 30 seconds to answer!",
            color=discord.Color.blue()
        )
        config = await self.get_config(str(interaction.guild_id))
        embed.add_field(
            name="Reward",
            value=f"🪙 {config['math_amount'][difficulty]} coins"
        )
        
        await interaction.response.send_message(embed=embed)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            message = await self.bot.wait_for('message', timeout=30.0, check=check)
            user_answer = float(message.content)
        except asyncio.TimeoutError:
            await interaction.followup.send(f'⏰ Time\'s up! The correct answer was: {answer}')
            return
        except ValueError:
            await interaction.followup.send('🤔 That\'s not a valid number!')
            return

        if abs(user_answer - answer) < 0.01:  # Using small difference to account for floating point
            # Award coins based on difficulty
            reward = config['math_amount'][difficulty]
            
            user_data = await self.bot.economy_cog._get_user_data(interaction.guild_id, interaction.user.id)
            user_data['balance'] += reward
            await self.bot.economy_cog._save_user_data(interaction.guild_id, interaction.user.id, user_data)
            
            await interaction.channel.send(
                f"✅ Correct! You won {reward} 🪙\n"
                f"Your answer: {message.content}"
            )
        else:
            await interaction.channel.send(
                f"❌ Wrong answer!\n"
                f"Your answer: {message.content}\n"
                f"Correct answer: {answer}"
            )
                
        # Update cooldown
        self.last_game[str(interaction.user.id)] = datetime.now()

        # Update user stats
        await self.update_user_stats(interaction.guild_id, interaction.user.id, "math", config['math_amount'][difficulty])

    @math.error
    async def math_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ You can play math again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.",
                ephemeral=True
            )

    @app_commands.command(name="startchallenge", description="Start a random chat challenge")
    @app_commands.describe(
        difficulty="Choose difficulty level (easy/medium/hard)",
        timeout="Challenge timeout in seconds (30-300)"
    )
    async def start_chat_challenge(
        self,
        interaction: discord.Interaction,
        difficulty: Literal["easy", "medium", "hard"] = "medium",
        timeout: app_commands.Range[int, 30, 300] = 60
    ):
        """Start a random chat challenge for coins."""
        try:
            # Check if game is enabled
            config = await self.get_config(str(interaction.guild_id))
            if "chat" not in config["enabled_games"]:
                await interaction.response.send_message(
                    "❌ Chat challenges are currently disabled on this server.",
                    ephemeral=True
                )
                return

            # Check for active challenge
            if interaction.channel.id in self.active_chat_challenges:
                await interaction.response.send_message(
                    "🚫 There's already an active challenge in this channel!",
                    ephemeral=True
                )
                return

            # Generate challenge text based on difficulty
            length_ranges = {
                "easy": (5, 7),
                "medium": (8, 12),
                "hard": (13, 15)
            }
            min_len, max_len = length_ranges[difficulty]
            length = random.randint(min_len, max_len)
            
            # Generate text with appropriate character set
            char_sets = {
                "easy": string.ascii_lowercase + string.digits,
                "medium": string.ascii_letters + string.digits,
                "hard": string.ascii_letters + string.digits + string.punctuation
            }
            chars = char_sets[difficulty]
            challenge_text = ''.join(random.choice(chars) for _ in range(length))
            
            # Calculate reward based on difficulty
            rewards = {
                "easy": config["chat_amount"],
                "medium": config["chat_amount"] * 2,
                "hard": config["chat_amount"] * 3
            }
            reward = rewards[difficulty]

            # Create challenge embed
            embed = discord.Embed(
                title="🎉 Chat Challenge!",
                description=(
                    f"**Difficulty**: {difficulty.capitalize()}\n"
                    f"**Time Limit**: {timeout} seconds\n\n"
                    f"First person to type this text exactly wins:\n"
                    f"```{challenge_text}```"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Prize: 🪙 {reward:,} coins")
            
            # Store challenge data
            self.active_chat_challenges[interaction.channel.id] = {
                'text': challenge_text,
                'winnings': reward,
                'start_time': datetime.now(),
                'timeout': timeout,
                'difficulty': difficulty
            }
            
            # Send challenge message
            await interaction.response.send_message(embed=embed)
            
            # Start timeout task
            self.bot.loop.create_task(
                self._handle_challenge_timeout(interaction.channel.id, timeout)
            )
            
        except Exception as e:
            self.logger.error(f"Error in start chat challenge command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while starting the chat challenge. Please try again.",
                ephemeral=True
            )

    async def _handle_challenge_timeout(self, channel_id: int, timeout: int):
        """Handle challenge timeout"""
        try:
            await asyncio.sleep(timeout)
            if channel_id in self.active_chat_challenges:
                challenge = self.active_chat_challenges[channel_id]
                channel = self.bot.get_channel(channel_id)
                if channel:
                    embed = discord.Embed(
                        title="⏰ Challenge Expired!",
                        description=(
                            f"Time's up! Nobody completed the challenge.\n"
                            f"The text was: `{challenge['text']}`"
                        ),
                        color=discord.Color.red()
                    )
                    await channel.send(embed=embed)
                del self.active_chat_challenges[channel_id]
        except Exception as e:
            self.logger.error(f"Error in challenge timeout handler: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle chat challenge responses"""
        try:
            # Ignore bot messages and DMs
            if message.author.bot or not message.guild:
                return

            # Check for active challenge
            if message.channel.id not in self.active_chat_challenges:
                return

            challenge = self.active_chat_challenges[message.channel.id]
            
            # Check if challenge has timed out
            time_elapsed = (datetime.now() - challenge['start_time']).total_seconds()
            if time_elapsed > challenge['timeout']:
                del self.active_chat_challenges[message.channel.id]
                return

            # Check answer
            if message.content == challenge['text']:
                try:
                    # Get economy cog
                    economy_cog = self.bot.get_cog('Economy')
                    if not economy_cog:
                        await message.channel.send("❌ Economy system is not available right now. Please try again later.")
                        return
                        
                    # Get and update user data
                    user_data = economy_cog._get_user_data(message.guild.id, message.author.id)
                    user_data["balance"] += challenge['winnings']
                    if not economy_cog._save_user_data(message.guild.id, message.author.id, user_data):
                        await message.channel.send("❌ Error saving reward. Please contact an admin.")
                        return
                    
                    # Create success embed
                    embed = discord.Embed(
                        title="🎉 Challenge Complete!",
                        description=(
                            f"**Winner**: {message.author.mention}\n"
                            f"**Difficulty**: {challenge['difficulty'].capitalize()}\n"
                            f"**Time**: {time_elapsed:.1f}s"
                        ),
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="Reward",
                        value=f"🪙 {challenge['winnings']:,} coins"
                    )
                    embed.add_field(
                        name="New Balance",
                        value=f"🪙 {user_data['balance']:,} coins"
                    )
                    
                    await message.channel.send(embed=embed)
                    
                    # Update user stats
                    await self.update_user_stats(
                        message.guild.id,
                        message.author.id,
                        "chat",
                        challenge['winnings']
                    )
                    
                finally:
                    # Always clean up the challenge
                    del self.active_chat_challenges[message.channel.id]
            
        except Exception as e:
            self.logger.error(f"Error in chat challenge handler: {e}")
            try:
                await message.channel.send(
                    "❌ An error occurred while processing the challenge. The challenge has been cancelled."
                )
            finally:
                # Ensure cleanup happens even if error message fails
                if message.channel.id in self.active_chat_challenges:
                    del self.active_chat_challenges[message.channel.id]

    @app_commands.command(name="gamble", description="Gamble your coins")
    @app_commands.describe(
        amount="Amount of coins to gamble (50-1000)",
    )
    async def gamble(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 50, 1000]
    ):
        """Gamble your coins."""
        try:
            # Check eligibility
            eligible, message = await self.check_game_eligibility(interaction, "gamble")
            if not eligible:
                await interaction.response.send_message(message, ephemeral=True)
                return

            # Get user data and config
            config = await self.get_config(str(interaction.guild_id))
            user_data = self._get_user_data(interaction.guild_id, interaction.user.id)

            # Check bet limits
            if amount < config["gamble_amount"]["min"] or amount > config["gamble_amount"]["max"]:
                await interaction.response.send_message(
                    f"🎲 Bet must be between 🪙 {config['gamble_amount']['min']} and 🪙 {config['gamble_amount']['max']}!",
                    ephemeral=True
                )
                return

            # Check if user has enough coins
            if user_data["balance"] < amount:
                await interaction.response.send_message(
                    f"❌ You don't have enough coins! You need 🪙 **{amount:,}** but have 🪙 **{user_data['balance']:,}**",
                    ephemeral=True
                )
                return

            # Add user to active games
            user_key = f"{interaction.guild_id}:{interaction.user.id}"
            self.active_games.add(user_key)

            try:
                # Roll the dice!
                win = random.random() < config["gamble_win_chance"]
                
                if win:
                    winnings = int(amount * config["gamble_multiplier"])
                    user_data["balance"] += winnings - amount  # Subtract bet, add winnings
                    result = f"🎉 You won! +{winnings:,} coins"
                    color = discord.Color.green()
                    net_gain = winnings - amount
                else:
                    user_data["balance"] -= amount
                    result = f"😢 You lost! -{amount:,} coins"
                    color = discord.Color.red()
                    net_gain = -amount

                # Save user data
                if not self._save_user_data(interaction.guild_id, interaction.user.id, user_data):
                    await interaction.response.send_message(
                        "❌ Error saving game results. Please try again.",
                        ephemeral=True
                    )
                    return

                # Create result embed
                embed = discord.Embed(
                    title="🎲 Gambling Results",
                    description=result,
                    color=color
                )
                embed.add_field(
                    name="Bet Amount",
                    value=f"🪙 {amount:,}",
                    inline=True
                )
                embed.add_field(
                    name="Net Gain/Loss",
                    value=f"🪙 {net_gain:,}",
                    inline=True
                )
                embed.add_field(
                    name="New Balance",
                    value=f"🪙 {user_data['balance']:,}",
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed)
                
                # Update user stats
                await self.update_user_stats(interaction.guild_id, interaction.user.id, "gamble", net_gain)
                
                # Update last game time
                self.last_game[user_key] = datetime.now()

            finally:
                # Always remove user from active games
                self.active_games.discard(user_key)
            
        except Exception as e:
            self.logger.error(f"Error in gamble command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while gambling. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="gameconfig", description="Configure game settings")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        setting="The setting to configure",
        value="The new value to set"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="RPS Reward", value="rps_amount"),
        app_commands.Choice(name="Trivia Reward", value="trivia_amount"),
        app_commands.Choice(name="Math Reward", value="math_amount"),
        app_commands.Choice(name="Chat Reward", value="chat_amount"),
        app_commands.Choice(name="Game Cooldown", value="cooldown"),
        app_commands.Choice(name="Max Daily Rewards", value="max_daily_rewards"),
        app_commands.Choice(name="Enable Gambling", value="enable_gambling"),
        app_commands.Choice(name="Disable Gambling", value="disable_gambling")
    ])
    async def game_config(
        self,
        interaction: discord.Interaction,
        setting: str,
        value: int = None
    ):
        """Configure game settings"""
        guild_id = str(interaction.guild_id)
        
        if setting in ["enable_gambling", "disable_gambling"]:
            config = await self.get_config(guild_id)
            if setting == "enable_gambling" and "gamble" not in config["enabled_games"]:
                config["enabled_games"].append("gamble")
                await self.update_config(guild_id, "enabled_games", config["enabled_games"])
                await interaction.response.send_message(
                    "✅ Gambling has been enabled for this server",
                    ephemeral=True
                )
            elif setting == "disable_gambling" and "gamble" in config["enabled_games"]:
                config["enabled_games"].remove("gamble")
                await self.update_config(guild_id, "enabled_games", config["enabled_games"])
                await interaction.response.send_message(
                    "✅ Gambling has been disabled for this server",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ No changes needed - gambling was already in the desired state",
                    ephemeral=True
                )
            return
        
        if value is None:
            await interaction.response.send_message(
                "❌ A value is required for this setting",
                ephemeral=True
            )
            return
        
        if setting.endswith("_amount") and (value < 1 or value > 1000):
            await interaction.response.send_message(
                "❌ Reward amounts must be between 1 and 1000",
                ephemeral=True
            )
            return
        
        if setting == "cooldown" and (value < 0 or value > 3600):
            await interaction.response.send_message(
                "❌ Cooldown must be between 0 and 3600 seconds",
                ephemeral=True
            )
            return
        
        if setting == "max_daily_rewards" and (value < 100 or value > 10000):
            await interaction.response.send_message(
                "❌ Maximum daily rewards must be between 100 and 10000",
                ephemeral=True
            )
            return
        
        await self.update_config(guild_id, setting, value)
        await interaction.response.send_message(
            f"✅ Updated {setting} to {value}",
            ephemeral=True
        )

    @app_commands.command(
        name="togglegame",
        description="Enable or disable specific games"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_game(
        self,
        interaction: discord.Interaction,
        game: Literal["rps", "trivia", "math", "chat", "gamble"],
        enabled: bool
    ):
        """Enable or disable specific games"""
        guild_id = str(interaction.guild_id)
        config = await self.get_config(guild_id)
        
        if enabled and game not in config["enabled_games"]:
            config["enabled_games"].append(game)
        elif not enabled and game in config["enabled_games"]:
            config["enabled_games"].remove(game)
        
        await self.update_config(guild_id, "enabled_games", config["enabled_games"])
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            f"✅ {game.upper()} has been {status}",
            ephemeral=True
        )

    @app_commands.command(
        name="viewgameconfig",
        description="View current game configuration"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def view_game_config(self, interaction: discord.Interaction):
        """View current game configuration"""
        guild_id = str(interaction.guild_id)
        config = await self.get_config(guild_id)
        
        embed = discord.Embed(
            title="🎮 Game Configuration",
            color=discord.Color.blue()
        )
        
        # Reward Amounts
        rewards = (
            f"🎲 RPS: {config['rps_amount']} coins\n"
            f"❓ Trivia:\n  Easy: {config['trivia_amount']['easy']} coins\n  Medium: {config['trivia_amount']['medium']} coins\n  Hard: {config['trivia_amount']['hard']} coins\n"
            f"🔢 Math:\n  Easy: {config['math_amount']['easy']} coins\n  Medium: {config['math_amount']['medium']} coins\n  Hard: {config['math_amount']['hard']} coins\n"
            f"💬 Chat: {config['chat_amount']} coins"
        )
        embed.add_field(
            name="💰 Reward Amounts",
            value=rewards,
            inline=False
        )
        
        # Game Status
        enabled_games = "\n".join(f"✅ {game.upper()}" for game in config["enabled_games"])
        disabled_games = "\n".join(f"❌ {game.upper()}" for game in ["rps", "trivia", "math", "chat", "gamble"] if game not in config["enabled_games"])
        
        status = enabled_games
        if disabled_games:
            status += "\n\n" + disabled_games
        
        embed.add_field(
            name="🎮 Game Status",
            value=status,
            inline=False
        )
        
        # Other Settings
        embed.add_field(
            name="⚙️ Other Settings",
            value=(
                f"⏰ Game Cooldown: {config['cooldown']} seconds\n"
                f"💰 Max Daily Rewards: {config['max_daily_rewards']} coins"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Use /gameconfig to modify these settings")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help_games", description="View information about available games")
    async def help_games(self, interaction: discord.Interaction):
        """Show help information for games"""
        try:
            config = await self.get_config(str(interaction.guild_id))
            
            embed = discord.Embed(
                title="🎮 Games Help",
                description="Here's everything you need to know about our games!",
                color=discord.Color.blue()
            )
            
            # Available Games
            games_info = ""
            if "rps" in config["enabled_games"]:
                games_info += "🎲 **Rock Paper Scissors**\n`/rps [choice]`\n- Choose rock, paper, or scissors\n- Win to earn coins!\n\n"
            if "trivia" in config["enabled_games"]:
                games_info += "❓ **Trivia**\n`/trivia [difficulty]`\n- Test your knowledge\n- Different rewards for each difficulty\n\n"
            if "math" in config["enabled_games"]:
                games_info += "🔢 **Math Challenge**\n`/math [difficulty]`\n- Solve math problems\n- Harder problems = bigger rewards\n\n"
            if "chat" in config["enabled_games"]:
                games_info += "💬 **Chat Challenge**\n`/startchallenge`\n- Type the shown text first to win\n- Quick typing = quick coins!\n\n"
            if "gamble" in config["enabled_games"]:
                games_info += "🎲 **Gamble**\n`/gamble [amount]`\n- Bet your coins\n- Win big or lose it all!\n\n"
            
            embed.add_field(
                name="🎯 Available Games",
                value=games_info or "No games are currently enabled",
                inline=False
            )
            
            # Game Rules
            embed.add_field(
                name="📜 Game Rules",
                value=(
                    f"• Cooldown between games: {config['cooldown']} seconds\n"
                    f"• Maximum daily earnings: 🪙 {config['max_daily_rewards']:,} coins\n"
                    "• Each game has different rewards based on difficulty\n"
                    "• You can't play multiple games at once\n"
                    "• Use `/gamestats` to track your progress"
                ),
                inline=False
            )
            
            # Tips
            embed.add_field(
                name="💡 Tips",
                value=(
                    "• Try harder difficulties for bigger rewards\n"
                    "• Keep an eye on your daily earnings limit\n"
                    "• Practice makes perfect!\n"
                    "• Join chat challenges for quick coins"
                ),
                inline=False
            )
            
            embed.set_footer(text="Have fun and play responsibly! 🌟")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error displaying games help: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching the help information.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Games(bot))

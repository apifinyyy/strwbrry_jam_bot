import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import json
import operator
import string
from typing import Optional

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trivia_questions = [
            {"question": "What is the capital of France?", "answer": "Paris"},
            {"question": "What is 2 + 2?", "answer": "4"},
            {"question": "Who wrote Romeo and Juliet?", "answer": "William Shakespeare"},
            {"question": "What is the largest planet in our solar system?", "answer": "Jupiter"},
            {"question": "What is the chemical symbol for gold?", "answer": "Au"},
            {"question": "What year did World War II end?", "answer": "1945"},
            {"question": "Who painted the Mona Lisa?", "answer": "Leonardo da Vinci"},
            {"question": "What is the capital of Japan?", "answer": "Tokyo"},
            {"question": "What is the hardest natural substance on Earth?", "answer": "Diamond"},
            {"question": "Who is known as the father of computers?", "answer": "Charles Babbage"}
        ]
        self.active_chat_challenges = {}
        self.math_operators = {
            '+': operator.add,
            '-': operator.sub,
            '*': operator.mul,
            '/': operator.truediv
        }

    def _get_user_data(self, guild_id: int, user_id: int) -> dict:
        """Get user's economy data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, "economy")
        except FileNotFoundError:
            data = {}
            
        if str(user_id) not in data:
            data[str(user_id)] = {
                "balance": self.bot.config_manager.get_value(guild_id, "economy", "starting_balance", default=0),
                "inventory": []
            }
            self.bot.data_manager.save_data(guild_id, "economy", data)
        return data[str(user_id)]

    def _save_user_data(self, guild_id: int, user_id: int, user_data: dict) -> None:
        """Save user's economy data for a specific guild."""
        try:
            data = self.bot.data_manager.load_data(guild_id, "economy")
        except FileNotFoundError:
            data = {}
        data[str(user_id)] = user_data
        self.bot.data_manager.save_data(guild_id, "economy", data)

    def get_winnable_amount(self, guild_id: int, game_type: str) -> int:
        """Get the winnable amount for a game type from config."""
        return self.bot.config_manager.get_value(
            guild_id,
            "games",
            f"{game_type}_amount",
            default=50
        )

    @app_commands.command(name="rps", description="Play Rock Paper Scissors")
    @app_commands.checks.cooldown(1, 30)  # 30 seconds cooldown
    async def rps(self, interaction: discord.Interaction, choice: str):
        """Play Rock Paper Scissors for coins."""
        try:
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
    @app_commands.checks.cooldown(1, 30)  # 30 seconds cooldown
    async def trivia(self, interaction: discord.Interaction):
        """Play a trivia game for coins."""
        try:
            question = random.choice(self.trivia_questions)
            embed = discord.Embed(
                title="🎮 Trivia",
                description=question['question'],
                color=discord.Color.blue()
            )
            embed.set_footer(text="You have 30 seconds to answer!")
            
            await interaction.response.send_message(embed=embed)

            def check(m):
                return m.author == interaction.user and m.channel == interaction.channel

            try:
                message = await self.bot.wait_for('message', timeout=30.0, check=check)
            except asyncio.TimeoutError:
                await interaction.followup.send('⏰ Time\'s up! The correct answer was: ' + question['answer'])
                return

            if message.content.lower() == question['answer'].lower():
                winnings = self.get_winnable_amount(interaction.guild_id, "trivia")
                user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
                user_data["balance"] += winnings
                self._save_user_data(interaction.guild_id, interaction.user.id, user_data)
                
                embed = discord.Embed(
                    title="🎉 Correct Answer!",
                    description=f"You won {winnings} coins!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="New Balance",
                    value=f"🪙 {user_data['balance']:,} coins"
                )
                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="😢 Wrong Answer!",
                    description=f"The correct answer was: {question['answer']}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while playing trivia. Please try again.",
                ephemeral=True
            )
            print(f"Error in trivia command: {str(e)}")

    @trivia.error
    async def trivia_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ You can play trivia again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.",
                ephemeral=True
            )

    @app_commands.command(name="math", description="Solve a math problem")
    @app_commands.checks.cooldown(1, 30)  # 30 seconds cooldown
    async def math(self, interaction: discord.Interaction):
        """Solve a math problem for coins."""
        try:
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
                description=f"Solve this problem: {problem}",
                color=discord.Color.blue()
            )
            embed.set_footer(text="You have 30 seconds to answer!")
            
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
                winnings = self.get_winnable_amount(interaction.guild_id, "math")
                user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
                user_data["balance"] += winnings
                self._save_user_data(interaction.guild_id, interaction.user.id, user_data)
                
                embed = discord.Embed(
                    title="🎉 Correct Answer!",
                    description=f"You won {winnings} coins!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="New Balance",
                    value=f"🪙 {user_data['balance']:,} coins"
                )
                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="😢 Wrong Answer!",
                    description=f"The correct answer was: {answer}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while playing math. Please try again.",
                ephemeral=True
            )
            print(f"Error in math command: {str(e)}")

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
    @app_commands.checks.has_permissions(administrator=True)
    async def start_chat_challenge(self, interaction: discord.Interaction):
        """Start a random chat challenge for coins."""
        try:
            if interaction.channel_id in self.active_chat_challenges:
                await interaction.response.send_message(
                    "🚫 There's already an active challenge in this channel!",
                    ephemeral=True
                )
                return

            # Generate random string
            length = random.randint(5, 10)
            chars = string.ascii_letters + string.digits
            challenge_text = ''.join(random.choice(chars) for _ in range(length))
            
            embed = discord.Embed(
                title="🎉 Chat Challenge!",
                description=f"First person to type this text wins:\n`{challenge_text}`",
                color=discord.Color.gold()
            )
            
            winnings = self.get_winnable_amount(interaction.guild_id, "chat")
            embed.set_footer(text=f"Prize: {winnings} coins")
            
            self.active_chat_challenges[interaction.channel_id] = {
                'text': challenge_text,
                'winnings': winnings
            }
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while starting the chat challenge. Please try again.",
                ephemeral=True
            )
            print(f"Error in start chat challenge command: {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if message.channel.id in self.active_chat_challenges:
            challenge = self.active_chat_challenges[message.channel.id]
            if message.content == challenge['text']:
                # Winner found!
                user_data = self._get_user_data(message.guild.id, message.author.id)
                user_data["balance"] += challenge['winnings']
                self._save_user_data(message.guild.id, message.author.id, user_data)
                
                embed = discord.Embed(
                    title="🎉 Challenge Complete!",
                    description=f"{message.author.mention} won {challenge['winnings']} coins!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="New Balance",
                    value=f"🪙 {user_data['balance']:,} coins"
                )
                
                await message.channel.send(embed=embed)
                del self.active_chat_challenges[message.channel.id]

    @app_commands.command(name="gamble", description="Gamble your coins")
    @app_commands.checks.cooldown(1, 30)  # 30 seconds cooldown
    async def gamble(self, interaction: discord.Interaction, amount: int):
        """Gamble your coins."""
        try:
            user_data = self._get_user_data(interaction.guild_id, interaction.user.id)
            if amount <= 0:
                await interaction.response.send_message(
                    "🤔 You must gamble at least 1 coin!",
                    ephemeral=True
                )
                return

            if user_data["balance"] < amount:
                await interaction.response.send_message(
                    "🚫 You don't have enough coins!",
                    ephemeral=True
                )
                return

            # 40% chance to win
            if random.random() < 0.4:
                winnings = amount * 2
                user_data["balance"] += amount
                result = f"You won! +{winnings} coins"
                color = discord.Color.green()
            else:
                user_data["balance"] -= amount
                result = f"You lost! -{amount} coins"
                color = discord.Color.red()

            self._save_user_data(interaction.guild_id, interaction.user.id, user_data)
            
            embed = discord.Embed(
                title="🎲 Gambling Results",
                description=result,
                color=color
            )
            embed.add_field(
                name="New Balance",
                value=f"🪙 {user_data['balance']:,} coins"
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while gambling. Please try again.",
                ephemeral=True
            )
            print(f"Error in gamble command: {str(e)}")

    @gamble.error
    async def gamble_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ You can gamble again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Games(bot))

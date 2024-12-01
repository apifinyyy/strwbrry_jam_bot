import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import logging
from datetime import datetime

class TemplateCog(commands.Cog):
    """
    Template cog for Strwbrry Jam Bot.
    Replace this description with your cog's purpose.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('template')  # Replace 'template' with your cog name
        
        # Add any additional initialization here
        # Example: self.config = {}
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Optional: Called when the cog is loaded and ready"""
        self.logger.info(f"{self.__class__.__name__} cog ready!")
        
    # Command example with app_commands (Slash Commands)
    @app_commands.command(name="template")
    @app_commands.describe(
        param="Example parameter"
    )
    async def template_command(
        self,
        interaction: discord.Interaction,
        param: str
    ):
        """Template command - Replace with your command's purpose"""
        try:
            # Your command logic here
            await interaction.response.send_message(f"Template command executed with param: {param}")
            
        except Exception as e:
            self.logger.error(f"Error in template command: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while executing the command.",
                ephemeral=True
            )
    
    # Event listener example
    @commands.Cog.listener()
    async def on_message(self, message):
        """Optional: Example event listener"""
        if message.author.bot:
            return
            
        # Your event handling logic here
    
    # Error handler example
    @template_command.error
    async def template_error(self, interaction: discord.Interaction, error):
        """Optional: Error handler for the template command"""
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command!",
                ephemeral=True
            )
        else:
            self.logger.error(f"Unexpected error in template command: {error}", exc_info=True)
            await interaction.response.send_message(
                "An unexpected error occurred.",
                ephemeral=True
            )

async def setup(bot):
    """Required: Setup function for loading the cog"""
    await bot.add_cog(TemplateCog(bot))

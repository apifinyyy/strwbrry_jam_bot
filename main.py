import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
from utils.config_manager import config_manager
from utils.data_manager import DataManager, data_manager
import logging
import asyncio

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')  # Will be None if not set, triggering SQLite fallback

class UtilityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=commands.when_mentioned_or('/'), intents=intents)
        
        # Store managers as bot attributes
        self.config_manager = config_manager
        self.data_manager = DataManager(database_url=DATABASE_URL)
        self.logger = logging.getLogger("discord")
        
        # Create necessary directories
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
    async def setup_hook(self):
        """Load all cogs when the bot starts."""
        # Initialize database connection
        print("Initializing database connection...")
        try:
            if not DATABASE_URL:
                print("No database URL found in environment variables, falling back to SQLite...")
            await self.data_manager.connect_to_database()
            print("Database connection established successfully!")
            
            print("Initializing database...")
            await self.data_manager.initialize_database()  # Initialize tables first
            
            print("Starting to load cogs...")
            # List of cogs to skip
            skip_cogs = {'profile'}  # Skip profile.py as its functionality is in social.py
            
            for cog_file in Path("cogs").glob("*.py"):
                if cog_file.stem != "__init__" and cog_file.stem not in skip_cogs:
                    try:
                        print(f"Loading {cog_file.stem}...")
                        await self.load_extension(f"cogs.{cog_file.stem}")
                        print(f"Successfully loaded {cog_file.stem}")
                    except Exception as e:
                        print(f"Failed to load {cog_file.stem}: {str(e)}")
                        self.logger.error(f"Failed to load {cog_file.stem}: {str(e)}")
        except Exception as e:
            print(f"Failed to initialize database: {str(e)}")
            self.logger.error(f"Failed to initialize database: {str(e)}")
            return
        
        print("Syncing commands...")
        try:
            await self.tree.sync()
            print("Commands synced successfully!")
        except Exception as e:
            print(f"Failed to sync commands: {str(e)}")
            self.logger.error(f"Failed to sync commands: {str(e)}")
            
    async def on_ready(self):
        """Called when the bot is ready."""
        print(f'{self.user} has connected to Discord!')
        print(f'Serving {len(self.guilds)} guilds')
        
    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild."""
        # Initialize default configuration
        self.config_manager.reset_guild_config(guild.id)
        print(f"Joined new guild: {guild.name} (ID: {guild.id})")
    
    async def on_guild_remove(self, guild):
        """Called when the bot is removed from a guild."""
        print(f"Left guild: {guild.name} (ID: {guild.id})")
        # Optionally clean up guild data
        # Uncomment if you want to delete guild data when bot leaves
        # guild_path = Path(f"data/{guild.id}")
        # if guild_path.exists():
        #     shutil.rmtree(guild_path)
    
    async def close(self):
        """Cleanup before shutdown"""
        print("Shutting down bot...")
        
        # Close database connection
        try:
            await self.data_manager.close()
            print("Database connection closed successfully")
        except Exception as e:
            print(f"Error closing database connection: {str(e)}")
            self.logger.error(f"Error closing database connection: {str(e)}")
        
        # Cancel all tasks
        print("Cancelling background tasks...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        print(f"Found {len(tasks)} tasks to cancel...")
        
        # Close aiohttp sessions in cogs
        for cog in self.cogs.values():
            if hasattr(cog, 'session') and cog.session:
                await cog.session.close()
        
        # Clean up database
        try:
            await self.data_manager.cleanup()
            print("Database cleaned up successfully")
        except Exception as e:
            print(f"Error cleaning up database: {str(e)}")
            self.logger.error(f"Error cleaning up database: {str(e)}")
        
        await super().close()
        
    def run(self):
        """Run the bot with the token from environment variables."""
        super().run(TOKEN, reconnect=True)

if __name__ == "__main__":
    bot = UtilityBot()
    bot.run()

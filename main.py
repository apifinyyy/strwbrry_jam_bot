import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
from utils.config_manager import config_manager
from utils.data_manager import DataManager, data_manager
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s', handlers=[
    logging.FileHandler("logs/bot.log"),
    logging.StreamHandler()
])

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))  # Default to 0 if not set
DATABASE_URL = os.getenv('DATABASE_URL')  # Will be None if not set, triggering SQLite fallback

class UtilityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=commands.when_mentioned_or('/'), intents=intents)
        
        # Store managers as bot attributes
        self.config_manager = config_manager
        self.data_manager = DataManager(database_url=DATABASE_URL)
        self.logger = logging.getLogger("discord")
        self.owner_id = OWNER_ID
        
        # Create necessary directories
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
    async def setup_hook(self):
        """Load all cogs when the bot starts."""
        # Initialize database connection
        self.logger.info("Initializing database connection...")
        try:
            if not DATABASE_URL:
                self.logger.warning("No database URL found in environment variables, falling back to SQLite...")
            await self.data_manager.connect_to_database()
            self.logger.info("Database connection established successfully!")
            
            self.logger.info("Initializing database...")
            await self.data_manager.initialize_database()  # Initialize tables first
            
            self.logger.info("Starting to load cogs...")
            
            # Get all .py files in the cogs directory
            cogs_dir = Path("cogs")
            cogs_dir.mkdir(exist_ok=True)  # Create cogs directory if it doesn't exist
            
            # Skip these files when loading cogs
            skip_files = {"__init__.py", "template_cog.py"}
            
            # Load each cog
            for cog_file in cogs_dir.glob("*.py"):
                if cog_file.name in skip_files:
                    continue
                    
                try:
                    cog_name = f"cogs.{cog_file.stem}"
                    await self.load_extension(cog_name)
                    self.logger.info(f"Successfully loaded cog: {cog_name}")
                except Exception as e:
                    self.logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
            
            self.logger.info("Finished loading cogs!")
            
        except Exception as e:
            self.logger.error(f"Error during setup: {e}", exc_info=True)
            raise
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info("------")
        
        # Sync commands with Discord
        try:
            self.logger.info("Syncing commands with Discord...")
            await self.tree.sync()
            self.logger.info("Successfully synced commands!")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}", exc_info=True)
    
    async def reload_cog(self, cog_name: str) -> bool:
        """Reload a specific cog."""
        try:
            await self.reload_extension(f"cogs.{cog_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload cog {cog_name}: {e}", exc_info=True)
            return False
    
    async def load_cog(self, cog_name: str) -> bool:
        """Load a specific cog."""
        try:
            await self.load_extension(f"cogs.{cog_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
            return False
    
    async def unload_cog(self, cog_name: str) -> bool:
        """Unload a specific cog."""
        try:
            await self.unload_extension(f"cogs.{cog_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unload cog {cog_name}: {e}", exc_info=True)
            return False
    
    async def is_owner(self, user: discord.User) -> bool:
        """Check if a user is the bot owner."""
        if self.owner_id:
            return user.id == self.owner_id
        return await super().is_owner(user)
        
    async def on_guild_join(self, guild):
        """Called when the bot joins a new guild."""
        # Initialize default configuration
        self.config_manager.reset_guild_config(guild.id)
        self.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
    
    async def on_guild_remove(self, guild):
        """Called when the bot is removed from a guild."""
        self.logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        # Optionally clean up guild data
        # Uncomment if you want to delete guild data when bot leaves
        # guild_path = Path(f"data/{guild.id}")
        # if guild_path.exists():
        #     shutil.rmtree(guild_path)
    
    async def close(self):
        """Cleanup before shutdown"""
        self.logger.info("Shutting down bot...")
        
        # Close database connection
        try:
            await self.data_manager.close()
            self.logger.info("Database connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {str(e)}")
        
        # Cancel all tasks
        self.logger.info("Cancelling background tasks...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        self.logger.info(f"Found {len(tasks)} tasks to cancel...")
        
        # Close aiohttp sessions in cogs
        for cog in self.cogs.values():
            if hasattr(cog, 'session') and cog.session:
                await cog.session.close()
        
        # Clean up database
        try:
            await self.data_manager.cleanup()
            self.logger.info("Database cleaned up successfully")
        except Exception as e:
            self.logger.error(f"Error cleaning up database: {str(e)}")
        
        await super().close()
        
    def run(self):
        """Run the bot with the token from environment variables."""
        super().run(TOKEN, reconnect=True)

if __name__ == "__main__":
    bot = UtilityBot()
    bot.run()

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
from utils.config_manager import config_manager
from utils.data_manager import data_manager

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

class UtilityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=commands.when_mentioned_or('/'), intents=intents)
        
        # Store managers as bot attributes
        self.config_manager = config_manager
        self.data_manager = data_manager
        
        # Create necessary directories
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
    async def setup_hook(self):
        """Load all cogs when the bot starts."""
        print("Starting to load cogs...")
        for cog_file in Path("cogs").glob("*.py"):
            if cog_file.stem != "__init__":
                try:
                    print(f"Loading {cog_file.stem}...")
                    await self.load_extension(f"cogs.{cog_file.stem}")
                    print(f"Successfully loaded {cog_file.stem}")
                except Exception as e:
                    print(f"Failed to load {cog_file.stem}: {str(e)}")
                    
        print("Syncing commands...")
        try:
            await self.tree.sync()
            print("Commands synced successfully!")
        except Exception as e:
            print(f"Failed to sync commands: {str(e)}")
    
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
    
    def run(self):
        """Run the bot with the token from environment variables."""
        super().run(TOKEN, reconnect=True)

if __name__ == "__main__":
    bot = UtilityBot()
    bot.run()

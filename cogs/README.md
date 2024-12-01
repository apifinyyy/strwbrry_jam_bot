# 🍓 Strwbrry Jam Bot - Cog Development Guide

## 📚 Table of Contents
- [Overview](#overview)
- [Documentation](#documentation)
- [Quick Start](#quick-start)
- [Core Cogs](#core-cogs)
- [Cog Development](#cog-development)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## 🌟 Overview
Strwbrry Jam Bot is a feature-rich Discord bot built with modularity in mind. The bot uses a cog system for organizing features, making it easy to add, modify, or remove functionality.

## 📖 Documentation
- **[Official Documentation](https://github.com/apifinyyy/strwbrry_jam_bot/wiki)**
- **[Support Server](https://discord.gg/XcH8JmGaHZ)**
- **[Developer Guide](../docs/DEVELOPER_GUIDE.md)**
- **[API Reference](../docs/API.md)**

## ⚡ Quick Start
1. Create a new cog from template:
   ```bash
   cp template_cog.py mycog.py
   ```
2. Place your cog in the `cogs` directory
3. The bot will automatically load it on startup

## 🔧 Core Cogs

### Moderation (`moderation.py`)
Advanced moderation system with:
- Warning system with severity levels
- Automated punishments
- Warning appeals and redemption
- Configurable auto-moderation
- Role hierarchy respect
- Detailed logging

Commands:
```
/moderation warn    - Warn a user (severity 1-3)
/moderation ban     - Ban a user with optional message deletion
/moderation mute    - Temporarily mute a user
/moderation clean   - Bulk delete messages
/moderation setup   - Configure moderation settings
```

### Logging (`logging.py`)
Comprehensive logging system featuring:
- Message tracking (edit/delete)
- Member events (join/leave)
- Role changes
- Voice activity
- Channel modifications

Commands:
```
/logsetup          - Configure logging settings
/logstatus         - View current logging configuration
```

### Auto-Roles (`auto_roles.py`)
Automated role management:
- Join roles
- Level-based roles
- Reaction roles
- Temporary roles
- Role persistence

### Economy (`economy.py`)
Virtual economy system:
- Currency management
- Shop system
- Trading
- Gambling mini-games
- Daily rewards

### XP System (`xp.py`)
Experience and leveling system:
- Message-based XP
- Voice activity XP
- Role rewards
- Leaderboards
- Custom level-up messages

## 🛠️ Cog Development

### Basic Structure
```python
from discord.ext import commands
import discord

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.__class__.__name__} cog loaded")
        
    @commands.hybrid_command()
    async def mycommand(self, ctx):
        """Command description"""
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

### Command Types

#### Regular Commands
```python
@app_commands.command(name="greet")
@app_commands.describe(user="User to greet")
async def greet(self, interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"Hello {user.mention}!")
```

#### Group Commands
```python
@commands.group(name="settings")
async def settings_group(self):
    pass

@settings_group.command(name="view")
async def settings_view(self, interaction: discord.Interaction):
    pass
```

#### Context Menu Commands
```python
@app_commands.context_menu(name="User Info")
async def user_info(self, interaction: discord.Interaction, user: discord.Member):
    pass
```

## 🔌 Bot Features

### Logger System
```python
# Basic logging
self.logger.info("Normal operation")
self.logger.warning("Something might be wrong")
self.logger.error("Something went wrong", exc_info=True)

# Child loggers
feature_logger = self.logger.getChild('feature')
feature_logger.info("Feature specific log")
```

### Data Management
```python
# Save data
await self.bot.data_manager.save("table_name", "key", data)

# Load data
data = await self.bot.data_manager.load("table_name", "key")

# Check existence
exists = await self.bot.data_manager.exists("table_name", "key")
```

### Configuration System
```python
# Get guild config
config = await self.bot.config_manager.get_guild_config(guild_id)

# Update config
await self.bot.config_manager.set_guild_config(guild_id, new_config)
```

### Rich Embeds
```python
embed = discord.Embed(
    title="Title",
    description="Description",
    color=discord.Color.blue()
)
embed.add_field(name="Field", value="Value", inline=True)
embed.set_footer(text="Footer")
await interaction.response.send_message(embed=embed)
```

## ✨ Best Practices

### 1. Error Handling
```python
try:
    await some_operation()
except discord.Forbidden:
    await interaction.response.send_message(
        "❌ I don't have permission to do that!",
        ephemeral=True
    )
except Exception as e:
    self.logger.error(f"Error: {e}", exc_info=True)
    await interaction.response.send_message(
        "❌ An error occurred",
        ephemeral=True
    )
```

### 2. Permission Checks
```python
@app_commands.checks.has_permissions(manage_messages=True)
async def mod_command(self, interaction: discord.Interaction):
    pass
```

### 3. Rate Limiting
```python
@app_commands.checks.cooldown(1, 60)  # Once per minute
async def limited_command(self, interaction: discord.Interaction):
    pass
```

### 4. User Feedback
- Use emojis for status (✅ ❌ ⚠️)
- Make error messages helpful
- Use ephemeral messages when appropriate
- Include progress indicators for long operations

## 🔍 Troubleshooting

### Common Issues
1. **Cog Not Loading**
   - Check for syntax errors
   - Verify setup function exists
   - Check console for error messages

2. **Commands Not Showing**
   - Ensure proper command decoration
   - Check guild/global command sync
   - Verify bot permissions

3. **Permission Errors**
   - Check bot role hierarchy
   - Verify necessary intents
   - Check command permission settings

### Debug Tools
```python
# Command error logging
@command.error
async def command_error(self, interaction: discord.Interaction, error):
    self.logger.error(f"Command error: {error}", exc_info=True)
```

## 🤝 Contributing
1. Fork the repository
2. Create a feature branch
3. Follow coding standards
4. Add tests if applicable
5. Submit a pull request

For more information, join our [Discord server](https://discord.gg/XcH8JmGaHZ) or check the [documentation](https://github.com/apifinyyy/strwbrry_jam_bot/wiki).

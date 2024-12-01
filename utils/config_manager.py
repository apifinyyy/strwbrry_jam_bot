from typing import Any, Dict, Optional, List
from .data_manager import data_manager
import asyncio
import logging

class ConfigManager:
    """Manages per-server configuration settings."""
    
    DEFAULT_CONFIG = {
        "prefix": "/",
        "economy": {
            "daily_amount": 100,
            "weekly_amount": 1000,
            "starting_balance": 0,
            "max_balance": 1000000,
            "shop_roles": {},  # role_id: price
        },
        "xp": {
            "chat_min": 15,
            "chat_max": 25,
            "voice_per_minute": 10,
            "xp_channels": [],
            "role_rewards": {},  # xp_amount: role_id
            "blocked_users": []
        },
        "games": {
            "rps_amount": 50,
            "trivia_amount": 100,
            "math_amount": 75,
            "chat_amount": 150,
            "cooldown": 30  # seconds
        },
        "tickets": {
            "category_id": None,
            "archive_category_id": None,
            "support_roles": [],
            "max_open": 1
        },
        "logging": {
            "channel_id": None,
            "events": {
                "messages": True,
                "joins": True,
                "leaves": True,
                "roles": True,
                "channels": True,
                "voice": True
            }
        },
        "welcome": {
            "channel_id": None,
            "message": "Welcome {user} to {server}! You are member #{count}!",
            "goodbye_message": "Goodbye {user}! We'll miss you!",
            "goodbye_channel_id": None,
            "dm_welcome": False
        },
        "auto_roles": {
            "join_roles": [],
            "role_messages": {},
            "auto_roles": {},
            "auto_remove_roles": {}
        }
    }

    def __init__(self):
        """Initialize the config manager."""
        self.data_type = "config"
        self.cache: Dict[int, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    def get_guild_config(self, guild_id: str) -> dict:
        """Get guild configuration with defaults"""
        try:
            if guild_id not in self.cache:
                config = data_manager.load("guild_configs", guild_id) or self.DEFAULT_CONFIG.copy()
                self.cache[guild_id] = config
                asyncio.create_task(self.save_guild_config(guild_id, config))
            return self.cache[guild_id]
        except Exception as e:
            self.logger.error(f"Error loading guild config: {e}", exc_info=True)
            return self.DEFAULT_CONFIG.copy()

    async def save_guild_config(self, guild_id: str, config: dict):
        """Save guild-specific configuration"""
        try:
            self.cache[guild_id] = config
            await data_manager.save("guild_configs", guild_id, config)
        except Exception as e:
            self.logger.error(f"Error saving guild config: {e}")

    def set_guild_config(self, guild_id: int, config: Dict[str, Any]) -> None:
        """Set the configuration for a specific guild."""
        self.cache[guild_id] = config
        asyncio.create_task(self.save_guild_config(str(guild_id), config))

    def get_value(self, guild_id: int, *keys: str, default: Any = None) -> Any:
        """Get a specific configuration value using dot notation."""
        config = self.get_guild_config(str(guild_id))
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def set_value(self, guild_id: int, value: Any, *keys: str) -> None:
        """Set a specific configuration value using dot notation."""
        config = self.get_guild_config(str(guild_id))
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        self.set_guild_config(guild_id, config)

    def reset_guild_config(self, guild_id: int) -> None:
        """Reset a guild's configuration to default."""
        config = self.DEFAULT_CONFIG.copy()
        self.set_guild_config(guild_id, config)

# Default instance
config_manager = ConfigManager()

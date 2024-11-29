import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import asyncio
import asyncpg

class DataManagerError(Exception):
    """Base exception class for DataManager errors."""
    pass

class DataManager:
    def __init__(self, base_path: str = "data", database_url: str = "postgresql://user:password@localhost/database"):
        """Initialize the data manager with a base path for data storage."""
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.cache: Dict[str, Dict[str, Any]] = {}
        
        # Setup logging
        self.logger = logging.getLogger("DataManager")
        self.logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Add file handler
        fh = logging.FileHandler(log_dir / "data_manager.log")
        fh.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(fh)
        
        # Initialize database connection
        self.database_url = database_url
        self.pool = None
    
    async def connect_to_database(self):
        """Connect to the PostgreSQL database."""
        try:
            self.pool = await asyncpg.create_pool(self.database_url)
            await self.initialize_database()
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise DataManagerError(f"Failed to connect to database: {e}")
    
    async def initialize_database(self):
        """Initialize the database tables if they don't exist."""
        async with self.pool.acquire() as conn:
            # Create guild_settings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    poll_settings JSONB DEFAULT '{}'::jsonb,
                    giveaway_settings JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            # Create user_profiles table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id BIGINT PRIMARY KEY,
                    profile_data JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            self.logger.info("Database tables initialized")
    
    def _get_guild_path(self, guild_id: int) -> Path:
        """Get the path for a specific guild's data directory."""
        try:
            guild_path = self.base_path / str(guild_id)
            guild_path.mkdir(exist_ok=True)
            return guild_path
        except Exception as e:
            self.logger.error(f"Failed to create guild directory for {guild_id}: {e}")
            raise DataManagerError(f"Failed to create guild directory: {e}")
    
    def _get_file_path(self, guild_id: int, data_type: str) -> Path:
        """Get the path for a specific data file."""
        return self._get_guild_path(guild_id) / f"{data_type}.json"
    
    def _backup_file(self, file_path: Path) -> None:
        """Create a backup of a data file."""
        if file_path.exists():
            backup_dir = self.base_path / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{file_path.stem}_{timestamp}.json"
            try:
                with open(file_path, 'r', encoding='utf-8') as source:
                    with open(backup_path, 'w', encoding='utf-8') as target:
                        target.write(source.read())
                self.logger.info(f"Created backup: {backup_path}")
            except Exception as e:
                self.logger.error(f"Failed to create backup for {file_path}: {e}")
    
    def load_data(self, guild_id: int, data_type: str) -> Dict[str, Any]:
        """Load data for a specific guild and data type."""
        cache_key = f"{guild_id}_{data_type}"
        if cache_key in self.cache:
            return self.cache[cache_key].copy()
        
        file_path = self._get_file_path(guild_id, data_type)
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}
            
            self.cache[cache_key] = data.copy()
            return data
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error in {file_path}: {e}")
            self._backup_file(file_path)
            self.cache[cache_key] = {}
            return {}
        except Exception as e:
            self.logger.error(f"Failed to load data from {file_path}: {e}")
            raise DataManagerError(f"Failed to load data: {e}")
    
    def save_data(self, guild_id: int, data_type: str, data: Dict[str, Any]) -> None:
        """Save data for a specific guild and data type."""
        file_path = self._get_file_path(guild_id, data_type)
        try:
            # Create backup before saving
            self._backup_file(file_path)
            
            # Save new data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            self.cache[f"{guild_id}_{data_type}"] = data.copy()
            self.logger.info(f"Saved data for guild {guild_id}, type {data_type}")
        except Exception as e:
            self.logger.error(f"Failed to save data to {file_path}: {e}")
            raise DataManagerError(f"Failed to save data: {e}")
    
    def get_value(self, guild_id: int, data_type: str, key: str, default: Any = None) -> Any:
        """Get a specific value from a guild's data."""
        try:
            data = self.load_data(guild_id, data_type)
            return data.get(key, default)
        except Exception as e:
            self.logger.error(f"Failed to get value {key} for guild {guild_id}: {e}")
            return default
    
    def set_value(self, guild_id: int, data_type: str, key: str, value: Any) -> None:
        """Set a specific value in a guild's data."""
        try:
            data = self.load_data(guild_id, data_type)
            data[key] = value
            self.save_data(guild_id, data_type, data)
        except Exception as e:
            self.logger.error(f"Failed to set value {key} for guild {guild_id}: {e}")
            raise DataManagerError(f"Failed to set value: {e}")
    
    def delete_value(self, guild_id: int, data_type: str, key: str) -> None:
        """Delete a specific value from a guild's data."""
        try:
            data = self.load_data(guild_id, data_type)
            if key in data:
                del data[key]
                self.save_data(guild_id, data_type, data)
                self.logger.info(f"Deleted key {key} for guild {guild_id}, type {data_type}")
        except Exception as e:
            self.logger.error(f"Failed to delete value {key} for guild {guild_id}: {e}")
            raise DataManagerError(f"Failed to delete value: {e}")
    
    def get_all_guild_data(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all data for a specific guild."""
        try:
            guild_path = self._get_guild_path(guild_id)
            all_data = {}
            for file_path in guild_path.glob("*.json"):
                data_type = file_path.stem
                all_data[data_type] = self.load_data(guild_id, data_type)
            return all_data
        except Exception as e:
            self.logger.error(f"Failed to get all data for guild {guild_id}: {e}")
            raise DataManagerError(f"Failed to get all guild data: {e}")
    
    def clear_cache(self, guild_id: Optional[int] = None) -> None:
        """Clear the cache for a specific guild or all guilds."""
        try:
            if guild_id is None:
                self.cache.clear()
                self.logger.info("Cleared entire cache")
            else:
                keys_to_remove = [k for k in self.cache if k.startswith(f"{guild_id}_")]
                for key in keys_to_remove:
                    del self.cache[key]
                self.logger.info(f"Cleared cache for guild {guild_id}")
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            raise DataManagerError(f"Failed to clear cache: {e}")
    
    def cleanup_old_backups(self, days: int = 7) -> None:
        """Remove backup files older than specified days."""
        try:
            backup_dir = self.base_path / "backups"
            if not backup_dir.exists():
                return
            
            cutoff = datetime.now().timestamp() - (days * 86400)
            for backup_file in backup_dir.glob("*.json"):
                if backup_file.stat().st_mtime < cutoff:
                    backup_file.unlink()
                    self.logger.info(f"Deleted old backup: {backup_file}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup old backups: {e}")
            raise DataManagerError(f"Failed to cleanup backups: {e}")

    # Utility Methods
    async def get_poll_settings(self, guild_id: int) -> dict:
        """Get poll settings for a guild"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id
            )
            return row["poll_settings"] if row and "poll_settings" in row else {}

    async def update_poll_settings(self, guild_id: int, settings: dict) -> None:
        """Update poll settings for a guild"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, poll_settings)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET poll_settings = $2
                """,
                guild_id, settings
            )

    async def get_giveaway_settings(self, guild_id: int) -> dict:
        """Get giveaway settings for a guild"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id
            )
            return row["giveaway_settings"] if row and "giveaway_settings" in row else {}

    async def update_giveaway_settings(self, guild_id: int, settings: dict) -> None:
        """Update giveaway settings for a guild"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, giveaway_settings)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET giveaway_settings = $2
                """,
                guild_id, settings
            )

    async def get_user_profile(self, user_id: int) -> dict:
        """Get a user's profile data"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT profile_data FROM user_profiles WHERE user_id = $1",
                user_id
            )
            return row["profile_data"] if row else None

    async def update_user_profile(self, user_id: int, updates: dict) -> None:
        """Update a user's profile data"""
        async with self.pool.acquire() as conn:
            # Get current profile data
            current_data = await self.get_user_profile(user_id) or {}
            
            # Update with new data
            current_data.update(updates)
            
            # Save to database
            await conn.execute(
                """
                INSERT INTO user_profiles (user_id, profile_data)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET profile_data = $2
                """,
                user_id, current_data
            )

    async def add_user_badge(self, user_id: int, badge_id: str) -> None:
        """Add a badge to a user's profile"""
        async with self.pool.acquire() as conn:
            current_data = await self.get_user_profile(user_id) or {}
            badges = current_data.get("badges", [])
            
            if badge_id not in badges:
                badges.append(badge_id)
                current_data["badges"] = badges
                
                await conn.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile_data)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET profile_data = $2
                    """,
                    user_id, current_data
                )

    async def remove_user_badge(self, user_id: int, badge_id: str) -> None:
        """Remove a badge from a user's profile"""
        async with self.pool.acquire() as conn:
            current_data = await self.get_user_profile(user_id) or {}
            badges = current_data.get("badges", [])
            
            if badge_id in badges:
                badges.remove(badge_id)
                current_data["badges"] = badges
                
                await conn.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile_data)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET profile_data = $2
                    """,
                    user_id, current_data
                )

# Default instance
data_manager = DataManager()

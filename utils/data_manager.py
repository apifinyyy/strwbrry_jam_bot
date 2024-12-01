import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import asyncio
import asyncpg
import aiosqlite
import aiofiles

class DataManagerError(Exception):
    """Base exception class for DataManager errors."""
    pass

class DataManager:
    def __init__(self, base_path: str = "data", database_url: str = None, pool_min_size: int = 1, pool_max_size: int = 10):
        """Initialize the data manager with a base path for data storage and database pool settings."""
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
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.db_path = os.path.join(os.path.dirname(__file__), "..", "data", "bot.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def connect_to_sqlite(self):
        """Connect to SQLite database."""
        try:
            self.conn = await aiosqlite.connect(self.db_path)
            await self.initialize_database()
            self.logger.info(f"Connected to SQLite database at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Error connecting to SQLite: {e}")
            raise DataManagerError(f"Failed to connect to SQLite: {e}")

    async def connect_to_database(self):
        """Connect to the database."""
        try:
            if self.database_url:
                # PostgreSQL
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=self.pool_min_size,
                    max_size=self.pool_max_size
                )
                self.logger.info("Connected to PostgreSQL database")
            else:
                # SQLite
                await self.connect_to_sqlite()
                self.logger.info("Connected to SQLite database")

            # Initialize tables
            await self.initialize_database()
            
        except Exception as e:
            self.logger.error(f"Error connecting to database: {e}")
            raise DataManagerError(f"Failed to connect to database: {e}")

    async def get_connection(self):
        """Get a database connection"""
        try:
            if self.database_url:
                if not self.pool:
                    await self.connect_to_database()
                return self.pool
            else:
                if not hasattr(self, 'conn') or self.conn is None:
                    await self.connect_to_sqlite()
                return self.conn
        except Exception as e:
            self.logger.error(f"Failed to get database connection: {e}")
            raise DataManagerError(f"Failed to get database connection: {e}")

    async def initialize_database(self):
        """Initialize the database tables."""
        try:
            if self.database_url:
                # PostgreSQL
                async with self.pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS key_value_store (
                            table_name TEXT,
                            key TEXT,
                            data JSONB,
                            PRIMARY KEY (table_name, key)
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS guild_settings (
                            guild_id BIGINT PRIMARY KEY,
                            settings JSONB DEFAULT '{}'::jsonb
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id BIGINT PRIMARY KEY,
                            profile JSONB DEFAULT '{}'::jsonb,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
            else:
                # SQLite
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS key_value_store (
                            table_name TEXT,
                            key TEXT,
                            data TEXT,
                            PRIMARY KEY (table_name, key)
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS guild_settings (
                            guild_id INTEGER PRIMARY KEY,
                            settings TEXT DEFAULT '{}'
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id INTEGER PRIMARY KEY,
                            profile TEXT DEFAULT '{}',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    await conn.commit()

        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise DataManagerError(f"Failed to initialize database: {e}")
    
    async def get_user_profile(self, user_id: int) -> dict:
        """Get a user's profile data"""
        try:
            if self.database_url:  # PostgreSQL
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT profile FROM user_profiles WHERE user_id = $1",
                        user_id
                    )
                    return json.loads(row['profile']) if row else {}
            else:  # SQLite
                conn = await self.get_connection()
                async with conn.execute(
                    "SELECT profile FROM user_profiles WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return json.loads(row[0]) if row else {}
        except Exception as e:
            self.logger.error(f"Failed to get user profile: {e}")
            return {}  # Return empty dict on error

    async def update_user_profile(self, user_id: int, **fields):
        """Update user profile fields."""
        try:
            # Get current profile
            current_profile = await self.get_user_profile(user_id)
            
            # Update fields
            current_profile.update(fields)
            profile_json = json.dumps(current_profile)
            
            if self.database_url:  # PostgreSQL
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO user_profiles (user_id, profile)
                        VALUES ($1, $2)
                        ON CONFLICT (user_id) 
                        DO UPDATE SET profile = $2
                        """,
                        user_id, profile_json
                    )
            else:  # SQLite
                conn = await self.get_connection()
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO user_profiles (user_id, profile)
                    VALUES (?, ?)
                    """,
                    (user_id, profile_json)
                )
                await conn.commit()
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to update user profile: {e}")
            return False  # Return False on error
    
    async def save_json(self, table: str, key: str, data: dict) -> bool:
        """Save JSON data to the database"""
        try:
            json_data = json.dumps(data)
            if self.database_url:
                # PostgreSQL
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO key_value_store (table_name, key, data)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (table_name, key) DO UPDATE SET data = $3
                        """,
                        table, key, json_data
                    )
            else:
                # SQLite
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO key_value_store (table_name, key, data)
                        VALUES (?, ?, ?)
                        """,
                        (table, key, json_data)
                    )
                    await conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Failed to save JSON data to {table}: {e}")
            raise DataManagerError(f"Failed to save JSON data: {e}")

    async def load_json(self, table: str, key: str) -> dict:
        """Load JSON data from the database"""
        try:
            if self.database_url:
                # PostgreSQL
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT data FROM key_value_store WHERE table_name = $1 AND key = $2",
                        table, key
                    )
                    return json.loads(row['data']) if row else {}
            else:
                # SQLite
                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "SELECT data FROM key_value_store WHERE table_name = ? AND key = ?",
                            (table, key)
                        )
                        row = await cursor.fetchone()
                        return json.loads(row[0]) if row else {}
        except Exception as e:
            self.logger.error(f"Failed to load JSON data from {table}: {e}")
            raise DataManagerError(f"Failed to load JSON data: {e}")

    async def exists(self, table: str, key: str = None) -> bool:
        """Check if a record exists in the database.
        
        Args:
            table (str): The table_name to check in key_value_store
            key (str, optional): The key to check in key_value_store
        """
        try:
            if self.database_url:
                # PostgreSQL
                async with self.pool.acquire() as conn:
                    if key is not None:
                        result = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM key_value_store WHERE table_name = $1 AND key = $2)",
                            table, key
                        )
                    else:
                        result = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM key_value_store WHERE table_name = $1)",
                            table
                        )
                    return bool(result)
            else:
                # SQLite
                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.cursor() as cursor:
                        if key is not None:
                            await cursor.execute(
                                "SELECT EXISTS(SELECT 1 FROM key_value_store WHERE table_name = ? AND key = ?)",
                                (table, key)
                            )
                        else:
                            await cursor.execute(
                                "SELECT EXISTS(SELECT 1 FROM key_value_store WHERE table_name = ?)",
                                (table,)
                            )
                        result = await cursor.fetchone()
                        return bool(result[0]) if result else False
        except Exception as e:
            self.logger.error(f"Failed to check existence in {table}: {e}")
            raise DataManagerError(f"Failed to check existence: {e}")

    async def save(self, table: str, key: str = "default", data: dict = None) -> bool:
        """Save data to the database.
        
        Args:
            table (str): The table name to save to
            key (str, optional): The key within the table. Defaults to "default".
            data (dict, optional): The data to save. Required if key is provided.
        """
        if data is None:
            # If no data provided, assume the key parameter is actually the data
            data = key
            key = "default"
            
        return await self.save_json(table, key, data)

    async def load(self, data_type: str, key: str = "default") -> dict:
        """Load data from JSON file"""
        try:
            file_path = self._get_file_path(data_type, key)
            if not os.path.exists(file_path):
                return {}
                
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
        except Exception as e:
            self.logger.error(f"Failed to load JSON data from {data_type}: {str(e)}")
            return {}

    async def save(self, data_type: str, key: str, data: dict) -> bool:
        """Save data to JSON file"""
        try:
            file_path = self._get_file_path(data_type, key)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=4))
            return True
        except Exception as e:
            self.logger.error(f"Failed to save JSON data to {data_type}: {str(e)}")
            return False

    async def exists(self, data_type: str, key: str = "default") -> bool:
        """Check if data exists for a given type and key."""
        try:
            file_path = self._get_file_path(data_type, key)
            return os.path.exists(file_path)
        except Exception as e:
            self.logger.error(f"Error checking existence of {data_type}/{key}: {e}")
            return False

    async def load_json(self, data_type: str, key: str = "default") -> dict:
        """Load JSON data with error handling."""
        try:
            file_path = self._get_file_path(data_type, key)
            if not os.path.exists(file_path):
                return {}
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
        except Exception as e:
            self.logger.error(f"Failed to load JSON data from {data_type}/{key}: {e}")
            return {}

    async def save_json(self, data_type: str, key: str, data: dict) -> bool:
        """Save JSON data with error handling."""
        try:
            file_path = self._get_file_path(data_type, key)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=4))
            return True
        except Exception as e:
            self.logger.error(f"Failed to save JSON data to {data_type}/{key}: {e}")
            return False

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

    async def close(self):
        """Close database connections"""
        try:
            if self.pool:
                await asyncio.wait_for(self.pool.close(), timeout=1.0)
            if hasattr(self, 'conn') and self.conn:
                await asyncio.wait_for(self.conn.close(), timeout=1.0)
            self.logger.info("Database connections closed")
        except asyncio.TimeoutError:
            self.logger.warning("Database close timed out")
        except Exception as e:
            self.logger.error(f"Error closing database connections: {e}")
            raise DataManagerError(f"Failed to close database connections: {e}")

    async def close_connections(self):
        """Close database connections."""
        try:
            if self.pool:
                await self.pool.close()
                self.logger.info("PostgreSQL connection pool closed.")
            if hasattr(self, 'conn') and self.conn:
                await self.conn.close()
                self.logger.info("SQLite connection closed.")
        except Exception as e:
            self.logger.error(f"Error closing database connections: {e}")

    async def add_index(self, table_name: str, column_name: str):
        """Add an index to a specified column in a table."""
        try:
            if self.database_url:
                async with self.pool.acquire() as conn:
                    await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{column_name} ON {table_name} ({column_name})")
                    self.logger.info(f"Index created on {table_name}.{column_name}.")
            else:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{column_name} ON {table_name} ({column_name})")
                    self.logger.info(f"Index created on {table_name}.{column_name}.")
        except Exception as e:
            self.logger.error(f"Error creating index on {table_name}.{column_name}: {e}")

    async def execute_query(self, query: str, *args):
        """Execute a parameterized query."""
        try:
            if self.database_url:
                async with self.pool.acquire() as conn:
                    result = await conn.fetch(query, *args)
                    return result
            else:
                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.execute(query, args) as cursor:
                        result = await cursor.fetchall()
                        return result
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise DataManagerError(f"Error executing query: {e}")

    async def execute_non_query(self, query: str, *args):
        """Execute a parameterized non-query (e.g., INSERT, UPDATE)."""
        try:
            if self.database_url:
                async with self.pool.acquire() as conn:
                    await conn.execute(query, *args)
            else:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(query, args)
                    await conn.commit()
        except Exception as e:
            self.logger.error(f"Error executing non-query: {e}")
            raise DataManagerError(f"Error executing non-query: {e}")

    async def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data before storing it."""
        # Placeholder for encryption logic
        # Implement encryption logic here
        return data

    async def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data after retrieving it."""
        # Placeholder for decryption logic
        # Implement decryption logic here
        return encrypted_data

    # Utility Methods
    async def get_poll_settings(self, guild_id: int) -> dict:
        """Get poll settings for a guild"""
        async with await self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id
            )
            return row["settings"].get("poll_settings", {}) if row and "settings" in row else {}

    async def update_poll_settings(self, guild_id: int, settings: dict) -> None:
        """Update poll settings for a guild"""
        async with await self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, settings)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET settings = $2
                """,
                guild_id, {"poll_settings": settings}
            )

    async def get_giveaway_settings(self, guild_id: int) -> dict:
        """Get giveaway settings for a guild"""
        async with await self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id
            )
            return row["settings"].get("giveaway_settings", {}) if row and "settings" in row else {}

    async def update_giveaway_settings(self, guild_id: int, settings: dict) -> None:
        """Update giveaway settings for a guild"""
        async with await self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, settings)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET settings = $2
                """,
                guild_id, {"giveaway_settings": settings}
            )

    async def add_user_badge(self, user_id: int, badge_id: str) -> None:
        """Add a badge to a user's profile"""
        async with await self.get_connection() as conn:
            current_data = await self.get_user_profile(user_id) or {}
            badges = current_data.get("badges", [])
            
            if badge_id not in badges:
                badges.append(badge_id)
                current_data["badges"] = badges
                
                await conn.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET profile = $2
                    """,
                    user_id, current_data
                )

    async def remove_user_badge(self, user_id: int, badge_id: str) -> None:
        """Remove a badge from a user's profile"""
        async with await self.get_connection() as conn:
            current_data = await self.get_user_profile(user_id) or {}
            badges = current_data.get("badges", [])
            
            if badge_id in badges:
                badges.remove(badge_id)
                current_data["badges"] = badges
                
                await conn.execute(
                    """
                    INSERT INTO user_profiles (user_id, profile)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET profile = $2
                    """,
                    user_id, current_data
                )

    async def init_db(self):
        """Initialize the database with required tables (backward compatibility method)"""
        try:
            if self.database_url:
                # PostgreSQL
                async with self.pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS key_value_store (
                            table_name TEXT,
                            key TEXT,
                            data JSONB,
                            PRIMARY KEY (table_name, key)
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS guild_settings (
                            guild_id BIGINT PRIMARY KEY,
                            settings JSONB DEFAULT '{}'::jsonb
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id BIGINT PRIMARY KEY,
                            profile JSONB DEFAULT '{}'::jsonb,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
            else:
                # SQLite
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS key_value_store (
                            table_name TEXT,
                            key TEXT,
                            data TEXT,
                            PRIMARY KEY (table_name, key)
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS guild_settings (
                            guild_id INTEGER PRIMARY KEY,
                            settings TEXT DEFAULT '{}'
                        )
                    """)
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_profiles (
                            user_id INTEGER PRIMARY KEY,
                            profile TEXT DEFAULT '{}',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    await conn.commit()
            
            self.logger.info("Database tables initialized")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise DataManagerError(f"Failed to initialize database: {e}")

    async def cleanup(self):
        """Clean up database connections and resources."""
        try:
            if hasattr(self, 'conn'):
                await self.conn.close()
            if self.pool:
                await self.pool.close()
            self.logger.info("Database connections closed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

# Default instance
data_manager = DataManager()

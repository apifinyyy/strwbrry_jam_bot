# Strwbrry Jam Bot API Documentation

## Core Systems

### Data Manager
The `DataManager` class handles all data persistence operations.

#### Methods
- `get_user_profile(user_id: int) -> dict`
  - Retrieves a user's profile data
  - Returns `None` if no profile exists

- `update_user_profile(user_id: int, updates: dict) -> None`
  - Updates a user's profile with new data
  - Creates profile if it doesn't exist

- `add_user_badge(user_id: int, badge_id: str) -> None`
  - Adds a badge to user's profile
  - Silently fails if badge already exists

- `remove_user_badge(user_id: int, badge_id: str) -> None`
  - Removes a badge from user's profile
  - Silently fails if badge doesn't exist

### Config Manager
The `ConfigManager` class manages server-specific configurations.

#### Methods
- `get_guild_config(guild_id: int) -> Dict[str, Any]`
  - Returns full configuration for a guild
  - Creates default config if none exists

- `set_guild_config(guild_id: int, config: Dict[str, Any]) -> None`
  - Updates entire guild configuration
  - Validates against schema before saving

- `get_value(guild_id: int, *keys: str, default: Any = None) -> Any`
  - Gets specific configuration value using dot notation
  - Returns default if key doesn't exist

- `set_value(guild_id: int, value: Any, *keys: str) -> None`
  - Sets specific configuration value using dot notation
  - Creates intermediate dictionaries as needed

## Cog Features

### Social Cog
Profile customization and social features.

#### Commands
- `/profile [user]`
  - Shows user's profile card
  - Parameters:
    - user (optional): User to view profile of
  - Returns: Custom profile card image

- `/settheme <theme>`
  - Changes profile theme
  - Parameters:
    - theme: One of ["default", "night", "sunset"]
  - Returns: Success/failure message

- `/setbio <bio>`
  - Sets profile bio
  - Parameters:
    - bio: New bio text (max 100 chars)
  - Returns: Success/failure message

- `/settitle <title>`
  - Sets profile custom title
  - Parameters:
    - title: New title (max 30 chars)
  - Returns: Success/failure message

### Utility Cog
General utility features.

#### Commands
- `/poll <title> <options> [duration] [blind]`
  - Creates a poll
  - Parameters:
    - title: Poll question
    - options: Options separated by |
    - duration (optional): Poll duration in minutes
    - blind (optional): Hide results until end
  - Returns: Interactive poll message

- `/giveaway <prize> <duration> [winners] [requirement]`
  - Starts a giveaway
  - Parameters:
    - prize: What to give away
    - duration: How long to run for
    - winners (optional): Number of winners
    - requirement (optional): Entry requirement
  - Returns: Interactive giveaway message

## Database Schema

### user_profiles
```sql
CREATE TABLE user_profiles (
    user_id BIGINT PRIMARY KEY,
    profile_data JSONB DEFAULT '{}'::jsonb
)
```

### guild_settings
```sql
CREATE TABLE guild_settings (
    guild_id BIGINT PRIMARY KEY,
    poll_settings JSONB DEFAULT '{}'::jsonb,
    giveaway_settings JSONB DEFAULT '{}'::jsonb
)
```

## Error Handling
All commands implement the following error handling:
- Invalid input validation with helpful messages
- Database connection errors with retry logic
- Permission errors with clear explanations
- Rate limit notifications
- General error fallbacks

## Events
The bot handles these Discord events:
- on_ready: Bot startup
- on_guild_join: Server join setup
- on_guild_remove: Server leave cleanup
- on_command_error: Command error handling
- on_message: Message processing
- on_reaction_add: Reaction handling

# 🔌 API Documentation

Complete API reference for Strwbrry Jam Bot's commands and features.

## 🔗 Quick Links
- [Support Server](https://discord.gg/XcH8JmGaHZ)
- [Invite Bot](https://discord.com/api/oauth2/authorize?client_id=1310455349131608096&permissions=1644971949559&scope=bot%20applications.commands)
- [Configuration Guide](CONFIGURATION.md)
- [Admin Guide](ADMIN_GUIDE.md)

## 📚 Command Categories

### 🛡️ Moderation Commands

#### Warning System
```python
/warn <user> [reason]
# Issue a warning to a user
# Parameters:
# - user: @mention or ID (required)
# - reason: Text (optional)
# Returns: Warning confirmation

/warnings <user>
# View user's warnings
# Parameters:
# - user: @mention or ID (required)
# Returns: List of warnings

/delwarn <user> <warn_id>
# Delete a warning
# Parameters:
# - user: @mention or ID (required)
# - warn_id: Warning ID (required)
# Returns: Deletion confirmation
```

#### Auto-Moderation
```python
/automod <action> <feature>
# Manage auto-moderation features
# Parameters:
# - action: enable/disable/config (required)
# - feature: spam/links/caps/mentions (required)
# Returns: Configuration status

/automod threshold <feature> <value>
# Set auto-mod thresholds
# Parameters:
# - feature: spam/mentions/caps (required)
# - value: Number (required)
# Returns: Updated threshold
```

### 💰 Economy Commands

#### Currency Management
```python
/balance [user]
# Check balance
# Parameters:
# - user: @mention or ID (optional)
# Returns: Current balance

/daily
# Claim daily reward
# Parameters: None
# Returns: Reward amount

/weekly
# Claim weekly reward
# Parameters: None
# Returns: Reward amount

/transfer <user> <amount>
# Transfer currency
# Parameters:
# - user: @mention or ID (required)
# - amount: Number (required)
# Returns: Transfer confirmation
```

#### Shop System
```python
/shop
# View shop items
# Parameters: None
# Returns: List of items

/buy <item>
# Purchase item
# Parameters:
# - item: Item name/ID (required)
# Returns: Purchase confirmation

/inventory [user]
# View inventory
# Parameters:
# - user: @mention or ID (optional)
# Returns: Inventory contents
```

### ⭐ XP & Leveling

```python
/rank [user]
# View rank card
# Parameters:
# - user: @mention or ID (optional)
# Returns: Rank card embed

/leaderboard [page]
# View XP leaderboard
# Parameters:
# - page: Number (optional)
# Returns: Leaderboard page

/xp info
# View XP system info
# Parameters: None
# Returns: XP rates and rewards
```

### 🎮 Mini-Games

```python
/trivia [category]
# Start trivia game
# Parameters:
# - category: Game category (optional)
# Returns: Trivia question

/rps <choice>
# Play Rock Paper Scissors
# Parameters:
# - choice: rock/paper/scissors (required)
# Returns: Game result

/math
# Start math game
# Parameters: None
# Returns: Math problem
```

### 🎫 Ticket System

```python
/ticket create [reason]
# Create support ticket
# Parameters:
# - reason: Text (optional)
# Returns: New ticket channel

/ticket close [reason]
# Close ticket
# Parameters:
# - reason: Text (optional)
# Returns: Close confirmation

/ticket add <user>
# Add user to ticket
# Parameters:
# - user: @mention or ID (required)
# Returns: Add confirmation
```

### 👋 Welcome System

```python
/welcome test
# Test welcome message
# Parameters: None
# Returns: Welcome message preview

/goodbye test
# Test goodbye message
# Parameters: None
# Returns: Goodbye message preview
```

## 📊 Event Webhooks

### Available Events
```json
{
  "member_join": {
    "user": "User object",
    "guild": "Guild object",
    "timestamp": "ISO timestamp"
  },
  "member_leave": {
    "user": "User object",
    "guild": "Guild object",
    "timestamp": "ISO timestamp"
  },
  "message_delete": {
    "message": "Message object",
    "channel": "Channel object",
    "timestamp": "ISO timestamp"
  }
}
```

### Webhook Format
```json
{
  "type": "event_type",
  "data": {
    // Event specific data
  },
  "timestamp": "ISO timestamp",
  "guild_id": "Guild ID"
}
```

## 🔒 Permission Levels

### User Levels
1. **User** (Level 0)
   - Basic commands
   - Game participation
   - Economy features

2. **Moderator** (Level 1)
   - Warning management
   - Ticket handling
   - Auto-mod config

3. **Administrator** (Level 2)
   - Full configuration
   - Economy management
   - Bot customization

4. **Owner** (Level 3)
   - Server settings
   - Permission management
   - Advanced features

## 🛠️ Rate Limits

### Command Limits
- General commands: 5/5s
- Economy commands: 3/5s
- Game commands: 1/10s
- Moderation commands: 10/10s

### Feature Limits
- Tickets: 1 per user
- Daily reward: 24h cooldown
- Weekly reward: 7d cooldown
- XP gain: 60s cooldown

## 📝 Response Formats

### Success Response
```json
{
  "success": true,
  "data": {
    // Command specific data
  },
  "message": "Success message"
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description"
  }
}
```

## ❓ Need Help?

- Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
- Check [Configuration Guide](CONFIGURATION.md)
- Review [Admin Guide](ADMIN_GUIDE.md)
- Use `/help` for command help

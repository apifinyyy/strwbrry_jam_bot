# ⚙️ Configuration Guide

A comprehensive guide to configuring Strwbrry Jam Bot for your server.

## 🔗 Quick Links
- [Support Server](https://discord.gg/XcH8JmGaHZ)
- [Invite Bot](https://discord.com/api/oauth2/authorize?client_id=1310455349131608096&permissions=1644971949559&scope=bot%20applications.commands)
- [Getting Started](GETTING_STARTED.md)
- [Admin Guide](ADMIN_GUIDE.md)

## 🚀 Quick Setup

```bash
/setup                             # Run initial server setup
/panel                             # View and edit server settings
/serverinfo                        # View server information
```

## 🛠️ Core Settings

### Server Configuration
```bash
# Basic Settings
/setup                             # Run initial server setup
/panel                             # View and edit server settings
/serverinfo                        # View server information

# Channels
/setwelcome #welcome              # Set welcome channel and message
/setgoodbye #goodbye              # Set goodbye channel and message
/logsetup #mod-logs               # Set logging channel
```

### Moderation
```bash
# Auto-Moderation
/panel automod                    # Configure auto-moderation settings
/logstatus                       # View current logging settings

# Warning System
/warn @user                      # Issue a warning
/warnings @user                  # View user warnings
/delwarn @user [warn_id]        # Delete a warning
```

### Economy System
```bash
# Currency Settings
/config economy daily 100             # Daily reward amount
/config economy weekly 500            # Weekly reward amount
/config economy payday 50             # Activity reward amount

# Shop Settings
/config shop add-item "VIP Role" 1000  # Add shop item
/config shop remove-item "VIP Role"    # Remove shop item
/config shop list                      # View all items
```

### XP System
```bash
# XP Management
/rank                           # View your rank
/leaderboard                    # View server leaderboard
/givexp @user <amount>          # Give XP to user
/takexp @user <amount>          # Remove XP from user
/blockxp @user                  # Block user from gaining XP
/unblockxp @user               # Unblock user from gaining XP

# Level Rewards
/setlevelrole <level> @role    # Set role reward for level
/setlevelchannel #channel      # Set level-up announcement channel
```

### Welcome System
```bash
# Messages
/setwelcome                    # Configure welcome message and channel
/setgoodbye                    # Configure goodbye message and channel
/testwelcome                   # Test welcome message
/testgoodbye                   # Test goodbye message
```

### Role Management
```bash
# Role Settings
/xprole                       # Configure XP-based roles
/persistentrole              # Configure persistent roles
```

### Tickets
```bash
# Setup
/ticketsetup                 # Set up ticket system
/ticketcategories           # Manage ticket categories
```

### Utilities
```bash
# Server Tools
/broadcast                  # Send scheduled announcements
/listbroadcasts            # View scheduled broadcasts
/cancelbroadcast           # Cancel a scheduled broadcast
/remind                    # Set a reminder
/calculate                 # Calculator utility
```

## 🎮 Feature Settings

### Games
```bash
# Game Rewards
/config games trivia 50              # Trivia win reward
/config games rps 30                 # RPS win reward
/config games math 40                # Math game reward

# Cooldowns
/config games cooldown trivia 30     # Trivia cooldown
/config games cooldown rps 15        # RPS cooldown
```

### Logging
```bash
# Event Logging
/config logs enable message-delete   # Log deleted messages
/config logs enable member-join      # Log member joins
/config logs enable role-changes     # Log role changes

# Log Format
/config logs format embed            # Use embed format
/config logs color #FF0000          # Set embed color
```

## 📋 Variables

Use these variables in messages:
- `{user}` - Mentions the user
- `{server}` - Server name
- `{count}` - Member count
- `{owner}` - Server owner
- `{channel}` - Channel name

## 🔒 Permissions

Required permissions for features:
- Moderation: Ban Members, Kick Members
- Welcome: Manage Roles
- Logging: View Audit Log
- Economy: Manage Roles
- Tickets: Manage Channels

## ❓ Need Help?

- Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
- Check [Admin Guide](ADMIN_GUIDE.md)
- Use `/help config` for command help

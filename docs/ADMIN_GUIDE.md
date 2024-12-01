# 👑 Admin Guide

A comprehensive guide for server administrators using Strwbrry Jam Bot.

## 🔗 Quick Links
- [Support Server](https://discord.gg/XcH8JmGaHZ)
- [Invite Bot](https://discord.com/api/oauth2/authorize?client_id=1310455349131608096&permissions=1644971949559&scope=bot%20applications.commands)
- [Configuration Guide](CONFIGURATION.md)
- [Setup Checklist](SETUP_CHECKLIST.md)

## 🚀 Initial Setup

### Bot Setup
1. **Invite the Bot**
   - Use the [invite link](https://discord.com/api/oauth2/authorize?client_id=1310455349131608096&permissions=1644971949559&scope=bot%20applications.commands)
   - Select your server
   - Grant required permissions

2. **Quick Configuration**
   ```bash
   /setup                # Run initial setup
   /panel               # View and edit settings
   /serverinfo         # View server information
   ```

3. **Essential Channels**
   ```bash
   /setwelcome         # Configure welcome channel
   /setgoodbye        # Configure goodbye channel
   /logsetup          # Set up logging channel
   ```

## 🛡️ Moderation System

### Warning System
```bash
# Issue Warning
/warn @user [reason]           # Warn user
/warnings @user               # View user warnings
/delwarn @user [warn_id]     # Delete warning

# Configure Warnings
/panel warnings              # Configure warning settings
```

### Auto-Moderation
```bash
# Configure Settings
/panel automod              # Configure auto-moderation
/logstatus                 # View current settings

# View Logs
/logsetup #channel        # Set logging channel
```

### Logging System
```bash
# Setup Logging
/logsetup                  # Configure logging
/logstatus                # View current settings
```

## 🎫 Ticket System

### Setup
```bash
# Basic Setup
/ticketsetup              # Set up ticket system
/ticketcategories        # Manage categories
```

### Management
```bash
# Staff Commands
/panel tickets           # Configure ticket settings
```

## 💰 Economy Management

### Currency Control
```bash
# Manage Currency
/givexp @user <amount>    # Give XP (currency)
/takexp @user <amount>   # Remove XP (currency)
/blockxp @user          # Block user from gaining XP
/unblockxp @user       # Unblock user
```

### XP & Roles
```bash
# Manage System
/xprole                # Configure XP roles
/setlevelrole         # Set level rewards
/setlevelchannel     # Set announcement channel
```

## ⚙️ Advanced Features

### Scheduled Messages
```bash
/broadcast            # Schedule a message
/listbroadcasts      # View scheduled messages
/cancelbroadcast     # Cancel scheduled message
```

### Utility Commands
```bash
/remind              # Set a reminder
/calculate          # Calculator utility
/serverinfo        # View server stats
```

## 📞 Support

Need help? We've got you covered:
- Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
- Check [Configuration Guide](CONFIGURATION.md)
- Review [Setup Checklist](SETUP_CHECKLIST.md)
- Use `/help admin` for command help

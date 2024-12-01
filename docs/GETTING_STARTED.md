# Getting Started with Strwbrry Jam Bot 🍓

Welcome to Strwbrry Jam Bot! This guide will help you get the bot up and running in your server quickly.

## 🔗 Quick Links
- [Support Server](https://discord.gg/XcH8JmGaHZ)
- [Invite Bot](https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands)
- [User Guide](USER_GUIDE.md)
- [Configuration](CONFIGURATION.md)
- [Admin Guide](ADMIN_GUIDE.md)

## 🚀 5-Minute Setup

### 1. Add Bot to Server
1. Click the [Invite Link](https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands)
2. Select your server
3. Click "Authorize"
4. Complete the captcha

### 2. Quick Configuration
Run these commands:
```
/setauditlog     # Set up audit logging
/serverinfo      # Shows your current server information
/help            # Lists all commands
```

### 3. Essential Features
Set up the most important features:

#### Moderation
```
/setauditlog #mod-logs     # Set up moderation logging
/clean                    # Delete messages from the channel
/mute                    # Mute users
/unmute                  # Unmute users
```

#### Role Management
```
/persistentrole          # Manage persistent roles
/xprole                  # Manage XP-based roles
```

## 📚 Next Steps

1. **Customize Your Server**
   - Configure audit logging with `/setauditlog`
   - Set up role management with `/persistentrole` and `/xprole`
   - Review server settings with `/serverinfo`

2. **Learn the Features**
   - [User Guide](USER_GUIDE.md)
   - Type `/help` for detailed help
   - Join our [Support Server](https://discord.gg/XcH8JmGaHZ)

3. **Engage Your Community**
   - Set up economy system
   - Configure moderation tools
   - Use utility commands

## 🆘 Need Help?

- Use `/help` for command information
- Check our [FAQ](USER_GUIDE.md#faq)
- Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
- Read the [Troubleshooting Guide](ADMIN_GUIDE.md#troubleshooting)

## 🔒 Permissions

The bot needs these permissions to function properly:
- Administrator (recommended)
- Or these specific permissions:
  - Manage Roles
  - Manage Channels
  - Kick/Ban Members
  - Manage Messages
  - View Channels
  - Send Messages
  - Embed Links
  - Attach Files
  - Add Reactions
  - Use External Emojis
  - Manage Webhooks

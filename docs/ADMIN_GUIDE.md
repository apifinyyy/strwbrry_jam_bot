# Strwbrry Jam Bot - Admin Guide

This guide covers all admin commands and setup instructions for Strwbrry Jam Bot.

## Quick Start

1. Bot Setup
   - Invite bot with required permissions
   - Use `/config help` to see all options
   - Set up logging with `/logsetup`

2. Essential Commands
```
/config - Change bot settings
/viewconfig - View current settings
/botappearance - Customize bot's look
/ticketsetup - Set up support tickets
```

## Feature Setup

### Support Tickets
```
1. Set up categories:
   /ticketcategories add "Support"
   /ticketcategories add "Bug Report"

2. Create ticket menu:
   /ticketsetup #channel
```

### Economy
```
1. Set rewards:
   /config economy daily_amount 100
   /config economy weekly_amount 500

2. Add shop roles:
   /config economy shop_role @VIP 1000
```

### XP System
```
1. Configure XP rates:
   /config xp chat_xp 5 15
   /config xp voice_xp 1

2. Set up rewards:
   /config xp role_reward @Level10 1000
```

### Welcome System
```
1. Set channels:
   /config welcome channel #welcome
   /config goodbye channel #goodbye

2. Set messages:
   /config welcome message "Welcome {user}!"
```

### Logs
```
1. Set log channel:
   /logsetup #logs

2. Configure events:
   /config logs enable message_delete
   /config logs enable member_join
```

## Tips
- Use `/help admin` for admin command list
- Test configurations in a private channel
- Back up settings with `/config backup`
- Monitor bot status with `/status`

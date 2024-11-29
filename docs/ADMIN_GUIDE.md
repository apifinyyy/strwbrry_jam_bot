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

### Moderation System
```
1. Configure Warning System:
   /escalation_config setting_type thresholds
   Example thresholds:
   - 3 points: 1 hour mute
   - 5 points: 24 hour mute
   - 7 points: kick
   - 10 points: ban

2. Set Warning Severity:
   /escalation_config setting_type severity
   - Level 1: Normal warning (1 point)
   - Level 2: Moderate warning (2 points)
   - Level 3: Severe warning (3 points)

3. Configure Warning Expiry:
   /escalation_config setting_type expiry
   - Level 1: 30 days
   - Level 2: 60 days
   - Level 3: 90 days

4. Set System Settings:
   /escalation_config setting_type settings
   - Cleanup interval
   - History retention
   - DM notifications
   - Log channel
   - Auto-pardon
   - Universal warnings
   - Warning sharing
```

### Warning Commands
```
1. Issue Warning:
   /warn @user [reason] [severity]
   - Severity 1-3 (default: 1)
   - Reason required if configured

2. View Infractions:
   /infractions @user
   - Shows active warnings
   - Shows warning history
   - Shows redemption progress

3. Manage Appeals:
   /manage_appeal @user [warning_id] [action] [reason]
   - approve/deny appeals
   - Add optional reason

4. Transfer Warnings:
   /transfer_warnings [from_server] @user [warning_ids]
   - Transfer specific or all warnings
```

### Redemption System
```
1. Default Tasks:
   - Help 3 other members (2 points)
   - Make 5 positive contributions (2 points)
   - Create a guide (3 points)

2. Submit Redemption:
   /redeem [task] [proof]
   - Users submit completed tasks
   - Mods review submissions
```

## Tips
- Use `/help admin` for admin command list
- Test configurations in a private channel
- Back up settings with `/config backup`
- Monitor bot status with `/status`

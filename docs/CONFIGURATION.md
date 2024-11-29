# Strwbrry Jam Bot - Configuration Guide

Quick reference for all configuration commands and settings.

## Game Settings

### Fun & Games
```
/config games rps_amount 50
/config games trivia_amount 100
/config games math_amount 75
/config games chat_amount 25
```

### Economy
```
/config economy daily_amount 100
/config economy weekly_amount 500
/config economy shop_role @Role 1000
/config economy gambling_max 1000
```

### XP System
```
/config xp chat_xp 5 15
/config xp voice_xp 2
/config xp level_multiplier 1.5
/config xp role_reward @Level10 1000
```

### Welcome Messages
```
/config welcome channel #welcome
/config welcome message "Welcome {user} to {server}!"
/config goodbye channel #goodbye
/config goodbye message "Goodbye {user}!"
```

### Tickets
```
/config tickets category "Support"
/config tickets archive_category "Closed Tickets"
/config tickets support_role @Support
```

### Roles
```
/config roles auto_role @Member
/config roles level_roles @Level5 500
/config roles welcome_role @New
```

### Logging
```
/config logs channel #logs
/config logs enable message_delete
/config logs enable member_join
/config logs enable role_update
```

### Bot Appearance
```
/botappearance name "Server Helper"
/botappearance avatar_url "https://example.com/avatar.png"
/resetbotappearance
```

## Tips
- Use `/viewconfig` to see current settings
- Test changes in a test channel first
- Keep track of role prices and rewards
- Back up config regularly

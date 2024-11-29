# Setup Checklist

## Discord Setup
- [ ] Create application at https://discord.com/developers/applications
- [ ] Create bot user
- [ ] Enable Privileged Gateway Intents:
  - [ ] Server Members Intent
  - [ ] Message Content Intent
  - [ ] Presence Intent
- [ ] Get bot token
- [ ] Generate bot invite link with necessary permissions
- [ ] Invite bot to your test server

## Database Setup
- [ ] Install PostgreSQL
- [ ] Create database:
  ```sql
  CREATE DATABASE strwbrry_jam_bot;
  ```
- [ ] Create user and set password:
  ```sql
  CREATE USER botuser WITH PASSWORD 'your_password';
  GRANT ALL PRIVILEGES ON DATABASE strwbrry_jam_bot TO botuser;
  ```
- [ ] Note down database URL:
  ```
  postgresql://botuser:your_password@localhost/strwbrry_jam_bot
  ```

## Environment Setup
- [ ] Create .env file with:
  ```env
  DISCORD_TOKEN=your_bot_token
  DATABASE_URL=your_database_url
  ```
- [ ] Install Python 3.8 or higher
- [ ] Create virtual environment:
  ```bash
  python -m venv venv
  ```
- [ ] Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## GitHub Setup (Optional)
- [ ] Create GitHub repository
- [ ] Update README.md badges:
  - [ ] Stars badge URL
  - [ ] Issues badge URL
  - [ ] Pull Requests badge URL
  - [ ] License badge URL

## Hosting Setup
Choose one:

### Local Hosting
- [ ] Ensure stable internet connection
- [ ] Configure firewall if necessary
- [ ] Set up auto-restart script (optional)

### Cloud Hosting
- [ ] Choose hosting provider
- [ ] Set up account and billing
- [ ] Configure environment variables
- [ ] Set up deployment method

## Final Checks
- [ ] Test database connection
- [ ] Test bot connection to Discord
- [ ] Verify all commands work
- [ ] Check logging system
- [ ] Backup database (if needed)
- [ ] Document any custom configurations

## Notes
- Keep your bot token secure and never share it
- Regularly backup your database
- Monitor bot's resource usage
- Join the support server for help: https://discord.gg/XcH8JmGaHZ

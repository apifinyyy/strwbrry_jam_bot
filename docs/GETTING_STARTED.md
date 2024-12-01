# Getting Started with Strwbrry Jam Bot 🍓

Welcome! This guide will help you get started with Strwbrry Jam Bot.

## 🎮 For Server Members

Just want to use the bot? It's easy!

1. **Use Commands**
   - Type `/help` to see all commands
   - Commands are grouped by category
   - Each command has a description

2. **Quick Commands**
   ```
   /profile           # View your profile
   /balance          # Check your money
   /daily            # Get daily rewards
   /shop             # Visit the shop
   /games            # List available games
   ```

3. **Need Help?**
   - Type `/help [command]` for detailed info
   - Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
   - Ask a server admin

## 👑 For Server Admins

Setting up the bot for your server:

1. **Quick Setup**
   ```
   /setup quickstart  # Run setup wizard
   /config           # View all settings
   /help admin       # View admin commands
   ```

2. **Essential Settings**
   - `/welcome setup` - Welcome messages
   - `/autorole set` - Auto-roles
   - `/modlog set` - Moderation logging
   - `/tickets setup` - Support tickets

3. **Recommended Features**
   - Set up auto-roles for new members
   - Configure welcome messages
   - Set up moderation logging
   - Enable auto-moderation

## 🛠️ For Developers

Want to host your own instance?

### Prerequisites
- Python 3.11+
- Git (optional)
- A Discord Bot Token

### Quick Setup

1. **Get the Code**
   ```bash
   git clone https://github.com/apifinyyy/strwbrry_jam_bot.git
   cd strwbrry_jam_bot
   ```

2. **Set Up Environment**
   ```bash
   python -m venv venv
   
   # On Windows
   .\venv\Scripts\activate
   
   # On Linux/Mac
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

3. **Configure Bot**
   - Copy `.env.example` to `.env`
   - Add your bot token and settings
   ```env
   DISCORD_TOKEN=your_token_here
   OWNER_ID=your_id_here
   ```

4. **Run the Bot**
   ```bash
   python main.py
   ```

### 🐛 Common Issues

1. **Bot Won't Start**
   - Check your `.env` file
   - Verify Python version (3.11+)
   - Look in `logs/bot.log`

2. **Commands Not Working**
   - Check bot permissions
   - Verify slash commands are synced
   - Enable required intents

3. **Need More Help?**
   - Check [Troubleshooting Guide](TROUBLESHOOTING.md)
   - Join Developer Support in our Discord
   - Open a GitHub issue

## 📚 Next Steps

- Read the [User Guide](USER_GUIDE.md)
- Check [Admin Guide](ADMIN_GUIDE.md) for advanced setup
- Join our [Support Server](https://discord.gg/XcH8JmGaHZ)
- Star us on [GitHub](https://github.com/apifinyyy/strwbrry_jam_bot)

---
Remember: The bot is designed to be user-friendly! If something isn't clear, let us know!

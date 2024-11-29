# Strwbrry Jam Bot 🍓

A feature-rich Discord utility bot with social features, economy system, games, and server management tools. Built with discord.py

## ✨ Features

### 🎭 Social System
- Rich profile customization
  * Multiple themes (default, night, sunset)
  * Custom titles and bios
  * Badge collection system
  * Dynamic profile cards
  * Achievement tracking
  * Interactive elements

### 🎮 Games & Activities
- Rock Paper Scissors
  * Player vs Bot matches
  * Currency rewards
  * Win tracking
- Trivia System
  * Various categories
  * Timed challenges
  * Score tracking
- Math Puzzles
  * Difficulty levels
  * Quick solve rewards
- Chat Games
  * Word chains
  * Type racing
  * Scramble words
- Gambling System
  * Fair odds
  * Loss protection
  * Betting limits

### 💰 Economy System
- Currency Management
  * Daily rewards
  * Weekly bonuses
  * Activity rewards
  * Game winnings
- Shop System
  * Role purchases
  * Custom items
  * Limited offers
- Leaderboards
  * Richest users
  * Most active
  * Top winners

### ⭐ Experience System
- Multi-Track XP
  * Chat activity XP
  * Voice time XP
  * Game participation XP
- Leaderboards
  * Server rankings
  * Category leaders
  * Progress tracking
- Role Rewards
  * Level-based roles
  * Activity rewards
  * Special perks

### 🎫 Support Tickets
- Advanced Ticket System
  * Custom categories
  * Priority levels
  * Staff assignment
- Management Tools
  * Archive system
  * Response templates
  * Status tracking

### 🎭 Role Management
- Automated Systems
  * Join roles
  * Level roles
  * Activity roles
- Custom Setup
  * Role hierarchy
  * Permission management
  * Role shop integration

### 👋 Welcome System
- Customizable Messages
  * Welcome messages
  * Goodbye messages
  * Custom formats
- Channel Configuration
  * Dedicated channels
  * Message formatting
  * Embed support
- Auto-Role System
  * Join roles
  * Verification roles
  * Level-based roles

### 📝 Server Logs
- Comprehensive Logging
  * Message events
  * Member activity
  * Role changes
  * Channel updates
- Custom Settings
  * Log channels
  * Event filters
  * Format options
- Detailed Embeds
  * Rich formatting
  * Event context
  * Time tracking

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Discord Bot Token

### Installation

1. Clone the repository:
```bash
git clone https://github.com/apifinyyy/strwbrry_jam_bot.git
cd strwbrry_jam_bot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file:
```env
DISCORD_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@localhost/database
```

5. Initialize the database:
```bash
psql -U postgres
CREATE DATABASE your_database_name;
```

6. Run the bot:
```bash
python main.py
```

## 📚 Documentation

- [API Documentation](docs/API.md) - Detailed API reference
- [Contributing Guide](CONTRIBUTING.md) - How to contribute
- [Changelog](CHANGELOG.md) - Version history

## 💻 Usage

### Basic Commands
- `/help` - View all commands
- `/config` - Configure bot settings
- `/profile` - View your profile
- `/economy` - View economy commands
- `/games` - View available games

### Admin Commands
- `/settings` - Server settings
- `/logs` - Configure logging
- `/autorole` - Setup auto roles
- `/tickets` - Manage ticket system

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🌟 Support

Join our [Discord Server](https://discord.gg/XcH8JmGaHZ) for support and updates.

## 📊 Stats

![GitHub Stars](https://img.shields.io/github/stars/apifinyyy/strwbrry_jam_bot)
![GitHub Issues](https://img.shields.io/github/issues/apifinyyy/strwbrry_jam_bot)
![GitHub Pull Requests](https://img.shields.io/github/issues-pr/apifinyyy/strwbrry_jam_bot)
![License](https://img.shields.io/github/license/apifinyyy/strwbrry_jam_bot)

## 🙏 Acknowledgments

- [discord.py](https://github.com/Rapptz/discord.py)
- [PostgreSQL](https://www.postgresql.org/)
- All our contributors

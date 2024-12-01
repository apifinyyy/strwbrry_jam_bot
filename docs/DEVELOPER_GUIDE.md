# Developer Guide 🛠️

This guide will help you set up your development environment and understand the project structure for contributing to Strwbrry Jam Bot.

## Table of Contents
- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Common Issues](#common-issues)

## Development Environment Setup

### Prerequisites
- Python 3.8 or higher
- Git
- A Discord account and access to the Discord Developer Portal
- Your favorite code editor (VS Code recommended)

### Initial Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/apifinyy/strwbrry_jam_bot.git
   cd strwbrry_jam_bot
   ```

2. **Set Up Virtual Environment**
   ```bash
   # Create virtual environment
   python -m venv venv

   # Activate virtual environment
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   # Copy example environment file
   cp .env.example .env

   # Edit .env with your settings:
   # - DISCORD_TOKEN: Your bot token from Discord Developer Portal
   # - Other configuration variables as needed
   ```

## Project Structure

```
strwbrry_jam_bot/
├── cogs/               # Bot command modules
├── data/              # Data storage
├── docs/              # Documentation
├── tests/             # Test files
├── utils/             # Utility functions
├── main.py            # Bot entry point
├── config.py          # Configuration handling
└── requirements.txt   # Project dependencies
```

### Key Components
- `cogs/`: Each file represents a category of bot commands
- `config.py`: Handles bot configuration and environment variables
- `utils/`: Helper functions and shared utilities
- `data/`: Storage for bot data and user information

## Development Workflow

1. **Create a New Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Development Guidelines**
   - Follow PEP 8 style guide
   - Add docstrings to all new functions/classes
   - Keep functions focused and single-purpose
   - Use type hints where possible

3. **Running the Bot Locally**
   ```bash
   python main.py
   ```

4. **Hot Reloading**
   - The bot supports hot reloading of cogs
   - Use `!reload <cog_name>` in Discord to reload a cog during development

## Testing

1. **Running Tests**
   ```bash
   # Run all tests
   python -m pytest

   # Run specific test file
   python -m pytest tests/test_specific.py

   # Run with coverage report
   python -m pytest --cov=.
   ```

2. **Writing Tests**
   - Place tests in the `tests/` directory
   - Name test files with `test_` prefix
   - Use pytest fixtures for common setup
   - Mock Discord.py components when needed

## Common Issues

### Bot Token Issues
- Ensure your token is correctly set in `.env`
- Verify token permissions in Discord Developer Portal
- Check for token revocation

### Dependencies
- If you get import errors, ensure your virtual environment is activated
- Try removing `venv` and reinstalling dependencies if issues persist

### Discord API
- Rate limiting: Implement cooldowns on commands
- Permissions: Check bot role hierarchy
- Gateway issues: Ensure proper intents are enabled

## Getting Help
- Check existing issues on GitHub
- Join our Discord support server
- Review Discord.py documentation

Remember to check our [Contributing Guidelines](../CONTRIBUTING.md) and [Code of Conduct](../CODE_OF_CONDUCT.md) before submitting any changes.

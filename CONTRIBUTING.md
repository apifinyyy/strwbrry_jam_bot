# Contributing to Strwbrry Jam Bot

Thank you for your interest in contributing to Strwbrry Jam Bot! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites
- Python 3.8 or higher
- PostgreSQL database
- Git

### Development Setup
1. Fork and clone the repository:
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
DISCORD_TOKEN=your_bot_token
DATABASE_URL=postgresql://user:password@localhost/database
```

5. Initialize the database:
```bash
psql -U postgres
CREATE DATABASE your_database_name;
```

## Code Style

### Python Guidelines
- Follow PEP 8 style guide
- Use type hints for function parameters and returns
- Add docstrings for all classes and functions
- Keep functions focused and under 50 lines
- Use meaningful variable names

### Discord.py Best Practices
- Use app commands (slash commands) for all new features
- Include command descriptions and parameter help
- Implement proper permission checks
- Handle all possible errors gracefully
- Use deferred responses for long operations

### Git Workflow
1. Create a new branch for your feature:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and commit them:
```bash
git add .
git commit -m "feat: your descriptive commit message"
```

3. Push to your fork:
```bash
git push origin feature/your-feature-name
```

4. Create a Pull Request

### Commit Message Format
Follow the Conventional Commits specification:
- feat: New feature
- fix: Bug fix
- docs: Documentation changes
- style: Code style changes
- refactor: Code refactoring
- test: Adding tests
- chore: Maintenance tasks

Example:
```
feat(social): add profile themes system

- Add theme selection command
- Implement theme color handling
- Add theme preview option
```

## Testing
- Write unit tests for new features
- Test your changes with the bot in a test server
- Ensure all existing tests pass
- Add integration tests for database operations

## Documentation
- Update API.md for new features
- Add JSDoc-style comments for complex functions
- Update README.md if adding major features
- Create examples for new commands

## Pull Request Process
1. Update relevant documentation
2. Add tests for new features
3. Ensure CI/CD passes
4. Request review from maintainers
5. Address review comments
6. Squash commits if requested

## Code Review
Your PR will be reviewed for:
- Code quality and style
- Test coverage
- Documentation
- Performance implications
- Security considerations

## Getting Help
- Create an issue for bug reports
- Join our Discord server for questions
- Check existing issues and PRs first
- Ask in #development channel

## License
By contributing, you agree that your contributions will be licensed under the project's license.

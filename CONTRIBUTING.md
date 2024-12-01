# Contributing to Strwbrry Jam Bot 🍓

First off, thank you for considering contributing to Strwbrry Jam Bot! This document provides guidelines and instructions for contributing.

## 📋 Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Process](#development-process)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## 📜 Code of Conduct

### Our Pledge
We pledge to make participation in our project a harassment-free experience for everyone.

### Our Standards
- Be respectful and inclusive
- Accept constructive criticism
- Focus on what's best for the community
- Show empathy towards others

## 🚀 Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/strwbrry_jam_bot.git
   ```
3. Create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```

## 💻 Development Process

### 1. Setting Up Development Environment
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Making Changes
1. Create a new branch for your feature
2. Write your code
3. Add tests
4. Update documentation
5. Run tests locally
6. Commit changes

### 3. Code Style
- Use [Black](https://github.com/psf/black) for formatting
- Follow PEP 8 guidelines
- Use type hints
- Add docstrings to all functions/classes
- Comment complex logic

Example:
```python
from typing import Optional

def my_function(param: str, optional_param: Optional[int] = None) -> bool:
    """
    Brief description of function.

    Args:
        param: Description of param
        optional_param: Description of optional_param

    Returns:
        Description of return value

    Raises:
        ValueError: Description of when this error occurs
    """
    pass
```

## 🔄 Pull Request Process

1. Update documentation
2. Run all tests
3. Update CHANGELOG.md
4. Submit PR with clear description
5. Wait for review
6. Address feedback
7. Get approval
8. Merge

### PR Title Format
- feat: Add new feature
- fix: Bug fix
- docs: Documentation changes
- style: Code style changes
- refactor: Code refactoring
- test: Add/modify tests
- chore: Maintenance tasks

## 📝 Coding Standards

### File Structure
```
strwbrry_jam_bot/
├── cogs/
│   ├── __init__.py
│   ├── template_cog.py
│   └── your_feature.py
├── utils/
│   └── helpers.py
└── tests/
    └── test_your_feature.py
```

### Cog Template
Use `cogs/template_cog.py` as base for new cogs:
```python
class YourFeature(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild('your_feature')

    @app_commands.command()
    async def your_command(self, interaction: discord.Interaction):
        """Command description"""
        pass

async def setup(bot):
    await bot.add_cog(YourFeature(bot))
```

## 🧪 Testing

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_your_feature.py

# Run with coverage
pytest --cov=.
```

### Writing Tests
```python
import pytest
from your_feature import YourFeature

@pytest.mark.asyncio
async def test_your_feature():
    # Setup
    bot = MockBot()
    cog = YourFeature(bot)
    
    # Test
    result = await cog.your_command()
    
    # Assert
    assert result == expected_result
```

## 📚 Documentation

### Docstring Format
```python
def function_name(param: type) -> return_type:
    """
    Brief description.

    Args:
        param: Parameter description

    Returns:
        Description of return value

    Raises:
        ErrorType: When error occurs
    """
    pass
```

### README Updates
- Keep feature list current
- Update setup instructions
- Document new commands
- Update troubleshooting

## ❓ Questions?

- Open an issue
- Join our Discord server
- Contact maintainers

Thank you for contributing! 🎉

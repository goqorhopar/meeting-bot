# Contributing to Meeting Bot

Thank you for considering contributing to Meeting Bot! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Welcome newcomers and help them learn

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues. When creating a bug report, include:

- Clear title and description
- Steps to reproduce the issue
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or screenshots

**Example:**
```markdown
**Bug**: Meeting recording fails on Linux

**Steps to Reproduce:**
1. Send meeting link to Telegram bot
2. Wait for processing
3. See error in logs

**Expected:** Audio file created
**Actual:** FileNotFoundError for ffmpeg

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.11
- Version: 1.0.0
```

### Suggesting Features

Feature suggestions are welcome! Please provide:

- Clear description of the feature
- Use case and benefits
- Possible implementation approach
- Any alternatives considered

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`make test` or `pytest tests/`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/meeting-bot.git
cd meeting-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies

# Install Node.js dependencies
npm install

# Set up environment
cp .env.example .env
# Edit .env with your values

# Run tests
pytest tests/ -v

# Run linting
flake8 *.py
black --check *.py
```

## Coding Standards

### Python

- Follow PEP 8 style guide
- Use type hints where possible
- Write docstrings for public functions
- Keep functions small and focused
- Use meaningful variable names

**Example:**
```python
from typing import Optional
from datetime import datetime, timezone


async def send_telegram_message(text: str) -> bool:
    """Send message to configured Telegram user with retry logic.
    
    Args:
        text: Message text to send
        
    Returns:
        True if message sent successfully, False otherwise
        
    Raises:
        None: Exceptions are handled internally
    """
    if not bot or not TELEGRAM_USER_ID:
        logger.warning("Telegram bot or user ID not configured")
        return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)
            return True
        except Exception as e:
            logger.error(f"Failed to send message (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))
    return False
```

### JavaScript/Node.js

- Use ES6+ features
- Use async/await for asynchronous code
- Add JSDoc comments for public functions
- Handle errors gracefully

### Testing

- Write tests for new features
- Maintain >80% code coverage
- Include unit tests and integration tests
- Test edge cases and error conditions

**Running Tests:**
```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=. --cov-report=html

# Specific test file
pytest tests/test_main.py -v

# Specific test class
pytest tests/test_main.py::TestConfig -v
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Telegram  │────▶│  FastAPI App │────▶│ LangChain Agent │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    │                              │                              │
                    ▼                              ▼                              ▼
          ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
          │   Puppeteer     │           │    Whisper      │           │    Bitrix24     │
          │  (Join Meeting) │           │  (Transcribe)   │           │   (Update CRM)  │
          └─────────────────┘           └────────┬────────┘           └─────────────────┘
                                                 │
                                                 ▼
                                        ┌─────────────────┐
                                        │   Gemini AI     │
                                        │   (Analyze)     │
                                        └─────────────────┘
```

## Release Process

1. Update version in `main.py` and `package.json`
2. Update CHANGELOG.md
3. Create release tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
4. Push tag: `git push origin --tags`
5. Create GitHub release with changelog

## Questions?

Feel free to open an issue for any questions or discussions.

---

Thank you for contributing to Meeting Bot! 🚀

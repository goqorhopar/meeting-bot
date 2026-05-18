# Meeting Bot - Production-Ready AI Meeting Analysis

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-AI-orange.svg)](https://ai.google.dev)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://docker.com)

**AI-powered meeting assistant** that automatically joins video meetings, records audio, transcribes conversations using Whisper, analyzes them with Gemini AI, and updates CRM leads in Bitrix24.

## Features

- **Automated Meeting Participation** - Joins Google Meet, Zoom, and Teams via headless browser
- **Audio Recording** - Captures meeting audio using ffmpeg
- **Speech-to-Text** - Transcribes audio using OpenAI Whisper
- **AI Analysis** - Generates structured reports with Gemini AI
- **CRM Integration** - Automatically updates Bitrix24 leads
- **Telegram Control** - Simple command interface
- **Production Ready** - Health checks, error handling, logging, Docker

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run
uvicorn main:app --host 0.0.0.0 --port 8080
```

## Docker

```bash
docker build -t meeting-bot .
docker run -d -p 8080:8080 --env-file .env meeting-bot
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Yes |
| `TELEGRAM_USER_ID` | Authorized Telegram user ID | Yes |
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `BITRIX_WEBHOOK_URL` | Bitrix24 webhook URL | Yes |
| `WHISPER_MODEL` | Whisper model (tiny/base/small/medium/large) | No (default: base) |
| `LOG_LEVEL` | Logging level | No (default: INFO) |

## Usage

Send to Telegram bot:
```
https://meet.google.com/abc-defg-hij id:123
```

Where `id:123` is the optional Bitrix24 lead ID.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health status |
| `/ready` | GET | Readiness probe |
| `/webhook` | POST | Telegram webhook |

## Project Structure

```
meeting-bot/
├── main.py              # FastAPI server + LangChain Agent
├── config.py            # Configuration management
├── tools.py             # Meeting processing tools
├── join-meeting.js      # Puppeteer for joining meetings
├── requirements.txt     # Python dependencies
├── package.json         # Node.js dependencies
├── Dockerfile           # Docker configuration
├── .env.example         # Environment template
└── README.md            # Documentation
```

## Architecture

```
Telegram → FastAPI → LangChain Agent → Tools
                                    ├── Join Meeting (Puppeteer)
                                    ├── Transcribe (Whisper)
                                    ├── Analyze (Gemini)
                                    └── Update CRM (Bitrix24)
```

## License

MIT License

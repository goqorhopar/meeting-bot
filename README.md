# Meeting Bot - Production-Ready AI Meeting Analysis System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-AI-orange.svg)](https://ai.google.dev)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Enterprise-grade AI meeting assistant** that automatically joins video meetings, records audio, transcribes conversations using Whisper, analyzes them with Gemini AI, and updates CRM leads in Bitrix24.

## 🚀 Features

### Core Functionality
- **Automated Meeting Participation** - Joins Google Meet, Zoom, and Teams via headless browser (Puppeteer)
- **Audio Recording** - Captures meeting audio using ffmpeg with virtual audio devices
- **Speech-to-Text** - Transcribes audio using OpenAI Whisper (multiple model sizes supported)
- **AI Analysis** - Generates structured reports with Gemini 1.5 Flash AI
- **CRM Integration** - Automatically updates Bitrix24 leads with analysis results
- **Telegram Control** - Simple command interface via Telegram bot
- **Rate Limiting** - Built-in rate limiting with Redis backend

### Production Features
- **Health Checks** - `/health` and `/ready` endpoints for monitoring
- **Structured Logging** - JSON-formatted logs with configurable levels
- **Error Handling** - Comprehensive exception handling with graceful degradation
- **Security** - CORS configuration, authentication, input validation
- **Docker Ready** - Multi-stage Dockerfile with health checks
- **Scalable** - Supports horizontal scaling with Redis-backed rate limiting
- **Resource Limits** - Configurable CPU/memory constraints

## 📋 Prerequisites

- Python 3.11+
- Node.js 20.x
- ffmpeg
- Google Gemini API key
- Telegram Bot token
- Bitrix24 webhook URL (optional)

## 🏃 Quick Start

### Local Development

```bash
# Clone repository
git clone <repository-url>
cd meeting-bot

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run the application
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Docker Deployment

```bash
# Build and run with Docker Compose (recommended)
docker-compose up -d

# Or build and run manually
docker build -t meeting-bot .
docker run -d -p 8080:8080 --env-file .env meeting-bot
```

## ⚙️ Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_USER_ID` | Your Telegram user ID (from @userinfobot) | `123456789` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |
| `BITRIX_WEBHOOK_URL` | Bitrix24 inbound webhook URL | `https://your-bitrix24.rest/id/webhook` |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Whisper model (tiny/base/small/medium/large) | `base` |
| `AUDIO_DEVICE` | Audio device name for recording | `pulse` |
| `MEETING_TIMEOUT` | Maximum meeting duration (seconds) | `3600` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `REDIS_URL` | Redis connection URL for rate limiting | `redis://localhost:6379` |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | `*` |
| `ENVIRONMENT` | Environment name (development/production) | `development` |

## 📡 API Endpoints

| Endpoint | Method | Description | Auth | Rate Limit |
|----------|--------|-------------|------|------------|
| `/` | GET | Health check with timestamp | None | None |
| `/health` | GET | Detailed health status | None | None |
| `/ready` | GET | Kubernetes readiness probe | None | None |
| `/webhook` | POST | Telegram webhook endpoint | User ID check | 10/min |

### Health Check Response

```json
{
  "status": "healthy",
  "config_valid": true,
  "missing_config": null,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## 💬 Usage

Send a message to your Telegram bot with the meeting URL:

```
https://meet.google.com/abc-defg-hij id:123
```

Where:
- `https://meet.google.com/abc-defg-hij` - Meeting URL
- `id:123` - (Optional) Bitrix24 lead ID

### Supported Meeting Platforms

- ✅ Google Meet
- ✅ Zoom
- ✅ Microsoft Teams (limited)

## 🏗️ Architecture

```
Telegram Bot → FastAPI Server → LangChain Agent
                                    ├── Puppeteer (Join Meeting)
                                    ├── Whisper (Transcribe)
                                    ├── Gemini AI (Analyze)
                                    └── Bitrix24 (Update Lead)
```

## 📁 Project Structure

```
meeting-bot/
├── main.py                 # FastAPI server + LangChain Agent
├── config.py               # Configuration management
├── tools.py                # Meeting processing tools
├── join-meeting.js         # Puppeteer script for joining meetings
├── requirements.txt        # Python dependencies
├── package.json            # Node.js dependencies
├── Dockerfile              # Docker configuration
├── docker-compose.yml      # Docker Compose configuration
├── .env.example            # Environment template
├── .gitignore              # Git ignore rules
├── render.yaml             # Render deployment config
├── railway-toml            # Railway deployment config
└── README.md               # This file
```

## 🧪 Testing

```bash
# Run syntax check
python -m py_compile main.py config.py tools.py

# Test health endpoint
curl http://localhost:8080/health

# Test webhook (replace with actual data)
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":{"from":{"id":"YOUR_USER_ID"},"text":"https://meet.google.com/test"}}'
```

## 🔒 Security Considerations

### Implemented Security Measures

1. **Authentication** - Webhook validates Telegram user ID
2. **Rate Limiting** - 10 requests per minute per IP (Redis-backed)
3. **CORS** - Configurable allowed origins
4. **Input Validation** - URL parsing and sanitization
5. **Environment Variables** - Secrets stored in environment, not code
6. **Health Checks** - Separate endpoints for liveness/readiness

### Security Recommendations

- Never commit `.env` file to version control
- Use HTTPS in production
- Rotate API keys regularly
- Restrict CORS origins in production
- Monitor rate limit violations
- Enable audit logging for compliance

## 🚢 Deployment

### Docker Compose (Recommended)

```bash
docker-compose up -d
```

### Render

1. Connect your GitHub repository
2. Set environment variables
3. Deploy automatically on push

### Railway

1. Import from GitHub
2. Configure environment variables
3. Deploy automatically

## 🔧 Troubleshooting

### Common Issues

**Issue: Puppeteer fails to launch**
```
Solution: Ensure all Chrome dependencies are installed
- Docker: Already included in Dockerfile
- Linux: sudo apt-get install -y chromium-browser
- macOS: brew install chromium
```

**Issue: Audio recording fails**
```
Solution: Check audio device configuration
- Windows: Install VB-Audio Virtual Cable
- Linux: Use PulseAudio or ALSA
- macOS: Install BlackHole
```

**Issue: Whisper transcription slow**
```
Solution: Use smaller model or upgrade hardware
- Set WHISPER_MODEL=tiny for faster processing
- Use GPU acceleration if available
```

## 📄 License

MIT License - see LICENSE file for details

---

**Built with ❤️ for enterprise-grade meeting analysis**

*Last updated: January 2024*

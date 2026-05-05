# Meeting Bot (Python)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-AI-orange.svg)](https://ai.google.dev)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://docker.com)

AI-ассистент для анализа встреч на Python: подключается к видеовстречам, записывает аудио, расшифровывает через Whisper, анализирует через Gemini AI и обновляет лиды в Bitrix24.

## Возможности

- **Запись аудио** с встреч через ffmpeg + виртуальный аудиокабель
- **Транскрипция** через OpenAI Whisper
- **Анализ Gemini AI** — структурированный отчёт (резюме, следующие шаги, решения, вопросы, статус лида)
- **Управление через Telegram** — отправьте ссылку, получите готовый отчёт
- **Интеграция с Bitrix24** — автообновление лидов с результатами встречи
- **FastAPI вебхуки** для приёма команд

## Быстрый старт

```bash
# Установка
pip install -r requirements.txt

# Настройка — создайте .env:
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_USER_ID=...
# GEMINI_API_KEY=...
# BITRIX_WEBHOOK_URL=...

# Запуск
uvicorn main:app --port 8080
```

## Docker

```bash
docker build -t meeting-bot-python .
docker run -d --env-file .env meeting-bot-python
```

## Архитектура

```
┌─────────────┐     ┌──────────┐     ┌─────────┐     ┌────────────┐
│  Telegram   │────▶│ FastAPI  │────▶│  Agent  │────▶│   Tools    │
│  Webhook    │     │ Server   │     │(LangChain)│    │            │
└─────────────┘     └──────────┘     └─────────┘     ├────────────┤
                                                     │ join_meeting│
                                                     │ transcribe  │
                                                     │ analyze     │
                                                     │ update_bitrix│
                                                     └────────────┘
```

## Структура

```
├── main.py          # FastAPI сервер + LangChain Agent
├── config.py        # Конфигурация и переменные окружения
├── tools.py         # Инструменты агента (запись, транскрипция, анализ)
├── join-meeting.js  # Скрипт подключения к встрече (Puppeteer)
├── requirements.txt
├── Dockerfile
└── render.yaml
```

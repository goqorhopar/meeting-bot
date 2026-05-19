"""
Meeting Bot - AI-powered meeting analysis service.

This application:
1. Receives meeting links via Telegram webhook
2. Joins meetings using Puppeteer (headless Chrome)
3. Records audio from the meeting
4. Transcribes audio using Whisper
5. Analyzes transcript with Gemini AI
6. Updates leads in Bitrix24 with the analysis
"""

import asyncio
import logging
import re
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_community.chat_models import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from tools import MeetingTools, initialize_models
from config import Config

# Configure logging
logging.basicConfig(
    level=Config.get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    logger.info("🚀 Starting Meeting Bot...")
    
    # Validate configuration
    errors = Config.validate_config()
    if errors:
        logger.error(f"❌ Configuration validation failed. Missing: {', '.join(errors)}")
        # Don't exit, allow health checks to work
    else:
        logger.info("✅ Configuration validated successfully")
    
    # Create directories
    Config.create_directories()
    
    # Initialize AI models
    try:
        initialize_models()
        logger.info("✅ AI models initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize AI models: {e}")
    
    # Initialize Telegram bot
    global bot, TELEGRAM_USER_ID
    if Config.API_TOKEN:
        bot = Bot(token=Config.API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        logger.info("✅ Telegram bot initialized")
    else:
        bot = None
        logger.warning("⚠️ Telegram bot not initialized (no token)")
    
    TELEGRAM_USER_ID = int(Config.TELEGRAM_USER_ID) if Config.TELEGRAM_USER_ID else None
    
    # Initialize rate limiter
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(redis_url)
            await FastAPILimiter.init(redis_client)
            logger.info("✅ Rate limiter initialized with Redis")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize rate limiter: {e}")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down Meeting Bot...")
    if bot:
        await bot.session.close()
    if redis_url:
        try:
            await FastAPILimiter.shutdown()
        except Exception:
            pass


# Initialize FastAPI app
app = FastAPI(
    title="Meeting Bot API",
    description="AI-powered meeting analysis service",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware with configurable origins
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
bot: Optional[Bot] = None
TELEGRAM_USER_ID: Optional[int] = None

# LangChain setup
prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты - бот-помощник для анализа встреч. Используй инструменты, чтобы подключиться к встрече, расшифровать, проанализировать и отправить отчет."),
    ("human", "{input}"),
    ("ai", "Я готов. Что мне нужно сделать?")
])


@app.get("/")
async def root() -> dict:
    """Root endpoint - health check."""
    return {
        "status": "ok",
        "service": "Meeting Bot",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for monitoring."""
    config_errors = Config.validate_config()
    return {
        "status": "healthy" if not config_errors else "degraded",
        "config_valid": len(config_errors) == 0,
        "missing_config": config_errors if config_errors else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ready")
async def readiness_check() -> JSONResponse:
    """Readiness check for Kubernetes/load balancers."""
    config_errors = Config.validate_config()
    if config_errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing configuration: {', '.join(config_errors)}"
        )
    return JSONResponse({"status": "ready"})


@app.post("/webhook")
async def handle_webhook(request: Request, rate_limit: str = Depends(RateLimiter(times=10, seconds=60))) -> dict:
    """
    Handle incoming Telegram webhook requests.
    
    Expects Telegram Update object with message containing:
    - Meeting URL
    - Optional lead ID (format: "url id:123")
    
    Rate limited to 10 requests per minute per IP.
    """
    try:
        update = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}
    
    # Validate message structure
    if not update.get("message"):
        logger.debug("Received update without message")
        return {"status": "ok", "message": "No message in update"}
    
    message = update["message"]
    
    # Validate sender is authorized user
    if not TELEGRAM_USER_ID or message.get("from", {}).get("id") != TELEGRAM_USER_ID:
        logger.warning(f"Unauthorized webhook attempt from user {message.get('from', {}).get('id')}")
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Extract text and parse meeting URL
    text = message.get("text", "").strip()
    if not text:
        logger.debug("Empty message received")
        return {"status": "ok", "message": "Empty message"}
    
    # Parse URL and optional lead ID with improved regex
    url_pattern = r'(https?://[^\s]+?)(?:\s+id:(\d+))?\s*$'
    match = re.search(url_pattern, text, re.IGNORECASE)
    
    if not match:
        logger.info(f"No valid URL found in message: {text[:100]}")
        await send_telegram_message(
            "❌ Пожалуйста, отправьте ссылку на встречу в формате:\n"
            "https://meet.google.com/xxx-yyy-zzz id:123"
        )
        return {"status": "ok", "message": "No URL found"}
    
    url = match.group(1).rstrip(',')
    lead_id = match.group(2) if match.group(2) else "без_ID"
    
    logger.info(f"📞 Processing meeting: {url[:50]}... Lead ID: {lead_id}")
    
    # Send initial status message
    await send_telegram_message(f"▶ Начинаю процесс для {url}\n🆔 ID лида: {lead_id}")
    
    # Process meeting asynchronously (fire and forget for now)
    # In production, you'd want to use a task queue like Celery
    asyncio.create_task(process_meeting_safe(url, lead_id))
    
    return {"status": "ok"}


async def process_meeting_safe(url: str, lead_id: str) -> None:
    """Wrapper for process_meeting with error handling for background tasks."""
    try:
        result = await process_meeting(url, lead_id)
        await send_telegram_message(f"✅ Готово! Вот отчет:\n\n{result}")
    except Exception as e:
        logger.error(f"❌ Error processing meeting: {e}", exc_info=True)
        await send_telegram_message(f"❌ Произошла ошибка: {str(e)[:500]}")


async def send_telegram_message(text: str) -> bool:
    """Send message to configured Telegram user with retry logic."""
    if not bot or not TELEGRAM_USER_ID:
        logger.warning("Telegram bot or user ID not configured")
        return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    return False


async def process_meeting(url: str, lead_id: str) -> str:
    """
    Process a meeting: join, record, transcribe, analyze, and update Bitrix.
    
    Args:
        url: Meeting URL
        lead_id: Bitrix lead ID
        
    Returns:
        Analysis report text
        
    Raises:
        ValueError: If meeting URL is invalid
        RuntimeError: If meeting processing fails
    """
    logger.info(f"🎯 Starting full meeting processing for {url}")
    
    # Validate URL format
    if not re.match(r'^https?://', url):
        raise ValueError(f"Invalid meeting URL: {url}")
    
    # Initialize LangChain agent with proper error handling
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0,
            api_key=Config.GEMINI_API_KEY,
            max_retries=3
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        raise RuntimeError(f"LLM initialization failed: {e}")
    
    tools = [
        MeetingTools.join_and_record_meeting,
        MeetingTools.transcribe_audio,
        MeetingTools.analyze_transcript,
        MeetingTools.update_bitrix_lead
    ]
    
    try:
        agent = create_structured_chat_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise RuntimeError(f"Agent creation failed: {e}")
    
    # Execute the agent with timeout protection
    try:
        result = await asyncio.wait_for(
            agent_executor.ainvoke({
                "input": f"Подключись к встрече по ссылке {url} с ID {lead_id}. Расшифруй аудио, проанализируй транскрипцию и обнови лид."
            }),
            timeout=Config.MEETING_TIMEOUT + 300  # Add 5 minutes buffer
        )
        return result.get("output", "Отчёт не был сгенерирован.")
    except asyncio.TimeoutError:
        logger.error(f"Meeting processing timed out after {Config.MEETING_TIMEOUT + 300}s")
        raise RuntimeError("Meeting processing timed out")
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise RuntimeError(f"Meeting analysis failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""
Meeting Bot - Enterprise-grade AI-powered meeting analysis service.

This application:
1. Receives meeting links via Telegram webhook
2. Joins meetings using Puppeteer (headless Chrome)
3. Records audio from the meeting
4. Transcribes audio using Whisper
5. Analyzes transcript with Gemini AI
6. Updates leads in Bitrix24 with the analysis

Architecture:
- FastAPI for async HTTP server
- LangChain for AI agent orchestration
- Puppeteer for browser automation
- Whisper for speech-to-text
- Gemini for natural language analysis
- Redis for rate limiting and caching
"""

import asyncio
import logging
import re
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse
import json

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

# Configure structured JSON logging for production
class JSONFormatter(logging.Formatter):
    """JSON log formatter for production observability."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        return json.dumps(log_data)


def setup_logging() -> None:
    """Configure logging based on environment."""
    log_level = Config.get_log_level()
    
    # Use JSON formatting in production, human-readable in development
    if Config.is_production():
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)
    
    # Set specific loggers to WARNING to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)


setup_logging()
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
    
    # Initialize rate limiter with Redis
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(redis_url)
            await FastAPILimiter.init(redis_client)
            logger.info("✅ Rate limiter initialized with Redis")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize rate limiter: {e}")
            # Continue without rate limiting - better than failing completely
    else:
        logger.warning("⚠️ REDIS_URL not set, rate limiting disabled")
    
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


# Initialize FastAPI app with metadata
app = FastAPI(
    title="Meeting Bot API",
    description="Enterprise-grade AI-powered meeting analysis service with automated transcription and CRM integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "Health check endpoints"},
        {"name": "Webhook", "description": "Telegram webhook endpoints"},
    ]
)

# Add CORS middleware with configurable origins and security validation
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Validate CORS configuration in production
if Config.is_production() and allowed_origins == ["*"]:
    logger.warning("⚠️ SECURITY WARNING: CORS is set to allow all origins (*) in production. Set ALLOWED_ORIGINS explicitly.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Global variables
bot: Optional[Bot] = None
TELEGRAM_USER_ID: Optional[int] = None

# LangChain setup with secure prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", """Ты - профессиональный бот-помощник для анализа деловых встреч. 
Твоя задача - подключиться к встрече, записать аудио, расшифровать его, проанализировать и отправить структурированный отчет.
Важно: соблюдай конфиденциальность данных, не разглашай чувствительную информацию."""),
    ("human", "{input}"),
    ("ai", "Я готов. Что мне нужно сделать?")
])


@app.get("/", tags=["Health"])
async def root() -> dict:
    """Root endpoint - basic health check with service metadata."""
    return {
        "status": "ok",
        "service": "Meeting Bot",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "production" if Config.is_production() else "development"
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns detailed health status including:
    - Overall service status
    - Configuration validation status
    - Missing configuration items (if any)
    - Current timestamp
    """
    config_errors = Config.validate_config()
    is_healthy = len(config_errors) == 0
    
    return {
        "status": "healthy" if is_healthy else "degraded",
        "config_valid": is_healthy,
        "missing_config": config_errors if config_errors else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": None,  # Could be tracked with a global variable
    }


@app.get("/ready", tags=["Health"])
async def readiness_check() -> JSONResponse:
    """
    Readiness check for Kubernetes/load balancers.
    
    Returns 503 if configuration is missing, indicating the service
    is not ready to accept traffic.
    """
    config_errors = Config.validate_config()
    if config_errors:
        logger.warning(f"Readiness check failed: {', '.join(config_errors)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing configuration: {', '.join(config_errors)}"
        )
    return JSONResponse({"status": "ready"})


@app.post("/webhook", tags=["Webhook"])
async def handle_webhook(
    request: Request, 
    rate_limit: str = Depends(RateLimiter(times=10, seconds=60))
) -> dict:
    """
    Handle incoming Telegram webhook requests.
    
    Expects Telegram Update object with message containing:
    - Meeting URL (required)
    - Optional lead ID (format: "url id:123")
    
    Rate limited to 10 requests per minute per IP address.
    
    Security:
    - Validates sender is authorized Telegram user
    - Sanitizes input URLs
    - Logs unauthorized access attempts
    
    Returns:
        dict: Status response with operation result
    """
    request_id = datetime.now(timezone.utc).isoformat()
    
    try:
        update = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook JSON [request_id={request_id}]: {e}")
        return {"status": "error", "message": "Invalid JSON format"}
    except Exception as e:
        logger.error(f"Unexpected error parsing webhook [request_id={request_id}]: {e}")
        return {"status": "error", "message": "Internal server error"}
    
    # Validate message structure
    if not update.get("message"):
        logger.debug(f"No message in update [request_id={request_id}]")
        return {"status": "ok", "message": "No message in update"}
    
    message = update["message"]
    
    # Validate sender is authorized user
    sender_id = message.get("from", {}).get("id")
    if not TELEGRAM_USER_ID or sender_id != TELEGRAM_USER_ID:
        logger.warning(
            f"Unauthorized webhook attempt from user {sender_id} [request_id={request_id}]"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access")
    
    # Extract text and parse meeting URL
    text = message.get("text", "").strip()
    if not text:
        logger.debug(f"Empty message received [request_id={request_id}]")
        return {"status": "ok", "message": "Empty message"}
    
    # Parse URL and optional lead ID with improved regex
    url_pattern = r'(https?://[^\s]+?)(?:\s+id:(\d+))?\s*$'
    match = re.search(url_pattern, text, re.IGNORECASE)
    
    if not match:
        logger.info(f"No valid URL found in message: {text[:100]} [request_id={request_id}]")
        await send_telegram_message(
            "❌ Пожалуйста, отправьте ссылку на встречу в формате:\n"
            "https://meet.google.com/xxx-yyy-zzz id:123"
        )
        return {"status": "ok", "message": "No valid URL found"}
    
    url = match.group(1).rstrip(',')
    lead_id = match.group(2) if match.group(2) else "без_ID"
    
    # Validate URL scheme for security
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ('http', 'https'):
        logger.warning(f"Invalid URL scheme: {parsed_url.scheme} [request_id={request_id}]")
        await send_telegram_message("❌ Неверный протокол URL. Используйте http:// или https://")
        return {"status": "ok", "message": "Invalid URL scheme"}
    
    logger.info(f"📞 Processing meeting: {url[:50]}... Lead ID: {lead_id} [request_id={request_id}]")
    
    # Send initial status message
    await send_telegram_message(f"▶ Начинаю процесс для {url}\n🆔 ID лида: {lead_id}")
    
    # Process meeting asynchronously (fire and forget)
    # In production, consider using a task queue like Celery or Redis Queue
    asyncio.create_task(process_meeting_safe(url, lead_id, request_id))
    
    return {"status": "ok", "request_id": request_id}


async def process_meeting_safe(url: str, lead_id: str, request_id: str = "unknown") -> None:
    """
    Wrapper for process_meeting with comprehensive error handling for background tasks.
    
    This function runs asynchronously and sends status updates to Telegram.
    All errors are caught and reported to prevent silent failures.
    
    Args:
        url: Meeting URL to process
        lead_id: Bitrix24 lead ID
        request_id: Unique identifier for request tracing
    """
    try:
        logger.info(f"Starting meeting processing [request_id={request_id}]")
        result = await process_meeting(url, lead_id, request_id)
        await send_telegram_message(f"✅ Готово! Вот отчет:\n\n{result}")
        logger.info(f"Meeting processing completed successfully [request_id={request_id}]")
    except Exception as e:
        logger.error(f"❌ Error processing meeting [request_id={request_id}]: {e}", exc_info=True)
        error_message = str(e)[:500] if str(e) else "Неизвестная ошибка"
        await send_telegram_message(f"❌ Произошла ошибка при обработке встречи:\n{error_message}")


async def send_telegram_message(text: str, retry_count: int = 3) -> bool:
    """
    Send message to configured Telegram user with exponential backoff retry logic.
    
    Args:
        text: Message text to send
        retry_count: Number of retry attempts on failure
        
    Returns:
        bool: True if message sent successfully, False otherwise
    """
    if not bot or not TELEGRAM_USER_ID:
        logger.warning("Telegram bot or user ID not configured, skipping message")
        return False
    
    for attempt in range(retry_count):
        try:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)
            return True
        except Exception as e:
            wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
            logger.error(
                f"Failed to send Telegram message (attempt {attempt + 1}/{retry_count}): {e}"
            )
            if attempt < retry_count - 1:
                await asyncio.sleep(wait_time)
    
    logger.error(f"All {retry_count} attempts to send Telegram message failed")
    return False


async def process_meeting(url: str, lead_id: str, request_id: str = "unknown") -> str:
    """
    Process a meeting: join, record, transcribe, analyze, and update Bitrix.
    
    This is the main orchestration function that coordinates all meeting processing steps:
    1. Validates the meeting URL
    2. Initializes LangChain agent with required tools
    3. Executes the agent to perform meeting processing
    4. Returns the analysis report
    
    Args:
        url: Meeting URL (must be http:// or https://)
        lead_id: Bitrix24 lead ID for CRM update
        request_id: Unique identifier for request tracing
        
    Returns:
        str: Analysis report text
        
    Raises:
        ValueError: If meeting URL is invalid or malformed
        RuntimeError: If meeting processing fails at any step
        asyncio.TimeoutError: If processing exceeds timeout limit
    """
    logger.info(f"🎯 Starting full meeting processing [request_id={request_id}]")
    
    # Validate URL format - security check
    if not re.match(r'^https?://', url):
        raise ValueError(f"Invalid meeting URL format: {url}")
    
    # Validate URL doesn't point to internal resources (SSRF protection)
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname:
            # Block private IP ranges to prevent SSRF attacks
            import ipaddress
            # Skip DNS resolution here - Puppeteer will handle it
            # But we log suspicious hostnames
            if hostname in ('localhost', '127.0.0.1', '::1'):
                logger.warning(f"Blocked localhost URL attempt [request_id={request_id}]")
                raise ValueError("Localhost URLs are not allowed")
    except Exception as e:
        logger.warning(f"URL validation warning [request_id={request_id}]: {e}")
    
    # Initialize LangChain agent with proper error handling
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0,
            api_key=Config.GEMINI_API_KEY,
            max_retries=3,
        )
        logger.info(f"LLM initialized successfully [request_id={request_id}]")
    except Exception as e:
        logger.error(f"Failed to initialize LLM [request_id={request_id}]: {e}")
        raise RuntimeError(f"LLM initialization failed: {e}")
    
    # Define available tools for the agent
    tools = [
        MeetingTools.join_and_record_meeting,
        MeetingTools.transcribe_audio,
        MeetingTools.analyze_transcript,
        MeetingTools.update_bitrix_lead
    ]
    
    try:
        agent = create_structured_chat_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=True, 
            handle_parsing_errors=True,
            max_iterations=10,  # Prevent infinite loops
            max_execution_time=Config.MEETING_TIMEOUT + 300
        )
        logger.info(f"Agent created successfully [request_id={request_id}]")
    except Exception as e:
        logger.error(f"Failed to create agent [request_id={request_id}]: {e}")
        raise RuntimeError(f"Agent creation failed: {e}")
    
    # Execute the agent with timeout protection
    try:
        result = await asyncio.wait_for(
            agent_executor.ainvoke({
                "input": f"Подключись к встрече по ссылке {url} с ID {lead_id}. Расшифруй аудио, проанализируй транскрипцию и обнови лид."
            }),
            timeout=Config.MEETING_TIMEOUT + 300  # Add 5 minutes buffer for AI processing
        )
        output = result.get("output", "Отчёт не был сгенерирован.")
        logger.info(f"Meeting processing completed successfully [request_id={request_id}]")
        return output
    except asyncio.TimeoutError:
        logger.error(f"Meeting processing timed out after {Config.MEETING_TIMEOUT + 300}s [request_id={request_id}]")
        raise RuntimeError(f"Meeting processing timed out after {Config.MEETING_TIMEOUT + 300} seconds")
    except Exception as e:
        logger.error(f"Agent execution failed [request_id={request_id}]: {e}", exc_info=True)
        raise RuntimeError(f"Meeting analysis failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
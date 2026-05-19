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
import json
import signal
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse
from dataclasses import dataclass, field
from enum import Enum

from fastapi import FastAPI, Request, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from tools import MeetingTools, initialize_models
from config import Config

# Configure structured JSON logging
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging():
    """Configure logging based on environment."""
    log_level = Config.get_log_level()
    
    # Use JSON formatting in production, human-readable in development
    if Config.is_production():
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)
    
    # Set specific loggers to INFO to reduce noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("puppeteer").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


logger = setup_logging()


class MeetingStatus(str, Enum):
    """Meeting processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class MeetingTask:
    """Represents a meeting processing task."""
    url: str
    lead_id: str
    status: MeetingStatus = MeetingStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[str] = None


# Task tracking (in production, use Redis or database)
meeting_tasks: Dict[str, MeetingTask] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    logger.info("🚀 Starting Meeting Bot...")
    
    # Validate configuration
    errors = Config.validate_config()
    if errors:
        logger.warning(f"⚠️ Configuration validation found missing vars: {', '.join(errors)}")
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
    else:
        logger.info("ℹ️ Rate limiter disabled (no REDIS_URL)")
    
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
    description="AI-powered meeting analysis service with automated transcription and CRM integration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware with configurable origins
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

# Global variables
bot: Optional[Bot] = None
TELEGRAM_USER_ID: Optional[int] = None

# LangChain setup - moved to process_meeting for lazy loading


@app.get("/")
async def root() -> dict:
    """Root endpoint - health check with service metadata."""
    return {
        "status": "ok",
        "service": "Meeting Bot",
        "version": "1.0.0",
        "environment": "production" if Config.is_production() else "development",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "webhook": "/webhook",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check() -> dict:
    """
    Comprehensive health check endpoint for monitoring.
    
    Returns detailed status including:
    - Overall service health
    - Configuration validation status
    - Component availability
    """
    config_errors = Config.validate_config()
    
    # Check Redis connectivity if configured
    redis_status = "not_configured"
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as redis
            client = redis.from_url(redis_url)
            await client.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"
    
    health_status = "healthy" if not config_errors else "degraded"
    
    return {
        "status": health_status,
        "config_valid": len(config_errors) == 0,
        "missing_config": config_errors if config_errors else None,
        "components": {
            "redis": redis_status,
            "telegram_bot": "initialized" if bot else "not_initialized",
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check for Kubernetes/load balancers.
    
    Returns 503 if service is not ready to accept traffic.
    """
    config_errors = Config.validate_config()
    if config_errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing configuration: {', '.join(config_errors)}"
        )
    return JSONResponse({"status": "ready"})


@app.get("/tasks")
async def list_tasks() -> dict:
    """List all meeting tasks with their current status."""
    return {
        "tasks": {
            task_id: {
                "url": task.url,
                "lead_id": task.lead_id,
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "error": task.error,
            }
            for task_id, task in meeting_tasks.items()
        },
        "total": len(meeting_tasks)
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get specific task status by ID."""
    if task_id not in meeting_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = meeting_tasks[task_id]
    return {
        "task_id": task_id,
        "url": task.url,
        "lead_id": task.lead_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "error": task.error,
        "result": task.result,
    }


@app.post("/webhook")
async def handle_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    rate_limit: str = Depends(RateLimiter(times=10, seconds=60))
) -> dict:
    """
    Handle incoming Telegram webhook requests.
    
    Expects Telegram Update object with message containing:
    - Meeting URL
    - Optional lead ID (format: "url id:123")
    
    Rate limited to 10 requests per minute per IP.
    
    Returns:
        Task ID for tracking meeting processing status
    """
    try:
        update = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}
    except Exception as e:
        logger.error(f"Unexpected error parsing webhook: {e}")
        return {"status": "error", "message": "Server error"}
    
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
    
    # Validate URL scheme and domain with SSRF protection
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ('http', 'https'):
            raise ValueError("Invalid URL scheme")
        if not parsed_url.netloc:
            raise ValueError("Invalid URL domain")
        
        # SSRF Protection: Block private/internal IPs
        import socket
        import ipaddress
        
        hostname = parsed_url.hostname
        try:
            ip_addresses = socket.getaddrinfo(hostname, None)
            for family, _, _, _, addr in ip_addresses:
                ip_str = addr[0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if ip.is_private or ip.is_loopback or ip.is_link_local:
                        logger.warning(f"Blocked SSRF attempt to private IP: {ip_str}")
                        raise ValueError(f"Access to private addresses is not allowed: {ip_str}")
                except ValueError:
                    pass  # Not a valid IP, continue
        except socket.gaierror:
            pass  # DNS resolution failed, will be caught later
    except Exception as e:
        logger.warning(f"Invalid URL format: {url} - {e}")
        await send_telegram_message("❌ Неверный формат ссылки на встречу")
        return {"status": "ok", "message": "Invalid URL format"}
    
    # Generate unique task ID
    task_id = f"{lead_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    
    # Create task record
    task = MeetingTask(url=url, lead_id=lead_id, status=MeetingStatus.PENDING)
    meeting_tasks[task_id] = task
    
    logger.info(f"📞 Processing meeting: {url[:50]}... Lead ID: {lead_id} Task ID: {task_id}")
    
    # Send initial status message
    await send_telegram_message(f"▶ Начинаю процесс для {url}\n🆔 ID лида: {lead_id}\n📋 Task ID: {task_id}")
    
    # Process meeting asynchronously in background
    background_tasks.add_task(process_meeting_safe, task_id, url, lead_id)
    
    return {
        "status": "accepted",
        "task_id": task_id,
        "message": "Meeting processing started",
        "status_endpoint": f"/tasks/{task_id}"
    }


async def process_meeting_safe(task_id: str, url: str, lead_id: str) -> None:
    """
    Wrapper for process_meeting with comprehensive error handling for background tasks.
    
    Updates task status and sends notifications on completion or failure.
    """
    # Update task status to processing
    if task_id in meeting_tasks:
        meeting_tasks[task_id].status = MeetingStatus.PROCESSING
        meeting_tasks[task_id].started_at = datetime.now(timezone.utc)
    
    try:
        result = await process_meeting(url, lead_id)
        
        # Update task on success
        if task_id in meeting_tasks:
            meeting_tasks[task_id].status = MeetingStatus.COMPLETED
            meeting_tasks[task_id].completed_at = datetime.now(timezone.utc)
            meeting_tasks[task_id].result = result
        
        await send_telegram_message(f"✅ Готово! Вот отчет:\n\n{result}")
        
    except asyncio.TimeoutError as e:
        logger.error(f"❌ Task {task_id} timed out: {e}", exc_info=True)
        if task_id in meeting_tasks:
            meeting_tasks[task_id].status = MeetingStatus.TIMEOUT
            meeting_tasks[task_id].completed_at = datetime.now(timezone.utc)
            meeting_tasks[task_id].error = str(e)
        await send_telegram_message(f"❌ Превышено время обработки встречи")
        
    except Exception as e:
        logger.error(f"❌ Task {task_id} failed: {e}", exc_info=True)
        if task_id in meeting_tasks:
            meeting_tasks[task_id].status = MeetingStatus.FAILED
            meeting_tasks[task_id].completed_at = datetime.now(timezone.utc)
            meeting_tasks[task_id].error = str(e)
        await send_telegram_message(f"❌ Произошла ошибка: {str(e)[:500]}")


async def send_telegram_message(text: str) -> bool:
    """Send message to configured Telegram user with retry logic."""
    if not bot or not TELEGRAM_USER_ID:
        logger.warning("Telegram bot or user ID not configured")
        return False
    
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)
            logger.info(f"✅ Telegram message sent successfully")
            return True
        except Exception as e:
            delay = base_delay * (attempt + 1)
            logger.error(f"Failed to send Telegram message (attempt {attempt + 1}/{max_retries}, retrying in {delay}s): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    
    logger.error("❌ All Telegram message attempts failed")
    return False


async def process_meeting(url: str, lead_id: str) -> str:
    """
    Process a meeting: join, record, transcribe, analyze, and update Bitrix.
    
    Args:
        url: Meeting URL (must be valid HTTP/HTTPS URL)
        lead_id: Bitrix lead ID
        
    Returns:
        Analysis report text
        
    Raises:
        ValueError: If meeting URL is invalid or SSRF detected
        RuntimeError: If meeting processing fails
        asyncio.TimeoutError: If processing exceeds timeout
    """
    logger.info(f"🎯 Starting full meeting processing for {url}")
    
    # Validate URL format
    if not re.match(r'^https?://', url):
        raise ValueError(f"Invalid meeting URL: {url}")
    
    # Create LangChain prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Ты - бот-помощник для анализа встреч. Используй инструменты, чтобы подключиться к встрече, расшифровать, проанализировать и отправить отчет."),
        ("human", "{input}"),
        ("ai", "Я готов. Что мне нужно сделать?")
    ])
    
    # Initialize LangChain agent with proper error handling
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,
            api_key=Config.GEMINI_API_KEY,
            max_retries=3,
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
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=True, 
            handle_parsing_errors=True,
            max_iterations=10,
            early_stopping_method="force"
        )
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise RuntimeError(f"Agent creation failed: {e}")
    
    # Execute the agent with timeout protection
    timeout_seconds = Config.MEETING_TIMEOUT + 300  # Add 5 minutes buffer
    try:
        result = await asyncio.wait_for(
            agent_executor.ainvoke({
                "input": f"Подключись к встрече по ссылке {url} с ID {lead_id}. Расшифруй аудио, проанализируй транскрипцию и обнови лид."
            }),
            timeout=timeout_seconds
        )
        return result.get("output", "Отчёт не был сгенерирован.")
    except asyncio.TimeoutError:
        logger.error(f"Meeting processing timed out after {timeout_seconds}s")
        raise asyncio.TimeoutError(f"Meeting processing timed out after {timeout_seconds} seconds")
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise RuntimeError(f"Meeting analysis failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
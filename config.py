import os
import logging
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for the meeting bot."""
    
    # Required API tokens and IDs
    API_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_USER_ID: Optional[str] = os.getenv("TELEGRAM_USER_ID")
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    BITRIX_WEBHOOK: Optional[str] = os.getenv("BITRIX_WEBHOOK_URL")
    
    # Whisper and audio settings
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    AUDIO_DEVICE: str = os.getenv("AUDIO_DEVICE", "CABLE Output (VB-Audio Virtual Cable)")
    
    # Meeting settings
    MEETING_TIMEOUT: int = int(os.getenv("MEETING_TIMEOUT", "3600"))  # 1 hour default
    RECORDING_DURATION: int = int(os.getenv("RECORDING_DURATION", "3600"))
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent
    RECORDINGS_DIR: Path = BASE_DIR / "recordings"
    TRANSCRIPTS_DIR: Path = BASE_DIR / "transcripts"
    REPORTS_DIR: Path = BASE_DIR / "reports"
    
    # Prompt template for analysis
    PROMPT_TEMPLATE: dict = {
        "ru": """Ты - ассистент-аналитик для отдела продаж. 
        Твоя задача — внимательно изучить транскрипцию звонка, выделить ключевые моменты и оформить их в структурированный отчёт.
        
        Обязательно включи следующие разделы:
        - **Резюме:** Основная тема и ключевые итоги встречи.
        - **Следующие шаги:** Действия, которые необходимо предпринять (от кого и в какие сроки).
        - **Ключевые решения:** Договоренности, принятые на встрече.
        - **Вопросы:** Нерешенные вопросы или моменты, требующие дополнительного уточнения.
        - **Статус лида:** (Горячий / Тёплый / Холодный), обоснуй.
        """,
        "en": """You are an assistant analyst for the sales department.
        Your task is to carefully study the call transcript, highlight key points and format them into a structured report.
        
        Be sure to include the following sections:
        - **Summary:** Main topic and key outcomes of the meeting.
        - **Next Steps:** Actions to be taken (by whom and by when).
        - **Key Decisions:** Agreements made during the meeting.
        - **Questions:** Unresolved issues or points requiring clarification.
        - **Lead Status:** (Hot / Warm / Cold), justify your assessment.
        """
    }

    @classmethod
    def create_directories(cls) -> None:
        """Create necessary directories for recordings, transcripts, and reports."""
        for directory in [cls.RECORDINGS_DIR, cls.TRANSCRIPTS_DIR, cls.REPORTS_DIR]:
            directory.mkdir(exist_ok=True, parents=True)
            logger.info(f"Directory created/verified: {directory}")
    
    @classmethod
    def validate_config(cls) -> List[str]:
        """
        Validate all required configuration variables.
        
        Returns:
            List of missing required environment variable names.
        """
        errors = []
        required_vars = {
            "TELEGRAM_BOT_TOKEN": cls.API_TOKEN,
            "GEMINI_API_KEY": cls.GEMINI_API_KEY,
            "BITRIX_WEBHOOK_URL": cls.BITRIX_WEBHOOK,
            "TELEGRAM_USER_ID": cls.TELEGRAM_USER_ID
        }
        
        for var_name, var_value in required_vars.items():
            if not var_value:
                errors.append(var_name)
                logger.error(f"Missing required environment variable: {var_name}")
        
        return errors
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENVIRONMENT", "development") == "production"
    
    @classmethod
    def get_log_level(cls) -> int:
        """Get logging level from environment."""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        return getattr(logging, log_level, logging.INFO)
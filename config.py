import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK_URL")
    
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "CABLE Output (VB-Audio Virtual Cable)")
    
    BASE_DIR = Path(__file__).parent
    RECORDINGS_DIR = BASE_DIR / "recordings"
    TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
    REPORTS_DIR = BASE_DIR / "reports"
    
    PROMPT_TEMPLATE = {
        "ru": """Ты - ассистент-аналитик для отдела продаж. 
        Твоя задача — внимательно изучить транскрипцию звонка, выделить ключевые моменты и оформить их в структурированный отчёт.
        
        Обязательно включи следующие разделы:
        - **Резюме:** Основная тема и ключевые итоги встречи.
        - **Следующие шаги:** Действия, которые необходимо предпринять (от кого и в какие сроки).
        - **Ключевые решения:** Договоренности, принятые на встрече.
        - **Вопросы:** Нерешенные вопросы или моменты, требующие дополнительного уточнения.
        - **Статус лида:** (Горячий / Тёплый / Холодный), обоснуй.
        """,
    }

    @classmethod
    def create_directories(cls):
        for directory in [cls.RECORDINGS_DIR, cls.TRANSCRIPTS_DIR, cls.REPORTS_DIR]:
            directory.mkdir(exist_ok=True, parents=True)
    
    @classmethod
    def validate_config(cls):
        errors = []
        if not cls.API_TOKEN: errors.append("TELEGRAM_BOT_TOKEN")
        if not cls.GEMINI_API_KEY: errors.append("GEMINI_API_KEY")
        if not cls.BITRIX_WEBHOOK: errors.append("BITRIX_WEBHOOK_URL")
        if not cls.TELEGRAM_USER_ID: errors.append("TELEGRAM_USER_ID")
        return errors
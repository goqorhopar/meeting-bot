"""
Meeting Tools for AI-powered meeting analysis.

This module provides tools for:
- Joining and recording meetings via Puppeteer
- Transcribing audio using Whisper
- Analyzing transcripts with Gemini AI
- Updating leads in Bitrix24
"""

import subprocess
import logging
import time
from pathlib import Path
from typing import Optional, Union
from datetime import datetime
import threading
import asyncio
import json

import whisper
import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize models at module level
whisper_model: Optional[whisper.Whisper] = None


def get_gemini_model():
    """Lazy load Gemini model to avoid import errors."""
    try:
        from google import genai as google_genai
        return google_genai
    except ImportError:
        pass
    
    try:
        import google.generativeai as genai
        return genai
    except ImportError:
        raise ImportError(
            "Google Generative AI not available. "
            "Install with: pip install google-generativeai"
        )


class ToolResult(BaseModel):
    """Standardized result structure for tool operations."""
    success: bool
    message: str
    data: Optional[str] = None
    error: Optional[str] = None


def initialize_models():
    """Initialize Whisper and Gemini models with error handling."""
    global whisper_model
    
    if whisper_model is None:
        try:
            logger.info(f"Loading Whisper model: {Config.WHISPER_MODEL}")
            whisper_model = whisper.load_model(Config.WHISPER_MODEL)
            logger.info("✅ Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise


def get_gemini_client():
    """Get Gemini client instance with proper error handling."""
    genai = get_gemini_model()
    
    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")
    
    genai.configure(api_key=Config.GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


class MeetingTools:
    """Collection of tools for meeting processing."""

    @staticmethod
    @tool
    def join_and_record_meeting(url: str, lead_id: str) -> str:
        """
        Подключается к видеовстрече, записывает аудио и возвращает путь к файлу.
        
        Args:
            url: URL встречи (Google Meet, Zoom, etc.)
            lead_id: ID лида в Bitrix24
            
        Returns:
            Путь к записанному аудиофайлу или сообщение об ошибке
        """
        logger.info(f"▶ Начинаю встречу для лида {lead_id} на {url}")
        
        # Validate URL
        if not url or not url.startswith(('http://', 'https://')):
            logger.error(f"Invalid meeting URL: {url}")
            return f"❌ Неверный URL встречи: {url}"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_wav = Config.RECORDINGS_DIR / f"lead_{lead_id}_{timestamp}.wav"
        
        proc_browser = None
        proc_ffmpeg = None
        
        try:
            # Запускаем браузер через Node.js скрипт
            proc_browser = subprocess.Popen(
                ["node", "join-meeting.js", url, f"--name=Ассистент {lead_id}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Даем время на подключение
            logger.info("⏳ Ожидание подключения к встрече...")
            time.sleep(15)

            # Запускаем запись аудио через ffmpeg с проверкой доступности
            try:
                proc_ffmpeg = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-f", "dshow",
                        "-i", f"audio={Config.AUDIO_DEVICE}",
                        "-acodec", "pcm_s16le",
                        "-ac", "1",
                        "-ar", "16000",
                        str(filename_wav)
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                logger.info(f"🎤 Запись началась: {filename_wav}")
            except FileNotFoundError:
                logger.error("ffmpeg не найден. Убедитесь, что ffmpeg установлен.")
                if proc_browser:
                    proc_browser.kill()
                return "❌ ffmpeg не найден. Убедитесь, что ffmpeg установлен."
            
            # Ждем завершения работы браузера (конец встречи)
            stdout, stderr = proc_browser.communicate(timeout=Config.MEETING_TIMEOUT)
            logger.info(f"Встреча завершена. Вывод браузера: {stdout[:500] if stdout else 'пусто'}")
            
            # Останавливаем запись
            if proc_ffmpeg and proc_ffmpeg.poll() is None:
                proc_ffmpeg.terminate()
                try:
                    proc_ffmpeg.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc_ffmpeg.kill()
            
            # Проверяем что файл был создан
            if filename_wav.exists() and filename_wav.stat().st_size > 0:
                file_size_mb = filename_wav.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Аудио сохранено: {filename_wav} ({file_size_mb:.2f} MB)")
                return str(filename_wav)
            else:
                logger.error(f"❌ Файл не был создан или пуст: {filename_wav}")
                return f"❌ Не удалось записать аудио. Проверьте настройки аудиоустройства."
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Таймаут встречи ({Config.MEETING_TIMEOUT}s)")
            if proc_browser and proc_browser.poll() is None:
                proc_browser.kill()
            return f"❌ Таймаут встречи ({Config.MEETING_TIMEOUT}s)"
        except Exception as e:
            logger.error(f"❌ Ошибка записи встречи: {e}", exc_info=True)
            return f"❌ Ошибка: {str(e)[:200]}"
        finally:
            # Cleanup: ensure processes are terminated
            if proc_browser and proc_browser.poll() is None:
                try:
                    proc_browser.kill()
                except Exception:
                    pass
            if proc_ffmpeg and proc_ffmpeg.poll() is None:
                try:
                    proc_ffmpeg.kill()
                except Exception:
                    pass

    @staticmethod
    @tool
    def transcribe_audio(file_path: str) -> str:
        """
        Расшифровывает аудиофайл встречи в текст.
        
        Args:
            file_path: Путь к аудиофайлу
            
        Returns:
            Текстовая транскрипция или сообщение об ошибке
        """
        logger.info(f"▶ Расшифровываю аудиофайл: {file_path}")
        
        try:
            # Инициализируем модели если нужно
            initialize_models()
            
            if not file_path:
                logger.error("❌ Пустой путь к файлу")
                return "❌ Пустой путь к файлу"
            
            audio_path = Path(file_path)
            if not audio_path.exists():
                logger.error(f"❌ Файл не найден: {file_path}")
                return f"❌ Файл не найден: {file_path}"
            
            if audio_path.stat().st_size == 0:
                logger.error(f"❌ Файл пуст: {file_path}")
                return "❌ Файл пуст"
            
            # Загружаем аудио и транскрибируем с обработкой ошибок
            try:
                audio = whisper.load_audio(file_path)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки аудио: {e}")
                return f"❌ Ошибка загрузки аудио: {str(e)[:100]}"
            
            try:
                result = whisper_model.transcribe(audio, fp16=False, language="ru", verbose=False)
                transcript = result['text'].strip()
            except Exception as e:
                logger.error(f"❌ Ошибка транскрипции: {e}")
                return f"❌ Ошибка транскрипции: {str(e)[:100]}"
            
            if not transcript:
                logger.warning("⚠️ Пустая транскрипция")
                return "⚠️ Не удалось распознать речь (возможно, тишина в записи)"
            
            # Сохраняем транскрипцию
            transcript_path = Config.TRANSCRIPTS_DIR / (audio_path.stem + ".txt")
            try:
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(transcript)
                logger.info(f"✅ Транскрипция сохранена: {transcript_path}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось сохранить транскрипцию: {e}")
            
            return transcript
            
        except Exception as e:
            logger.error(f"❌ Ошибка расшифровки: {e}", exc_info=True)
            return f"❌ Не удалось получить транскрипцию: {str(e)[:100]}"

    @staticmethod
    @tool
    def analyze_transcript(transcript: str) -> str:
        """
        Анализирует транскрипцию с помощью Gemini.
        
        Args:
            transcript: Текст транскрипции встречи
            
        Returns:
            Структурированный анализ встречи или сообщение об ошибке
        """
        logger.info("▶ Анализирую транскрипцию с помощью Gemini")
        
        try:
            initialize_models()
            
            if not transcript or len(transcript.strip()) < 50:
                logger.warning("⚠️ Слишком короткая транскрипция для анализа")
                return "⚠️ Транскрипция слишком короткая для качественного анализа (< 50 символов)"
            
            # Проверка на максимально допустимый размер
            max_tokens = 100000  # Approximate limit for Gemini
            if len(transcript) > max_tokens * 4:  # Rough character estimate
                logger.warning(f"⚠️ Транскрипция слишком большая, обрезается до {max_tokens} токенов")
                transcript = transcript[:max_tokens * 4]
            
            prompt_template = Config.PROMPT_TEMPLATE.get('ru', Config.PROMPT_TEMPLATE['en'])
            full_prompt = f"{prompt_template}\n\nТранскрипция:\n{transcript}"
            
            # Get Gemini model and generate response
            gemini_model = get_gemini_client()
            
            try:
                response = gemini_model.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": 0.3,
                        "top_k": 40,
                        "top_p": 0.95,
                        "max_output_tokens": 2048,
                    }
                )
            except Exception as e:
                logger.error(f"❌ Ошибка запроса к Gemini: {e}")
                return f"❌ Ошибка AI анализа: {str(e)[:100]}"
            
            if response and response.text:
                logger.info("✅ Анализ завершен")
                return response.text
            else:
                logger.error("❌ Пустой ответ от Gemini")
                return "⚠️ Не удалось проанализировать транскрипцию (пустой ответ AI)"
                
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе Gemini: {e}", exc_info=True)
            return f"❌ Не удалось проанализировать транскрипцию: {str(e)[:100]}"

    @staticmethod
    @tool
    def update_bitrix_lead(lead_id: str, analysis: str) -> str:
        """
        Обновляет лид в Bitrix24.
        
        Args:
            lead_id: ID лида в Bitrix24
            analysis: Текст анализа для добавления в комментарии
            
        Returns:
            Статус операции
        """
        logger.info(f"▶ Обновляю лид {lead_id} в Bitrix24")
        
        try:
            if not Config.BITRIX_WEBHOOK:
                logger.error("❌ BITRIX_WEBHOOK_URL не настроен")
                return "❌ Вебхук Bitrix24 не настроен"
            
            # Проверяем что lead_id это число
            try:
                lead_id_int = int(lead_id)
            except ValueError:
                logger.error(f"❌ Неверный формат lead_id: {lead_id}")
                return f"❌ Неверный формат ID лида: {lead_id}"
            
            # Sanitize analysis to prevent injection
            sanitized_analysis = analysis.replace('\x00', '')  # Remove null bytes
            
            data = {
                "id": lead_id_int,
                "fields": {
                    "COMMENTS": f"{sanitized_analysis}\n\n---\nОбновлено автоматически Meeting Bot"
                }
            }
            
            webhook_url = f"{Config.BITRIX_WEBHOOK.rstrip('/')}/crm.lead.update.json"
            
            try:
                response = requests.post(
                    webhook_url, 
                    json=data, 
                    timeout=30,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                result = response.json()
            except requests.exceptions.Timeout:
                logger.error("❌ Таймаут запроса к Bitrix24")
                return "❌ Таймаут соединения с Bitrix24"
            except requests.exceptions.ConnectionError:
                logger.error("❌ Ошибка подключения к Bitrix24")
                return "❌ Ошибка подключения к Bitrix24"
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Ошибка сети Bitrix24: {e}")
                return f"❌ Ошибка сети: {str(e)[:100]}"
            
            if result.get('result'):
                logger.info(f"✅ Лид {lead_id} успешно обновлен.")
                return f"✅ Лид {lead_id} успешно обновлен."
            else:
                error_msg = result.get('error_description', str(result))
                logger.error(f"❌ Ошибка при обновлении лида: {error_msg}")
                return f"❌ Ошибка при обновлении лида: {error_msg[:200]}"
                
        except Exception as e:
            logger.error(f"❌ Ошибка Bitrix24: {e}", exc_info=True)
            return f"❌ Ошибка Bitrix24: {str(e)[:100]}"


# Инициализируем модели при импорте модуля
try:
    initialize_models()
except Exception as e:
    logger.warning(f"⚠️ Не удалось инициализировать модели при старте: {e}")

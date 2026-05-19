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
from typing import Optional
from datetime import datetime
import threading
import asyncio

import whisper
import google.generativeai as genai
import requests
from langchain.agents import tool

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize models at module level
whisper_model: Optional[whisper.Whisper] = None
gemini_model: Optional[genai.GenerativeModel] = None


def initialize_models():
    """Initialize Whisper and Gemini models."""
    global whisper_model, gemini_model
    
    if whisper_model is None:
        logger.info(f"Loading Whisper model: {Config.WHISPER_MODEL}")
        whisper_model = whisper.load_model(Config.WHISPER_MODEL)
    
    if gemini_model is None:
        logger.info("Initializing Gemini model")
        genai.configure(api_key=Config.GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")


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
            Путь к записанному аудиофайлу
        """
        logger.info(f"▶ Начинаю встречу для лида {lead_id} на {url}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_wav = Config.RECORDINGS_DIR / f"lead_{lead_id}_{timestamp}.wav"
        
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

            # Запускаем запись аудио через ffmpeg
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
            
            # Ждем завершения работы браузера (конец встречи)
            stdout, stderr = proc_browser.communicate(timeout=Config.MEETING_TIMEOUT)
            logger.info(f"Встреча завершена. Вывод браузера: {stdout[:500] if stdout else 'пусто'}")
            
            # Останавливаем запись
            proc_ffmpeg.terminate()
            proc_ffmpeg.wait(timeout=5)
            
            # Проверяем что файл был создан
            if filename_wav.exists() and filename_wav.stat().st_size > 0:
                file_size_mb = filename_wav.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Аудио сохранено: {filename_wav} ({file_size_mb:.2f} MB)")
                return str(filename_wav)
            else:
                logger.error(f"❌ Файл не был создан или пуст: {filename_wav}")
                return ""
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Таймаут встречи ({Config.MEETING_TIMEOUT}s)")
            proc_browser.kill()
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка записи встречи: {e}", exc_info=True)
            return ""
        finally:
            # Cleanup: ensure processes are terminated
            try:
                if proc_browser.poll() is None:
                    proc_browser.kill()
            except Exception:
                pass
            try:
                if 'proc_ffmpeg' in locals() and proc_ffmpeg.poll() is None:
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
            Текстовая транскрипция
        """
        logger.info(f"▶ Расшифровываю аудиофайл: {file_path}")
        
        try:
            # Инициализируем модели если нужно
            initialize_models()
            
            if not Path(file_path).exists():
                logger.error(f"❌ Файл не найден: {file_path}")
                return "Файл не найден"
            
            # Загружаем аудио и транскрибируем
            audio = whisper.load_audio(file_path)
            result = whisper_model.transcribe(audio, fp16=False, language="ru")
            transcript = result['text'].strip()
            
            if not transcript:
                logger.warning("⚠️ Пустая транскрипция")
                return "Не удалось распознать речь"
            
            # Сохраняем транскрипцию
            transcript_path = Config.TRANSCRIPTS_DIR / (Path(file_path).stem + ".txt")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            
            logger.info(f"✅ Транскрипция сохранена: {transcript_path}")
            return transcript
            
        except Exception as e:
            logger.error(f"❌ Ошибка расшифровки: {e}", exc_info=True)
            return "Не удалось получить транскрипцию"

    @staticmethod
    @tool
    def analyze_transcript(transcript: str) -> str:
        """
        Анализирует транскрипцию с помощью Gemini.
        
        Args:
            transcript: Текст транскрипции встречи
            
        Returns:
            Структурированный анализ встречи
        """
        logger.info("▶ Анализирую транскрипцию с помощью Gemini")
        
        try:
            initialize_models()
            
            if not transcript or len(transcript.strip()) < 50:
                logger.warning("⚠️ Слишком короткая транскрипция для анализа")
                return "Транскрипция слишком короткая для качественного анализа"
            
            prompt = Config.PROMPT_TEMPLATE.get('ru', Config.PROMPT_TEMPLATE['en'])
            full_prompt = f"{prompt}\n\nТранскрипция:\n{transcript}"
            
            response = gemini_model.generate_content(full_prompt)
            
            if response and response.text:
                logger.info("✅ Анализ завершен")
                return response.text
            else:
                logger.error("❌ Пустой ответ от Gemini")
                return "Не удалось проанализировать транскрипцию"
                
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе Gemini: {e}", exc_info=True)
            return "Не удалось проанализировать транскрипцию"

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
            
            data = {
                "id": lead_id_int,
                "fields": {
                    "COMMENTS": f"{analysis}\n\n---\nОбновлено автоматически Meeting Bot"
                }
            }
            
            webhook_url = f"{Config.BITRIX_WEBHOOK.rstrip('/')}/crm.lead.update.json"
            response = requests.post(
                webhook_url, 
                json=data, 
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('result'):
                logger.info(f"✅ Лид {lead_id} успешно обновлен.")
                return f"✅ Лид {lead_id} успешно обновлен."
            else:
                error_msg = result.get('error_description', str(result))
                logger.error(f"❌ Ошибка при обновлении лида: {error_msg}")
                return f"❌ Ошибка при обновлении лида: {error_msg}"
                
        except requests.exceptions.Timeout:
            logger.error("❌ Таймаут запроса к Bitrix24")
            return "❌ Таймаут соединения с Bitrix24"
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети Bitrix24: {e}")
            return f"❌ Ошибка сети: {e}"
        except Exception as e:
            logger.error(f"❌ Ошибка Bitrix24: {e}", exc_info=True)
            return f"❌ Ошибка Bitrix24: {e}"


# Инициализируем модели при импорте модуля
try:
    initialize_models()
except Exception as e:
    logger.warning(f"⚠️ Не удалось инициализировать модели при старте: {e}")

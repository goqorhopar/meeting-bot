import subprocess
import logging
from pathlib import Path
import whisper
import google.generativeai as genai
import requests
import time
from datetime import datetime
from langchain.agents import tool
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

whisper_model = whisper.load_model(Config.WHISPER_MODEL)
genai.configure(api_key=Config.GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

class MeetingTools:

    @staticmethod
    @tool
    def join_and_record_meeting(url: str, lead_id: str) -> str:
        """
        Подключается к видеовстрече, записывает аудио и возвращает путь к файлу.
        """
        logger.info(f"▶ Начинаю встречу для лида {lead_id} на {url}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_wav = Config.RECORDINGS_DIR / f"lead_{lead_id}_{timestamp}.wav"
        
        proc_browser = subprocess.Popen(
            ["node", "joinMeeting.js", url, f"--name=Ассистент {lead_id}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        time.sleep(15)

        proc_ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-f", "dshow",
                "-i", f"audio={Config.AUDIO_DEVICE}",
                "-acodec", "pcm_s16le",
                "-ac", "1",
                str(filename_wav)
            ]
        )
        
        proc_browser.wait()
        proc_ffmpeg.terminate()
        
        return str(filename_wav)

    @staticmethod
    @tool
    def transcribe_audio(file_path: str) -> str:
        """
        Расшифровывает аудиофайл встречи в текст.
        """
        logger.info(f"▶ Расшифровываю аудиофайл: {file_path}")
        try:
            audio = whisper.load_audio(file_path)
            result = whisper_model.transcribe(audio, fp16=False)
            transcript = result['text']
            
            transcript_path = Config.TRANSCRIPTS_DIR / (Path(file_path).stem + ".txt")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            
            return transcript
        except Exception as e:
            logger.error(f"❌ Ошибка расшифровки: {e}")
            return "Не удалось получить транскрипцию"

    @staticmethod
    @tool
    def analyze_transcript(transcript: str) -> str:
        """
        Анализирует транскрипцию с помощью Gemini.
        """
        logger.info("▶ Анализирую транскрипцию с помощью Gemini")
        try:
            response = gemini_model.generate_content(
                Config.PROMPT_TEMPLATE['ru'] + f"\n\nТранскрипция:\n{transcript}"
            )
            return response.text
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе Gemini: {e}")
            return "Не удалось проанализировать транскрипцию"

    @staticmethod
    @tool
    def update_bitrix_lead(lead_id: str, analysis: str) -> str:
        """
        Обновляет лид в Bitrix24.
        """
        logger.info(f"▶ Обновляю лид {lead_id} в Bitrix24")
        try:
            data = {
                "id": lead_id,
                "fields": {
                    "COMMENTS": analysis
                }
            }
            response = requests.post(f"{Config.BITRIX_WEBHOOK}crm.lead.update.json", json=data)
            response.raise_for_status()
            result = response.json()
            if result.get('result'):
                logger.info(f"✅ Лид {lead_id} успешно обновлен.")
                return f"✅ Лид {lead_id} успешно обновлен."
            else:
                logger.error(f"❌ Ошибка при обновлении лида: {result.get('error_description', result)}")
                return f"❌ Ошибка при обновлении лида: {result.get('error_description')}"
        except Exception as e:
            logger.error(f"❌ Ошибка Bitrix24: {e}")
            return f"❌ Ошибка Bitrix24: {e}"
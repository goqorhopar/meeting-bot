import logging
import re
from fastapi import FastAPI, Request
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_community.chat_models import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from tools import MeetingTools
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
Config.create_directories()
errors = Config.validate_config()
if errors:
    for error in errors:
        logger.error(f"Configuration error: {error}")
    exit(1)

bot = Bot(token=Config.API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
TELEGRAM_USER_ID = int(Config.TELEGRAM_USER_ID)

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты - бот-помощник для анализа встреч. Используй инструменты, чтобы подключиться к встрече, расшифровать, проанализировать и отправить отчет."),
    ("human", "{input}"),
    ("ai", "Я готов. Что мне нужно сделать?")
])
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0, api_key=Config.GEMINI_API_KEY)
tools = [
    MeetingTools.join_and_record_meeting,
    MeetingTools.transcribe_audio,
    MeetingTools.analyze_transcript,
    MeetingTools.update_bitrix_lead
]
agent = create_structured_chat_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

@app.post("/webhook")
async def handle_webhook(request: Request):
    update = await request.json()
    
    if update.get("message") and update["message"]["from"]["id"] == TELEGRAM_USER_ID:
        text = update["message"]["text"].strip()
        
        match = re.search(r'(https?://\S+)(?:\s+id:(\d+))?', text)
        
        if match:
            url = match.group(1)
            lead_id = match.group(2) if match.group(2) else "без_ID"
            
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"▶ Начинаю процесс для {url}. ID лида: {lead_id}")
            
            try:
                result = await agent_executor.ainvoke({"input": f"Подключись к встрече по ссылке {url} с ID {lead_id}. Расшифруй аудио, проанализируй транскрипцию и обнови лид."})
                
                final_report = result.get("output", "Отчёт не был сгенерирован.")
                
                await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"✅ Готово! Вот отчет:\n\n{final_report}")
                
            except Exception as e:
                logger.error(f"❌ Произошла ошибка в агенте: {e}")
                await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"❌ Произошла ошибка: {e}")

    return {"status": "ok"}
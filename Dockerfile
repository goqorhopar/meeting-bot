# Базовый образ Python
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Устанавливаем Node.js LTS и системные зависимости
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y \
    nodejs \
    libnss3-dev \
    libasound2 \
    libatk1.0-0 \
    libgtk-3-0 \
    libcups2 \
    libxtst6 \
    libxss1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libdbus-glib-1-2 \
    ffmpeg \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Node.js зависимости (если есть)
COPY package*.json ./
RUN if [ -f package.json ]; then npm install; fi

# Устанавливаем Python зависимости
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запуск бота
CMD ["python", "bot.py"]


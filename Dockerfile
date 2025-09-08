# Используем официальный образ Python
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
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
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Копируем package.json если есть
COPY package*.json ./
RUN npm install

# Копируем requirements.txt и устанавливаем Python пакеты
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]
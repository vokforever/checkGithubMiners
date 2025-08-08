# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем зависимости и сразу очищаем кэш
RUN pip install --no-cache-dir aiohttp==3.9.1 aiogram==3.6.0 apscheduler==3.10.4 beautifulsoup4==4.12.2 python-dotenv==1.0.0

# Копируем только main.py, а не все файлы
COPY main.py .

# Создаем директорию для данных
RUN mkdir -p data

# Эти переменные окружения здесь указаны с "dummy" значениями.
# Реальные значения должны быть настроены в Coolify в разделе "Variables" вашего сервиса.
ENV BOT_TOKEN="dummy" \
    GITHUB_TOKEN="dummy" \
    CHANNEL_ID="dummy" \
    ADMIN_ID="dummy" \
    CHECK_INTERVAL_MINUTES="60"

# Команда для запуска приложения при старте контейнера
CMD ["python", "main.py"]

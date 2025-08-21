# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем основные файлы
COPY main.py .
COPY supabase_config.py .

# Создаем директории для данных и логов
RUN mkdir -p data logs backups

# Эти переменные окружения здесь указаны с "dummy" значениями.
# Реальные значения должны быть настроены в CapRover/Coolify в разделе "Variables" вашего сервиса.
ENV BOT_TOKEN="dummy" \
    GITHUB_TOKEN="dummy" \
    CHANNEL_ID="dummy" \
    ADMIN_ID="dummy" \
    SUPABASE_URL="dummy" \
    SUPABASE_SERVICE_ROLE_KEY="dummy" \
    CHECK_INTERVAL_MINUTES="60"

# Команда для запуска приложения при старте контейнера
CMD ["python", "main.py"]

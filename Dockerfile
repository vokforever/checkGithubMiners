FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости напрямую (без requirements.txt)
RUN pip install --no-cache-dir aiohttp==3.9.1 aiogram==3.6.0 apscheduler==3.10.4 beautifulsoup4==4.12.2 python-dotenv==1.0.0

# Копируем только main.py
COPY main.py .

# Создаем директорию для данных
RUN mkdir -p data

# Команда запуска
CMD ["python", "main.py"]

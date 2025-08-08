# Используем официальный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем ТОЛЬКО необходимые системные зависимости без обновления
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаем директорию для данных бота
RUN mkdir -p data && chmod 755 data

# Устанавливаем права на выполнение
RUN chmod +x bot.py

# Открываем порт для health check
EXPOSE 8080

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Команда для запуска бота
CMD ["python", "main.py"]

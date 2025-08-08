# Этап 1: Сборка зависимостей
FROM python:3.11-slim as builder

WORKDIR /app

# Устанавливаем только необходимые зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Этап 2: Финальный образ
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем только runtime зависимости
RUN apt-get update && apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Копируем установленные зависимости из builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Копируем приложение
COPY . .

# Создаем директорию для данных
RUN mkdir -p data && chmod 755 data

# Устанавливаем права для main.py
RUN chmod +x main.py

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Команда запуска
CMD ["python", "main.py"]

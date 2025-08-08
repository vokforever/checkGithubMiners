FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости без лишних пакетов
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Копируем приложение
COPY . .

# Устанавливаем права
RUN chmod +x main.py && mkdir -p data && chmod 755 data

# Настраиваем окружение
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Команда запуска
CMD ["python", "main.py"]

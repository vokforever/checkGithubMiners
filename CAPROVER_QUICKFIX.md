# 🚀 CapRover Quick Fix

## ⚡ Быстрое исправление

### 1. Установить psutil
```bash
# В CapRover контейнере
pip install psutil==5.9.8
```

### 2. Проверить Supabase ключи
Убедитесь, что используете **service_role** key, а не **anon** key.

### 3. Перезапустить приложение
В CapRover Dashboard → Apps → Restart

### 4. Проверить логи
```bash
caprover logs --app-name your-app-name
```

## 🔑 Ключевые моменты

- **psutil** нужен для команды `/debug`
- **service_role** key для записи в Supabase
- Все зависимости в `requirements.txt`
- Dockerfile обновлен для CapRover

## 📋 Команды для проверки

После исправления используйте:
- `/debug` - статус системы и Supabase
- `/sync` - синхронизация с БД
- `/priority` - приоритеты репозиториев

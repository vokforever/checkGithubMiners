# Supabase Integration для checkGithubMiners

Полная интеграция с Supabase для замены JSON файлов.

## 📁 Файлы

- **`supabase_config.py`** - Основной файл интеграции с Supabase
- **`migrate_to_supabase.py`** - Скрипт миграции данных из JSON в Supabase
- **SQL скрипты** - Для создания таблиц в Supabase

## 🚀 Быстрый старт

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения
Создайте файл `.env`:
```env
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

### 3. Миграция данных
```bash
python migrate_to_supabase.py
```

## 🔧 Использование

### Основные функции

```python
from supabase_config import SupabaseManager

# Инициализация
supabase = SupabaseManager()

# Получение отчета в формате Telegram
report = await supabase.get_telegram_report()

# Обновление данных репозитория
await supabase.update_repository_priority(
    'andru-kun/wildrig-multi',
    priority_score=0.5,
    update_count=5
)

# Логирование проверки
await supabase.log_repository_check(
    'andru-kun/wildrig-multi',
    'success',
    response_time_ms=150
)
```

### Удобные функции

```python
from supabase_config import get_telegram_report, update_repository_data, log_check

# Получение отчета
report = await get_telegram_report()

# Обновление данных
await update_repository_data('repo-name', priority_score=0.3)

# Логирование
await log_check('repo-name', 'success', response_time_ms=200)
```

## 📊 Структура данных

### Основная таблица: `checkgithub_repository_priorities`
- `repo_name` - Полное имя репозитория
- `display_name` - Отображаемое имя
- `priority_score` - Оценка приоритета (0.0-1.0)
- `priority_level` - Уровень (high/medium/low)
- `priority_color` - Эмодзи цвета
- `check_interval` - Интервал проверки в минутах
- `update_count` - Количество обновлений
- `total_checks` - Общее количество проверок

## 🔄 Миграция

Скрипт `migrate_to_supabase.py` автоматически:
1. Создает таблицы в Supabase
2. Переносит данные из `repo_priority.json`
3. Создает backup исходного файла
4. Генерирует отчет из Supabase

## 📈 Преимущества

- **Централизованное хранение** - все данные в Supabase
- **Автоматическое резервирование** - backup при миграции
- **Готовые функции** - для работы с приоритетами
- **Логирование** - всех проверок репозиториев
- **Масштабируемость** - легко добавлять новые функции

## 🚨 Важно

После успешной миграции:
- JSON файл будет переименован в backup
- Все новые данные будут сохраняться в Supabase
- Для восстановления используйте backup файл

## 🔍 Мониторинг

```python
# Получение статистики
summary = await supabase.get_priority_summary()

# Проверка проблем с подключением
issues = await supabase._get_connection_issues()

# Экспорт в JSON (если нужно)
json_data = await supabase.export_to_json()
```

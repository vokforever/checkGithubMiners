# SQL Setup для checkGithubMiners

Этот документ описывает SQL скрипты для создания и настройки базы данных checkGithubMiners с префиксом `checkgithub_`.

## 📁 Файлы SQL

### 1. `create_checkgithub_tables.sql` - Основные таблицы
Создает основную таблицу `checkgithub_repository_priorities` с данными о приоритетах репозиториев.

### 2. `create_checkgithub_additional_tables.sql` - Дополнительные таблицы
Создает таблицы для логирования, статистики и мониторинга.

### 3. `create_checkgithub_views_and_queries.sql` - Представления и запросы
Создает представления для анализа данных и функции для генерации отчетов.

## 🚀 Быстрый старт

### Шаг 1: Создание основных таблиц
```sql
\i create_checkgithub_tables.sql
```

### Шаг 2: Создание дополнительных таблиц
```sql
\i create_checkgithub_additional_tables.sql
```

### Шаг 3: Создание представлений и функций
```sql
\i create_checkgithub_views_and_queries.sql
```

## 🗄️ Структура базы данных

### Основная таблица: `checkgithub_repository_priorities`
```sql
- id: Уникальный идентификатор
- repo_name: Полное имя репозитория (owner/repo)
- display_name: Отображаемое имя
- update_count: Количество обновлений
- check_interval: Интервал проверки в минутах
- priority_score: Оценка приоритета (0.0 - 1.0)
- priority_level: Уровень приоритета (high/medium/low)
- priority_color: Эмодзи для отображения
- last_check: Время последней проверки
- total_checks: Общее количество проверок
```

### Дополнительные таблицы:
- `checkgithub_check_logs` - Логи проверок
- `checkgithub_performance_stats` - Статистика производительности
- `checkgithub_monitoring_config` - Конфигурация мониторинга
- `checkgithub_priority_history` - История изменений приоритетов

## 📊 Основные представления

### 1. `checkgithub_telegram_format`
Форматирует данные для отображения в Telegram:
```sql
SELECT * FROM checkgithub_telegram_format;
```

### 2. `checkgithub_performance_monitoring`
Мониторинг производительности системы:
```sql
SELECT * FROM checkgithub_performance_monitoring;
```

### 3. `checkgithub_connection_issues`
Проблемы с подключением:
```sql
SELECT * FROM checkgithub_connection_issues;
```

### 4. `checkgithub_system_health`
Общее состояние системы:
```sql
SELECT * FROM checkgithub_system_health;
```

## 🔧 Основные функции

### 1. Генерация отчета в формате Telegram
```sql
SELECT * FROM checkgithub_generate_telegram_report();
```

### 2. Обновление приоритета репозитория
```sql
SELECT checkgithub_update_repository_priority(
    'andru-kun/wildrig-multi',
    5,    -- update_count
    300,  -- check_interval
    0.6,  -- priority_score
    15    -- total_checks
);
```

### 3. Логирование проверки
```sql
SELECT checkgithub_log_repository_check(
    'andru-kun/wildrig-multi',
    'success',
    150,  -- response_time_ms
    NULL, -- error_message
    FALSE, -- update_detected
    NULL,  -- new_release_tag
    NULL   -- new_release_url
);
```

### 4. Получение статистики по репозиторию
```sql
SELECT * FROM checkgithub_get_repository_stats('andru-kun/wildrig-multi', 30);
```

### 5. Получение системной статистики
```sql
SELECT * FROM checkgithub_get_system_stats();
```

## 📈 Примеры запросов

### Получение топ репозиториев по активности
```sql
SELECT 
    display_name,
    priority_score,
    update_count,
    total_checks,
    ROUND((update_count::NUMERIC / NULLIF(total_checks, 0)) * 100, 2) as activity_score
FROM checkgithub_repository_priorities
WHERE total_checks > 0
ORDER BY activity_score DESC
LIMIT 5;
```

### Мониторинг проблемных репозиториев
```sql
SELECT 
    display_name,
    consecutive_failures,
    priority_color,
    CASE 
        WHEN consecutive_failures >= 3 THEN '🔴 Critical'
        WHEN consecutive_failures >= 2 THEN '🟠 Warning'
        WHEN consecutive_failures >= 1 THEN '🟡 Attention'
        ELSE '🟢 Healthy'
    END as status
FROM checkgithub_repository_priorities
WHERE consecutive_failures > 0
ORDER BY consecutive_failures DESC;
```

### Статистика по уровням приоритета
```sql
SELECT 
    priority_level,
    priority_color,
    COUNT(*) as repository_count,
    ROUND(AVG(priority_score), 3) as avg_priority_score,
    SUM(update_count) as total_updates
FROM checkgithub_repository_priorities
GROUP BY priority_level, priority_color
ORDER BY 
    CASE priority_level 
        WHEN 'high' THEN 1 
        WHEN 'medium' THEN 2 
        WHEN 'low' THEN 3 
    END;
```

## 🔍 Мониторинг и алерты

### Проверка здоровья системы
```sql
-- Общее состояние
SELECT * FROM checkgithub_system_health;

-- Покрытие репозиториев
SELECT 
    COUNT(*) as total_repos,
    COUNT(CASE WHEN last_check >= NOW() - INTERVAL '24 hours' THEN 1 END) as active_repos,
    COUNT(CASE WHEN last_check < NOW() - INTERVAL '24 hours' THEN 1 END) as stale_repos
FROM checkgithub_repository_priorities;
```

### Мониторинг ошибок
```sql
-- Ошибки за последние 24 часа
SELECT 
    repo_name,
    COUNT(*) as error_count,
    MAX(check_timestamp) as last_error
FROM checkgithub_check_logs
WHERE check_result = 'failure'
AND check_timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY repo_name
ORDER BY error_count DESC;
```

## 🛠️ Обслуживание базы данных

### Очистка старых логов
```sql
-- Удаление логов старше 90 дней
DELETE FROM checkgithub_check_logs 
WHERE check_timestamp < NOW() - INTERVAL '90 days';

-- Удаление статистики старше 30 дней
DELETE FROM checkgithub_performance_stats 
WHERE date < CURRENT_DATE - INTERVAL '30 days';
```

### Обновление статистики
```sql
-- Обновление среднего времени ответа
UPDATE checkgithub_repository_priorities 
SET average_response_time = (
    SELECT ROUND(AVG(response_time_ms), 2)
    FROM checkgithub_check_logs
    WHERE repo_name = checkgithub_repository_priorities.repo_name
    AND check_timestamp >= NOW() - INTERVAL '7 days'
)
WHERE EXISTS (
    SELECT 1 FROM checkgithub_check_logs 
    WHERE repo_name = checkgithub_repository_priorities.repo_name
);
```

## 📋 Конфигурация мониторинга

### Изменение настроек
```sql
-- Изменение порога высокого приоритета
UPDATE checkgithub_monitoring_config 
SET config_value = '0.6', updated_at = NOW()
WHERE config_key = 'high_priority_threshold';

-- Включение email уведомлений
UPDATE checkgithub_monitoring_config 
SET config_value = 'true', updated_at = NOW()
WHERE config_key = 'enable_email_notifications';
```

### Просмотр текущих настроек
```sql
SELECT config_key, config_value, description, is_active
FROM checkgithub_monitoring_config
WHERE is_active = true
ORDER BY config_key;
```

## 🔐 Безопасность

### Создание пользователя только для чтения
```sql
-- Создание пользователя для мониторинга
CREATE USER checkgithub_monitor WITH PASSWORD 'secure_password';

-- Предоставление прав только на чтение
GRANT SELECT ON ALL TABLES IN SCHEMA public TO checkgithub_monitor;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO checkgithub_monitor;
```

### Ограничение доступа к конфигурации
```sql
-- Создание представления только для чтения конфигурации
CREATE VIEW checkgithub_config_readonly AS
SELECT config_key, config_value, description
FROM checkgithub_monitoring_config
WHERE is_active = true;

-- Предоставление доступа к представлению
GRANT SELECT ON checkgithub_config_readonly TO checkgithub_monitor;
```

## 📊 Экспорт данных

### Экспорт в CSV
```sql
-- Экспорт приоритетов репозиториев
COPY (
    SELECT 
        repo_name, display_name, priority_level, priority_score,
        check_interval, update_count, total_checks, last_check
    FROM checkgithub_repository_priorities
    ORDER BY priority_score DESC
) TO '/tmp/repository_priorities.csv' WITH CSV HEADER;

-- Экспорт статистики производительности
COPY (
    SELECT * FROM checkgithub_performance_monitoring
) TO '/tmp/performance_monitoring.csv' WITH CSV HEADER;
```

### Экспорт отчета в JSON
```sql
-- Создание функции для экспорта в JSON
CREATE OR REPLACE FUNCTION checkgithub_export_to_json()
RETURNS JSON AS $$
BEGIN
    RETURN (
        SELECT json_build_object(
            'timestamp', NOW(),
            'total_repositories', COUNT(*),
            'repositories', json_agg(
                json_build_object(
                    'name', display_name,
                    'priority', priority_level,
                    'score', priority_score,
                    'updates', update_count,
                    'checks', total_checks
                )
            )
        )
        FROM checkgithub_repository_priorities
    );
END;
$$ LANGUAGE plpgsql;

-- Использование
SELECT checkgithub_export_to_json();
```

## 🚨 Устранение неполадок

### Проверка целостности данных
```sql
-- Проверка на дубликаты
SELECT repo_name, COUNT(*) 
FROM checkgithub_repository_priorities 
GROUP BY repo_name 
HAVING COUNT(*) > 1;

-- Проверка на NULL значения в обязательных полях
SELECT * FROM checkgithub_repository_priorities 
WHERE repo_name IS NULL OR display_name IS NULL;
```

### Восстановление после сбоя
```sql
-- Сброс счетчиков неудач
UPDATE checkgithub_repository_priorities 
SET consecutive_failures = 0 
WHERE consecutive_failures > 0;

-- Обновление времени последней проверки
UPDATE checkgithub_repository_priorities 
SET last_check = NOW() 
WHERE last_check IS NULL;
```

## 📚 Дополнительные ресурсы

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Supabase Documentation](https://supabase.com/docs)
- [SQL Tutorial](https://www.w3schools.com/sql/)

## 🤝 Поддержка

При возникновении проблем или вопросов:
1. Проверьте логи PostgreSQL
2. Убедитесь в корректности SQL синтаксиса
3. Проверьте права доступа пользователя
4. Обратитесь к документации PostgreSQL

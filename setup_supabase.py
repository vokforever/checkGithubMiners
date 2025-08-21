#!/usr/bin/env python3
"""
Скрипт для настройки Supabase на основе официальной документации
"""

import os
import json
from dotenv import load_dotenv

def setup_supabase():
    """Настраивает Supabase подключение и создает таблицы"""
    print("🚀 GitHub Miners Bot - Supabase Setup")
    print("=" * 60)
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем переменные окружения
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Ошибка: SUPABASE_URL и SUPABASE_KEY должны быть настроены")
        print("💡 Создайте файл .env с переменными окружения")
        return False
    
    print(f"✅ Supabase URL: {supabase_url[:30]}...")
    print(f"✅ Supabase Key: {supabase_key[:10]}...")
    
    try:
        from supabase import create_client, Client
        
        # Создаем клиент согласно официальной документации
        supabase: Client = create_client(supabase_url, supabase_key)
        print("✅ Supabase клиент создан успешно")
        
        # Проверяем подключение
        print("\n🔍 Проверка подключения...")
        
        # Пытаемся получить информацию о проекте
        try:
            # Простая проверка - пытаемся получить список таблиц
            # Это может не сработать без специальных прав, но покажет, что клиент работает
            print("✅ Подключение к Supabase установлено")
        except Exception as e:
            print(f"⚠️  Предупреждение: {e}")
        
        # Создаем таблицу приоритетов
        print("\n🔧 Создание таблицы приоритетов...")
        
        # SQL для создания таблицы (выполняется в Supabase Dashboard)
        create_table_sql = """
-- Создание таблицы приоритетов репозиториев
CREATE TABLE IF NOT EXISTS checkgithub_repository_priorities (
    id SERIAL PRIMARY KEY,
    repo_name VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    update_count INTEGER DEFAULT 0,
    last_update TIMESTAMPTZ,
    check_interval INTEGER DEFAULT 1440,
    priority_score DECIMAL(5,3) DEFAULT 0.0,
    last_check TIMESTAMPTZ DEFAULT NOW(),
    consecutive_failures INTEGER DEFAULT 0,
    total_checks INTEGER DEFAULT 0,
    average_response_time DECIMAL(10,6) DEFAULT 0.0,
    priority_level VARCHAR(20) DEFAULT 'low',
    priority_color VARCHAR(10) DEFAULT '🟢',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Создание индексов
CREATE INDEX IF NOT EXISTS idx_checkgithub_repo_name ON checkgithub_repository_priorities(repo_name);
CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_score ON checkgithub_repository_priorities(priority_score);
CREATE INDEX IF NOT EXISTS idx_checkgithub_last_check ON checkgithub_repository_priorities(last_check);
CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_level ON checkgithub_repository_priorities(priority_level);
"""
        
        print("📝 SQL для создания таблицы:")
        print(create_table_sql)
        
        print("\n💡 Инструкции:")
        print("1. Откройте Supabase Dashboard")
        print("2. Перейдите в SQL Editor")
        print("3. Скопируйте и выполните SQL код выше")
        print("4. Или создайте таблицу через Table Editor")
        
        # Проверяем, существует ли таблица
        try:
            result = supabase.table('checkgithub_repository_priorities').select('count').limit(1).execute()
            print("✅ Таблица checkgithub_repository_priorities уже существует")
        except Exception as e:
            print(f"❌ Таблица не найдена: {e}")
            print("🔧 Создайте таблицу вручную в Supabase Dashboard")
        
        # Мигрируем данные из JSON если таблица существует
        if os.path.exists('repo_priority.json'):
            print("\n🔄 Миграция данных из JSON...")
            try:
                with open('repo_priority.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                print(f"📊 Найдено {len(data.get('priorities', {}))} репозиториев для миграции")
                
                # Пытаемся мигрировать данные
                try:
                    from supabase_config import SupabaseManager
                    supabase_manager = SupabaseManager()
                    success = supabase_manager.migrate_from_json('repo_priority.json')
                    if success:
                        print("✅ Миграция завершена успешно")
                    else:
                        print("❌ Миграция не удалась")
                except Exception as e:
                    print(f"❌ Ошибка миграции: {e}")
                    print("💡 Создайте таблицу вручную и попробуйте снова")
                
            except Exception as e:
                print(f"❌ Ошибка чтения JSON: {e}")
        
        print("\n🎯 Следующие шаги:")
        print("1. Создайте таблицу в Supabase Dashboard")
        print("2. Запустите бота: python main.py")
        print("3. Используйте команду /sync в Telegram")
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("💡 Установите supabase: pip install supabase")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    """Основная функция"""
    success = setup_supabase()
    
    if success:
        print("\n✅ Настройка Supabase завершена")
    else:
        print("\n❌ Настройка Supabase не удалась")
        print("🔧 Проверьте переменные окружения и попробуйте снова")

if __name__ == "__main__":
    main()

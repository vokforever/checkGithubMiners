#!/usr/bin/env python3
"""
Скрипт для создания таблиц в Supabase
"""

import os
from dotenv import load_dotenv

def create_tables():
    """Создает таблицы в Supabase"""
    print("🔧 Создание таблиц в Supabase...")
    
    # Загружаем переменные окружения
    load_dotenv()
    
    try:
        from supabase_config import SupabaseManager
        supabase = SupabaseManager()
        print("✅ SupabaseManager создан успешно")
        
        # SQL для создания таблицы
        create_table_sql = """
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
        """
        
        # Создаем таблицу через SQL
        try:
            # Пытаемся выполнить SQL напрямую
            result = supabase.client.rpc('exec_sql', {'sql': create_table_sql}).execute()
            print("✅ Таблица создана через RPC")
        except Exception as e:
            print(f"⚠️  Не удалось создать через RPC: {e}")
            
            # Альтернативный способ - через insert с проверкой
            try:
                # Проверяем, существует ли таблица
                test_result = supabase.client.table('checkgithub_repository_priorities').select('count').limit(1).execute()
                print("✅ Таблица уже существует")
            except Exception as table_error:
                print(f"❌ Таблица не существует: {table_error}")
                print("💡 Создайте таблицу вручную в Supabase Dashboard")
                return False
        
        # Создаем индексы
        try:
            index_sql = """
            CREATE INDEX IF NOT EXISTS idx_checkgithub_repo_name ON checkgithub_repository_priorities(repo_name);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_score ON checkgithub_repository_priorities(priority_score);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_last_check ON checkgithub_repository_priorities(last_check);
            CREATE INDEX IF NOT EXISTS idx_checkgithub_priority_level ON checkgithub_repository_priorities(priority_level);
            """
            
            supabase.client.rpc('exec_sql', {'sql': index_sql}).execute()
            print("✅ Индексы созданы")
        except Exception as e:
            print(f"⚠️  Не удалось создать индексы: {e}")
        
        # Проверяем таблицу
        try:
            result = supabase.client.table('checkgithub_repository_priorities').select('*').execute()
            if result.data:
                print(f"✅ Таблица содержит {len(result.data)} записей")
            else:
                print("✅ Таблица создана, но пуста")
        except Exception as e:
            print(f"❌ Ошибка проверки таблицы: {e}")
        
        supabase.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def migrate_data():
    """Мигрирует данные из JSON в Supabase"""
    print("\n🔄 Миграция данных из JSON...")
    
    try:
        from supabase_config import SupabaseManager
        supabase = SupabaseManager()
        
        # Проверяем, есть ли файл JSON
        if os.path.exists('repo_priority.json'):
            print("✅ Файл repo_priority.json найден")
            
            # Мигрируем данные
            success = supabase.migrate_from_json('repo_priority.json')
            if success:
                print("✅ Миграция завершена успешно")
            else:
                print("❌ Миграция не удалась")
        else:
            print("⚠️  Файл repo_priority.json не найден")
        
        supabase.close()
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

def main():
    """Основная функция"""
    print("🚀 GitHub Miners Bot - Supabase Table Creator")
    print("=" * 60)
    
    # Создаем таблицы
    if create_tables():
        print("\n✅ Таблицы созданы/проверены")
        
        # Мигрируем данные
        migrate_data()
        
        print("\n🎯 Следующие шаги:")
        print("1. Проверьте таблицы в Supabase Dashboard")
        print("2. Запустите бота: python main.py")
        print("3. Используйте команду /sync в Telegram")
    else:
        print("\n❌ Не удалось создать таблицы")
        print("💡 Создайте таблицы вручную в Supabase Dashboard")

if __name__ == "__main__":
    main()

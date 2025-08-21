#!/usr/bin/env python3
"""
Тестирование подключения к Supabase и проверка таблиц
"""

import asyncio
import os
from dotenv import load_dotenv

async def test_supabase():
    """Тестирует подключение к Supabase"""
    print("🔗 Тестирование подключения к Supabase...")
    
    # Загружаем переменные окружения
    load_dotenv()
    
    try:
        from supabase_config import SupabaseManager
        supabase = SupabaseManager()
        print("✅ SupabaseManager создан успешно")
        
        # Проверяем URL и ключ
        if supabase.supabase_url and supabase.supabase_url != 'dummy':
            print(f"✅ Supabase URL: {supabase.supabase_url[:30]}...")
        else:
            print("❌ Supabase URL не настроен")
            
        if supabase.supabase_key and supabase.supabase_key != 'dummy':
            print(f"✅ Supabase Key: {supabase.supabase_key[:10]}...")
        else:
            print("❌ Supabase Key не настроен")
        
        # Пытаемся подключиться к базе данных
        print("\n🔍 Тестирование подключения к БД...")
        try:
            # Проверяем существование таблицы
            result = await supabase.client.table('checkgithub_repository_priorities').select('count').execute()
            print("✅ Таблица checkgithub_repository_priorities доступна")
            
            # Получаем количество записей
            count_result = await supabase.client.rpc('count_repository_priorities').execute()
            if count_result.data:
                print(f"✅ Количество записей: {count_result.data[0]}")
            else:
                print("⚠️  Не удалось получить количество записей")
                
        except Exception as e:
            print(f"❌ Ошибка подключения к таблице: {e}")
            
            # Пытаемся создать таблицу
            print("\n🔧 Попытка создания таблицы...")
            try:
                await supabase.create_tables()
                print("✅ Таблицы созданы/проверены")
            except Exception as create_error:
                print(f"❌ Ошибка создания таблиц: {create_error}")
        
        # Тестируем загрузку приоритетов
        print("\n📊 Тестирование загрузки приоритетов...")
        try:
            priorities = await supabase.get_repository_priorities()
            if priorities:
                print(f"✅ Загружено {len(priorities)} приоритетов")
                for priority in priorities[:3]:  # Показываем первые 3
                    print(f"   • {priority.get('repo_name', 'N/A')}: {priority.get('priority_score', 0)}")
            else:
                print("⚠️  Приоритеты не найдены")
        except Exception as e:
            print(f"❌ Ошибка загрузки приоритетов: {e}")
        
        # Тестируем миграцию из JSON
        print("\n🔄 Тестирование миграции из JSON...")
        if os.path.exists('repo_priority.json'):
            try:
                await supabase.migrate_from_json('repo_priority.json')
                print("✅ Миграция из JSON успешна")
            except Exception as e:
                print(f"❌ Ошибка миграции: {e}")
        else:
            print("⚠️  Файл repo_priority.json не найден")
        
        await supabase.close()
        
    except ImportError as e:
        print(f"❌ Ошибка импорта SupabaseManager: {e}")
    except Exception as e:
        print(f"❌ Ошибка создания SupabaseManager: {e}")

async def main():
    """Основная функция"""
    print("🚀 GitHub Miners Bot - Supabase Connection Test")
    print("=" * 60)
    
    await test_supabase()
    
    print("\n" + "=" * 60)
    print("🎯 Результаты тестирования:")
    print("✅ Если все тесты прошли успешно - Supabase работает")
    print("❌ Если есть ошибки - проверьте настройки подключения")
    print("🔧 Используйте команду /sync в боте для синхронизации")

if __name__ == "__main__":
    asyncio.run(main())

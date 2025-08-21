#!/usr/bin/env python3
"""
Тестовый скрипт для проверки синхронизации с Supabase
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
load_dotenv()

async def test_supabase_sync():
    """Тестирует синхронизацию с Supabase"""
    print("🧪 Тестирование синхронизации с Supabase...")
    
    try:
        # Импортируем необходимые модули
        from supabase_config import SupabaseManager
        from main import RepositoryPriorityManager, REPOS
        
        print("✅ Модули успешно импортированы")
        
        # Создаем менеджер Supabase
        supabase_manager = SupabaseManager()
        print("✅ SupabaseManager создан")
        
        # Создаем менеджер приоритетов
        priority_manager = RepositoryPriorityManager()
        print("✅ RepositoryPriorityManager создан")
        
        # Тестируем загрузку приоритетов из БД
        print("\n🔄 Загрузка приоритетов из базы данных...")
        await priority_manager.initialize_priorities()
        
        # Проверяем загруженные данные
        print(f"📊 Загружено приоритетов: {len(priority_manager.priorities)}")
        
        # Показываем несколько примеров
        print("\n📋 Примеры приоритетов:")
        for i, repo in enumerate(REPOS[:3]):  # Показываем первые 3
            priority_data = priority_manager.get_priority(repo)
            print(f"  {repo}:")
            print(f"    - Приоритет: {priority_data['priority_score']:.3f}")
            print(f"    - Интервал: {priority_data['check_interval']} мин")
            print(f"    - Обновлений: {priority_data['update_count']}")
            print(f"    - Проверок: {priority_data['total_checks']}")
        
        # Тестируем статистику
        print("\n📈 Статистика приоритетов:")
        stats = priority_manager.get_priority_stats()
        print(f"  - Всего репозиториев: {stats['total_repos']}")
        print(f"  - Высокий приоритет: {stats['high_priority']} 🔴")
        print(f"  - Средний приоритет: {stats['medium_priority']} 🟡")
        print(f"  - Низкий приоритет: {stats['low_priority']} 🟢")
        print(f"  - Проблемные: {stats['failing_repos']} ⚠️")
        
        print("\n✅ Тест синхронизации завершен успешно!")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("Убедитесь, что все необходимые модули установлены")
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_supabase_sync())

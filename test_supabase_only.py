#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы приоритетов только с Supabase
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
load_dotenv()

async def test_supabase_only():
    """Тестирует работу приоритетов только с Supabase"""
    print("🧪 Тестирование приоритетов только с Supabase...")
    
    try:
        # Импортируем необходимые модули
        from supabase_config import SupabaseManager
        from main import RepositoryPriorityManager, REPOS
        
        print("✅ Модули успешно импортированы")
        
        # Создаем менеджер приоритетов
        priority_manager = RepositoryPriorityManager()
        print("✅ RepositoryPriorityManager создан")
        
        # Проверяем статус Supabase
        if not priority_manager.supabase_manager:
            print("❌ SupabaseManager недоступен")
            return
        
        print("✅ SupabaseManager доступен")
        
        # Тестируем загрузку приоритетов из БД
        print("\n🔄 Загрузка приоритетов из базы данных...")
        priority_manager.initialize_priorities()
        
        # Проверяем загруженные данные
        print(f"📊 Загружено приоритетов: {len(priority_manager.priorities)}")
        print(f"🗄️ Статус БД: {'Синхронизировано' if priority_manager.db_synced else 'Не синхронизировано'}")
        
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
        
        # Тестируем сохранение (изменяем один приоритет)
        print("\n💾 Тестирование сохранения в БД...")
        test_repo = REPOS[0]
        original_score = priority_manager.get_priority(test_repo)['priority_score']
        
        # Временно изменяем приоритет
        priority_manager.priorities[test_repo]['priority_score'] = 0.999
        priority_manager.priorities[test_repo]['update_count'] += 1
        
        # Сохраняем в БД
        priority_manager._save_priorities_to_db()
        print(f"✅ Приоритет {test_repo} сохранен в БД")
        
        # Восстанавливаем оригинальное значение
        priority_manager.priorities[test_repo]['priority_score'] = original_score
        priority_manager.priorities[test_repo]['update_count'] -= 1
        
        # Сохраняем обратно
        priority_manager._save_priorities_to_db()
        print(f"✅ Оригинальный приоритет {test_repo} восстановлен")
        
        print("\n✅ Тест Supabase-only системы завершен успешно!")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("Убедитесь, что все необходимые модули установлены")
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_supabase_only())

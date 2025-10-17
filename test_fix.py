#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
load_dotenv()

async def test_fix():
    """Тестируем исправления"""
    print("🧪 Тестирование исправлений...")
    
    try:
        # Импортируем необходимые модули
        from main import RepositoryPriorityManager, REPOS, check_single_repo
        from aiogram import Bot
        
        print("✅ Модули успешно импортированы")
        
        # Создаем менеджер приоритетов
        priority_manager = RepositoryPriorityManager()
        print("✅ RepositoryPriorityManager создан")
        
        # Проверяем статус Supabase
        if not priority_manager.supabase_manager:
            print("❌ SupabaseManager недоступен")
            return
        
        print("✅ SupabaseManager доступен")
        
        # Инициализируем приоритеты
        print("\n🔄 Инициализация приоритетов...")
        priority_manager.initialize_priorities()
        print(f"✅ Приоритеты инициализированы: {len(priority_manager.priorities)} репозиториев")
        
        # Проверяем запись информации о проверке
        print("\n📝 Тестирование записи информации о проверке...")
        test_repo = REPOS[0]
        
        # Записываем успешную проверку
        priority_manager.record_check(test_repo, success=True, response_time=1.5)
        print(f"✅ Успешная проверка записана для {test_repo}")
        
        # Записываем неудачную проверку
        priority_manager.record_check(test_repo, success=False, response_time=0.0)
        print(f"✅ Неудачная проверка записана для {test_repo}")
        
        # Записываем обновление
        priority_manager.record_update(test_repo)
        print(f"✅ Обновление записано для {test_repo}")
        
        # Проверяем получение приоритета
        priority_data = priority_manager.get_priority(test_repo)
        print(f"✅ Получен приоритет для {test_repo}: {priority_data['priority_score']}")
        
        print("\n✅ Все тесты пройдены успешно!")
        print("🎉 Проблема с SupabaseManager решена!")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_fix())
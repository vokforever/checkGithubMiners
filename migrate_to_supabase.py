#!/usr/bin/env python3
"""
Скрипт для миграции данных из JSON в Supabase
"""

import asyncio
import logging
from supabase_config import SupabaseManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def main():
    """Основная функция миграции"""
    print("🚀 Начинаем миграцию данных в Supabase...")
    
    try:
        # Инициализация Supabase
        supabase = SupabaseManager()
        
        # Создание таблиц
        print("🔨 Создаем таблицы в Supabase...")
        await supabase.create_tables()
        
        # Миграция данных из JSON
        print("📊 Мигрируем данные из repo_priority.json...")
        success = await supabase.migrate_from_json()
        
        if success:
            print("✅ Миграция завершена успешно!")
            print("📁 Исходный JSON файл сохранен как backup")
            
            # Получение отчета
            print("\n📊 Генерируем отчет из Supabase...")
            report = await supabase.get_telegram_report()
            print("\n" + report)
            
        else:
            print("❌ Миграция не удалась")
            
    except Exception as e:
        print(f"💥 Ошибка: {e}")
        logging.error(f"Migration error: {e}")
        
    finally:
        if 'supabase' in locals():
            await supabase.close()

if __name__ == "__main__":
    asyncio.run(main())

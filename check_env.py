#!/usr/bin/env python3
"""
Скрипт для проверки и настройки переменных окружения
"""

import os
import sys
from dotenv import load_dotenv

def check_environment():
    """Проверяет переменные окружения"""
    print("🔍 Проверка переменных окружения...")
    print("=" * 50)
    
    # Загружаем .env файл если он существует
    if os.path.exists('.env'):
        load_dotenv()
        print("✅ Файл .env найден и загружен")
    else:
        print("⚠️  Файл .env не найден")
    
    # Проверяем обязательные переменные
    required_vars = {
        'BOT_TOKEN': 'Telegram Bot Token',
        'GITHUB_TOKEN': 'GitHub API Token', 
        'CHANNEL_ID': 'Telegram Channel ID',
        'ADMIN_ID': 'Admin User ID',
        'SUPABASE_URL': 'Supabase Project URL',
        'SUPABASE_KEY': 'Supabase API Key (anon or service_role)'
    }
    
    missing_vars = []
    available_vars = []
    
            for var, description in required_vars.items():
            value = os.getenv(var)
            if value and value != 'dummy':
                available_vars.append(f"✅ {var}: {description}")
                if var in ['SUPABASE_KEY', 'BOT_TOKEN']:
                    print(f"✅ {var}: {description} (длина: {len(value)} символов)")
                else:
                    print(f"✅ {var}: {description}")
            else:
                missing_vars.append(var)
                print(f"❌ {var}: {description} - НЕ НАСТРОЕН")
    
    print("\n" + "=" * 50)
    
    if missing_vars:
        print(f"🚨 Отсутствуют {len(missing_vars)} переменных окружения:")
        for var in missing_vars:
            print(f"   • {var}")
        
        print("\n💡 Решения:")
        print("1. Создайте файл .env на основе env_template.txt")
        print("2. Настройте переменные в CapRover/Coolify панели")
        print("3. Установите переменные в системе")
        
        return False
    else:
        print("🎉 Все переменные окружения настроены!")
        return True

def create_env_template():
    """Создает пример .env файла"""
    template = """# Bot Configuration
BOT_TOKEN=your_telegram_bot_token_here
GITHUB_TOKEN=your_github_token_here
CHANNEL_ID=your_telegram_channel_id_here
ADMIN_ID=your_admin_user_id_here

# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_api_key_here

# Optional: Legacy variable names for compatibility
# SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
# SUPABASE_ANON_KEY=your_anon_key_here

# Check interval in minutes
CHECK_INTERVAL_MINUTES=60
"""
    
    try:
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write(template)
        print("✅ Создан файл .env.example")
        print("📝 Скопируйте его в .env и заполните реальными значениями")
    except Exception as e:
        print(f"❌ Ошибка создания .env.example: {e}")

def test_supabase_connection():
    """Тестирует подключение к Supabase"""
    print("\n🔗 Тестирование подключения к Supabase...")
    
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
            
    except ImportError as e:
        print(f"❌ Ошибка импорта SupabaseManager: {e}")
    except Exception as e:
        print(f"❌ Ошибка создания SupabaseManager: {e}")

def main():
    """Основная функция"""
    print("🚀 GitHub Miners Bot - Environment Checker")
    print("=" * 50)
    
    # Проверяем переменные окружения
    env_ok = check_environment()
    
    # Тестируем Supabase подключение
    test_supabase_connection()
    
    print("\n" + "=" * 50)
    
    if env_ok:
        print("🎯 Следующие шаги:")
        print("1. Запустите бота: python main.py")
        print("2. Проверьте команду /debug в Telegram")
        print("3. Используйте команду /priority для проверки приоритетов")
    else:
        print("🔧 Следующие шаги:")
        print("1. Настройте переменные окружения")
        print("2. Создайте файл .env или настройте в CapRover")
        print("3. Запустите этот скрипт снова")
    
    # Создаем пример .env файла
    create_env_template()

if __name__ == "__main__":
    main()

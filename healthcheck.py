#!/usr/bin/env python3
import sys
import os
import asyncio
from datetime import datetime

async def health_check():
    """Простая проверка работоспособности"""
    try:
        # Проверяем основные компоненты
        import aiohttp
        import aiogram
        import apscheduler
        import bs4
        import dotenv
        
        # Проверяем наличие необходимых файлов
        required_files = ['main.py', 'data']
        for file in required_files:
            if not os.path.exists(file):
                print(f"Missing required file: {file}", file=sys.stderr)
                return False
        
        # Проверяем переменные окружения
        if not os.getenv('BOT_TOKEN'):
            print("BOT_TOKEN not set", file=sys.stderr)
            return False
            
        print(f"Health check passed at {datetime.now()}")
        return True
        
    except Exception as e:
        print(f"Health check failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    result = asyncio.run(health_check())
    sys.exit(0 if result else 1)

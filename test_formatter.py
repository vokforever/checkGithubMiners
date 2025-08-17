#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки работы современного форматтера
"""

import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_formatting():
    """Тестирует базовое форматирование"""
    print("=== Тест базового форматирования ===")
    
    try:
        from modern_telegram_formatter import convert_markdown_to_telegram
        
        # Тестовый текст
        test_text = """
# Заголовок
**Жирный текст** и *курсив*
`код` и ~~зачеркнутый~~
||спойлер||
"""
        
        print("Исходный текст:")
        print(test_text)
        print()
        
        # Тестируем автоматический выбор формата
        formatted_text, parse_mode = convert_markdown_to_telegram(test_text, "auto")
        print(f"Автоматический формат ({parse_mode}):")
        print(formatted_text)
        print()
        
        # Тестируем HTML формат
        formatted_text, parse_mode = convert_markdown_to_telegram(test_text, "html")
        print(f"HTML формат ({parse_mode}):")
        print(formatted_text)
        print()
        
        # Тестируем MarkdownV2 формат
        formatted_text, parse_mode = convert_markdown_to_telegram(test_text, "markdown_v2")
        print(f"MarkdownV2 формат ({parse_mode}):")
        print(formatted_text)
        print()
        
        return True
        
    except Exception as e:
        print(f"Ошибка тестирования: {e}")
        return False

def test_text_cleaning():
    """Тестирует очистку текста"""
    print("=== Тест очистки текста ===")
    
    try:
        from modern_telegram_formatter import clean_text_for_telegram_modern
        
        # Тестовый текст с HTML и Markdown
        test_text = """
<div>HTML тег</div>
**Markdown текст**
[Ссылка](http://example.com)
{Метаданные}
<!-- Комментарий -->
"""
        
        print("Исходный текст:")
        print(test_text)
        print()
        
        # Очищаем текст
        cleaned_text = clean_text_for_telegram_modern(test_text)
        print("Очищенный текст:")
        print(cleaned_text)
        print()
        
        return True
        
    except Exception as e:
        print(f"Ошибка тестирования: {e}")
        return False

def test_complex_markdown():
    """Тестирует сложное Markdown форматирование"""
    print("=== Тест сложного Markdown ===")
    
    try:
        from modern_telegram_formatter import convert_markdown_to_telegram
        
        # Сложный Markdown с таблицами и кодовыми блоками
        test_text = """
| Колонка 1 | Колонка 2 | Колонка 3 |
|------------|------------|------------|
| Данные 1   | Данные 2   | Данные 3   |

```python
def hello_world():
    print("Hello, World!")
```

**> Расширяемая цитата

> Это будет скрыто по умолчанию
> Пользователь сможет развернуть
"""
        
        print("Исходный текст:")
        print(test_text)
        print()
        
        # Автоматический выбор формата
        formatted_text, parse_mode = convert_markdown_to_telegram(test_text, "auto")
        print(f"Автоматический формат ({parse_mode}):")
        print(formatted_text)
        print()
        
        return True
        
    except Exception as e:
        print(f"Ошибка тестирования: {e}")
        return False

def test_library_availability():
    """Проверяет доступность библиотек"""
    print("=== Проверка доступности библиотек ===")
    
    try:
        from modern_telegram_formatter import TELEGRAMIFY_AVAILABLE
        
        print(f"telegramify-markdown: {'доступен' if TELEGRAMIFY_AVAILABLE else 'не установлен'}")
        
        if TELEGRAMIFY_AVAILABLE:
            print("✓ Основная библиотека работает")
        else:
            print("⚠ Используется fallback режим")
        
        return True
        
    except Exception as e:
        print(f"Ошибка проверки: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("Тестирование современного форматтера для Telegram")
    print("=" * 50)
    print()
    
    tests = [
        test_library_availability,
        test_basic_formatting,
        test_text_cleaning,
        test_complex_markdown
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
                print("✓ Тест пройден")
            else:
                print("✗ Тест не пройден")
        except Exception as e:
            print(f"✗ Ошибка в тесте: {e}")
        
        print()
    
    print("=" * 50)
    print(f"Результат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
    else:
        print("⚠ Некоторые тесты не пройдены")

if __name__ == "__main__":
    main()

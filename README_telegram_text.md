# Очистка текста от форматирования для Telegram

## Обзор

Этот модуль предоставляет комплексные инструменты для очистки и форматирования текста при работе с Telegram Bot API. Решает проблемы с интерпретацией символов Markdown и обеспечивает безопасную отправку сообщений.

## Основные проблемы с форматированием в Telegram

### 1. Символы Markdown интерпретируются как форматирование
- `*текст*` → **текст** (жирный)
- `_текст_` → _текст_ (курсив)
- `` `код` `` → `код` (моноширинный)
- `~~текст~~` → ~~текст~~ (зачеркнутый)
- `||текст||` → ||текст|| (скрытый)

### 2. Служебные теги от языковых моделей
- `<think>`, `</think>`
- `<sys>`, `</sys>`
- `<ai>`, `</ai>`
- `<user>`, `</user>`
- `<assistant>`, `</assistant>`

### 3. Ограничения Telegram
- Максимальная длина сообщения: 4096 символов
- Специальные символы требуют экранирования
- Разные режимы парсинга (Markdown, MarkdownV2, HTML)

## Функции модуля

### Основные функции очистки

#### `clean_markdown_text(text: str) -> str`
Удаляет все символы Markdown форматирования из текста.

```python
from telegram_text_utils import clean_markdown_text

text = "**Жирный** и __курсив__ текст"
cleaned = clean_markdown_text(text)
# Результат: "Жирный и курсив текст"
```

#### `clean_ai_response(text: str) -> str`
Очищает ответы ИИ от служебных тегов и артефактов.

```python
from telegram_text_utils import clean_ai_response

ai_text = "<think>Служебный тег</think>**Важная информация**"
cleaned = clean_ai_response(ai_text)
# Результат: "Важная информация"
```

#### `clean_github_release_body(body: str, max_length: int = 1000) -> str`
Специализированная очистка для описаний релизов GitHub.

```python
from telegram_text_utils import clean_github_release_body

github_body = """<!-- comment -->
**Новые возможности:**
- Улучшения производительности
[Подробнее](https://github.com/repo)"""

cleaned = clean_github_release_body(github_body, max_length=100)
# Результат: "Новые возможности:\n- Улучшения производительности"
```

### Функции экранирования

#### `escape_markdown(text: str) -> str`
Экранирует специальные символы для обычного Markdown.

#### `escape_markdown_v2(text: str) -> str`
Экранирует символы для MarkdownV2 (более строгий режим).

```python
from telegram_text_utils import escape_markdown, escape_markdown_v2

text = "Текст с *звездочками* и _подчеркиваниями_"

# Обычный Markdown
escaped_md = escape_markdown(text)
# Результат: "Текст с \*звездочками\* и \_подчеркиваниями\_"

# MarkdownV2
escaped_md2 = escape_markdown_v2(text)
# Результат: "Текст с \*звездочками\* и \_подчеркиваниями\_"
```

### Функции валидации и безопасности

#### `validate_telegram_text(text: str, max_length: int = 4096) -> str`
Проверяет и подготавливает текст для отправки в Telegram.

```python
from telegram_text_utils import validate_telegram_text

long_text = "a" * 5000  # 5000 символов
validated = validate_telegram_text(long_text)
# Результат: обрезанный до 4096 символов текст
```

#### `format_telegram_message_safe(text: str, parse_mode: str = None) -> tuple[str, str]`
Безопасно форматирует сообщение и рекомендует режим парсинга.

```python
from telegram_text_utils import format_telegram_message_safe

text = "**Жирный** текст с [ссылками]"
safe_text, recommended_mode = format_telegram_message_safe(text)

print(f"Текст: {safe_text}")
print(f"Рекомендуемый режим: {recommended_mode}")
# Результат: режим 'HTML' для безопасного отображения
```

### Функции конвертации

#### `convert_markdown_to_html(text: str) -> str`
Конвертирует простые Markdown элементы в HTML.

```python
from telegram_text_utils import convert_markdown_to_html

markdown_text = "**Жирный** и __курсив__"
html_text = convert_markdown_to_html(markdown_text)
# Результат: "<b>Жирный</b> и <i>курсив</i>"
```

## Практические примеры использования

### 1. Отправка уведомлений о релизах

```python
from aiogram import Bot, types
from aiogram.enums import ParseMode
from telegram_text_utils import clean_github_release_body, escape_markdown

async def send_release_notification(bot: Bot, chat_id: int, release_data: dict):
    # Очищаем описание релиза
    body = release_data.get('body', '')
    cleaned_body = clean_github_release_body(body, max_length=1000)
    
    # Экранируем для Markdown
    escaped_body = escape_markdown(cleaned_body)
    
    message = f"""🚀 Новый релиз: {release_data['name']}
    
{escaped_body}"""
    
    # Отправляем с Markdown парсингом
    await bot.send_message(
        chat_id, 
        message, 
        parse_mode=ParseMode.MARKDOWN
    )
```

### 2. Обработка пользовательского ввода

```python
from telegram_text_utils import clean_ai_response, validate_telegram_text

def process_user_input(user_text: str) -> str:
    # Очищаем от возможных артефактов
    cleaned = clean_ai_response(user_text)
    
    # Валидируем для Telegram
    validated = validate_telegram_text(cleaned)
    
    return validated
```

### 3. Безопасная отправка с автоматическим выбором режима

```python
from aiogram import Bot, types
from aiogram.enums import ParseMode
from telegram_text_utils import format_telegram_message_safe

async def send_safe_message(bot: Bot, chat_id: int, text: str):
    # Автоматически определяем безопасный режим
    safe_text, recommended_mode = format_telegram_message_safe(text)
    
    # Определяем режим парсинга
    if recommended_mode == 'HTML':
        parse_mode = ParseMode.HTML
    elif recommended_mode == 'Markdown':
        parse_mode = ParseMode.MARKDOWN
    else:
        parse_mode = None
    
    await bot.send_message(
        chat_id,
        safe_text,
        parse_mode=parse_mode
    )
```

## Лучшие практики

### 1. Всегда очищайте пользовательский ввод

```python
# ❌ Плохо - может сломать форматирование
await message.answer(user_input, parse_mode=ParseMode.MARKDOWN)

# ✅ Хорошо - безопасная обработка
cleaned_input = clean_ai_response(user_input)
safe_text, mode = format_telegram_message_safe(cleaned_input)
await message.answer(safe_text, parse_mode=mode)
```

### 2. Используйте специализированные функции для разных типов контента

```python
# Для GitHub релизов
body = clean_github_release_body(release['body'])

# Для ответов ИИ
response = clean_ai_response(ai_response)

# Для пользовательского ввода
input_text = clean_markdown_text(user_input)
```

### 3. Ограничивайте длину сообщений

```python
# Автоматическое ограничение
text = validate_telegram_text(long_text, max_length=4096)

# Ручное ограничение для специфичных случаев
description = clean_github_release_body(body, max_length=500)
```

### 4. Выбирайте правильный режим парсинга

```python
# Для простого текста - без парсинга
await bot.send_message(chat_id, text)

# Для форматированного текста - HTML (более надежен)
await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)

# Для Markdown - только если уверены в корректности
await bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
```

## Обработка ошибок

### 1. Проверка длины сообщения

```python
from telegram_text_utils import validate_telegram_text

try:
    safe_text = validate_telegram_text(long_text)
    await bot.send_message(chat_id, safe_text)
except Exception as e:
    # Разбиваем на части или обрезаем
    truncated = long_text[:4093] + "..."
    await bot.send_message(chat_id, truncated)
```

### 2. Fallback для проблемного форматирования

```python
from telegram_text_utils import format_telegram_message_safe

try:
    safe_text, mode = format_telegram_message_safe(problematic_text)
    await bot.send_message(chat_id, safe_text, parse_mode=mode)
except Exception as e:
    # Отправляем без форматирования
    plain_text = clean_markdown_text(problematic_text)
    await bot.send_message(chat_id, plain_text)
```

## Тестирование

Запустите тесты для проверки всех функций:

```bash
python telegram_text_utils.py
```

Или импортируйте в свой код:

```python
from telegram_text_utils import example_usage

# Запуск примеров
example_usage()
```

## Производительность

- Все функции используют регулярные выражения для быстрой обработки
- Минимальное количество проходов по тексту
- Эффективная обработка больших объемов текста
- Кэширование регулярных выражений

## Совместимость

- Python 3.7+
- aiogram 2.x и 3.x
- python-telegram-bot
- Любые другие Telegram библиотеки

## Лицензия

MIT License - свободное использование в коммерческих и некоммерческих проектах.

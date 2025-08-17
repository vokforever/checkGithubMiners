#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для очистки и форматирования текста для Telegram

Этот модуль содержит функции для:
- Очистки текста от Markdown форматирования
- Очистки ответов ИИ от служебных тегов
- Безопасного форматирования сообщений для Telegram
- Конвертации Markdown в HTML
"""

import re
from typing import Tuple

def clean_markdown_text(text: str) -> str:
    """
    Удаляет символы Markdown форматирования из текста
    
    Args:
        text: Исходный текст с Markdown разметкой
        
    Returns:
        str: Текст без Markdown разметки
        
    Examples:
        >>> clean_markdown_text("**жирный** и __курсив__")
        'жирный и курсив'
        
        >>> clean_markdown_text("`код` и ~~зачеркнутый~~")
        'код и зачеркнутый'
    """
    if not text:
        return text
    
    # Удаляем жирное форматирование **text**
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    
    # Удаляем курсив __text__
    text = re.sub(r'__(.*?)__', r'\1', text)
    
    # Удаляем моноширинный ```text```
    text = re.sub(r'```(.*?)```', r'\1', text)
    
    # Удаляем зачеркнутый ~~text~~
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    
    # Удаляем скрытый ||text||
    text = re.sub(r'\|\|(.*?)\|\|', r'\1', text)
    
    # Удаляем одиночные символы форматирования
    text = re.sub(r'[\*_~`|]', '', text)
    
    return text.strip()

def clean_ai_response(text: str) -> str:
    """
    Очищает ответ ИИ от служебных тегов и разметки
    
    Args:
        text: Ответ от ИИ с возможными служебными тегами
        
    Returns:
        str: Очищенный текст
        
    Examples:
        >>> clean_ai_response("<think>Это служебный тег</think>Обычный текст")
        'Обычный текст'
        
        >>> clean_ai_response("Текст с [метаданными] и {информацией}")
        'Текст с  и '
    """
    if not text:
        return text
    
    # Удаляем типичные служебные теги
    text = re.sub(r'</?think>', '', text)
    text = re.sub(r'</?sys>', '', text)
    text = re.sub(r'</?ai>', '', text)
    text = re.sub(r'</?user>', '', text)
    text = re.sub(r'</?assistant>', '', text)
    
    # Удаляем HTML/XML теги
    text = re.sub(r'<[^>]+>', '', text)
    
    # Удаляем Markdown форматирование
    text = clean_markdown_text(text)
    
    # Дополнительная очистка от специфичных артефактов
    text = re.sub(r'\[.*?\]', '', text)  # Удаляем текст в квадратных скобках
    text = re.sub(r'\{.*?\}', '', text)  # Удаляем текст в фигурных скобках
    
    # Удаляем лишние пробелы и переносы строк
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Максимум 2 пустые строки подряд
    text = re.sub(r' +', ' ', text)  # Убираем множественные пробелы
    
    return text.strip()

def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Текст с экранированными символами
        
    Examples:
        >>> escape_markdown("Текст с *звездочками* и _подчеркиваниями_")
        'Текст с \\*звездочками\\* и \\_подчеркиваниями\\_'
    """
    if not text:
        return ""
    
    # Список символов, которые нужно экранировать в Markdown
    escape_chars = '_*[]()~`>#+='
    
    # Сначала удаляем существующие экранирующие слэши
    cleaned_text = ""
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in escape_chars:
            # Пропускаем обратный слэш, оставляем только символ
            cleaned_text += text[i + 1]
            i += 2
        else:
            cleaned_text += text[i]
            i += 1
    
    # Теперь экранируем нужные символы
    escaped_text = ""
    for char in cleaned_text:
        if char in escape_chars:
            escaped_text += f'\\{char}'
        else:
            escaped_text += char
    
    return escaped_text

def escape_markdown_v2(text: str) -> str:
    """
    Экранирует специальные символы для MarkdownV2 (более строгий режим)
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Текст с экранированными символами для MarkdownV2
        
    Examples:
        >>> escape_markdown_v2("Текст с . и !")
        'Текст с \\. и \\!'
    """
    if not text:
        return ""
    
    # Список символов для MarkdownV2
    escape_chars = '_*[]()~`>#+=|{}.!'
    
    escaped_text = ""
    for char in text:
        if char in escape_chars:
            escaped_text += f'\\{char}'
        else:
            escaped_text += char
    
    return escaped_text

def validate_telegram_text(text: str, max_length: int = 4096) -> str:
    """
    Проверяет и подготавливает текст для отправки в Telegram
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина сообщения
        
    Returns:
        str: Подготовленный текст
        
    Examples:
        >>> len(validate_telegram_text("a" * 5000))
        4096
    """
    if not text:
        return ""
    
    # Ограничиваем длину сообщения
    if len(text) > max_length:
        # Пытаемся обрезать по словам, а не по символам
        words = text[:max_length-3].rsplit(' ', 1)
        if len(words) > 1:
            text = words[0] + "..."
        else:
            text = text[:max_length-3] + "..."
    
    # Очищаем от служебных тегов
    text = clean_ai_response(text)
    
    return text

def clean_github_release_body(body: str, max_length: int = 1000) -> str:
    """
    Специализированная очистка для описания релизов GitHub
    
    Args:
        body: Описание релиза
        max_length: Максимальная длина
        
    Returns:
        str: Очищенное описание
        
    Examples:
        >>> clean_github_release_body("<!-- comment -->**Bold** text", 50)
        'Bold text'
    """
    if not body:
        return ""
    
    # Очищаем от Markdown
    cleaned = clean_markdown_text(body.strip())
    
    # Удаляем специфичные для GitHub элементы
    cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)  # HTML комментарии
    cleaned = re.sub(r'\[.*?\]\(.*?\)', '', cleaned)  # Markdown ссылки
    cleaned = re.sub(r'!\[.*?\]\(.*?\)', '', cleaned)  # Markdown изображения
    
    # Убираем лишние пробелы и переносы
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r' +', ' ', cleaned)
    
    # Ограничиваем длину
    if len(cleaned) > max_length:
        # Пытаемся обрезать по предложениям
        sentences = cleaned[:max_length-3].rsplit('.', 1)
        if len(sentences) > 1:
            cleaned = sentences[0] + "..."
        else:
            cleaned = cleaned[:max_length-3] + "..."
    
    return cleaned.strip()

def format_telegram_message_safe(text: str, parse_mode: str = None) -> Tuple[str, str]:
    """
    Безопасно форматирует сообщение для Telegram
    
    Args:
        text: Исходный текст
        parse_mode: Режим парсинга
        
    Returns:
        tuple: (подготовленный_текст, рекомендуемый_режим_парсинга)
        
    Examples:
        >>> text, mode = format_telegram_message_safe("**Bold** text")
        >>> mode
        'HTML'
        >>> "Bold" in text
        True
    """
    if not text:
        return "", None
    
    # Очищаем от служебных тегов
    cleaned_text = clean_ai_response(text)
    
    # Проверяем длину
    validated_text = validate_telegram_text(cleaned_text)
    
    # Определяем рекомендуемый режим парсинга
    if parse_mode is None:
        # Анализируем текст и рекомендуем режим
        if re.search(r'[*_`~|]', validated_text):
            # Есть символы Markdown - используем HTML для безопасности
            recommended_mode = 'HTML'
            # Конвертируем Markdown в HTML
            validated_text = convert_markdown_to_html(validated_text)
        else:
            recommended_mode = None
    else:
        recommended_mode = parse_mode
    
    return validated_text, recommended_mode

def convert_markdown_to_html(text: str) -> str:
    """
    Конвертирует простые Markdown элементы в HTML
    
    Args:
        text: Текст с Markdown разметкой
        
    Returns:
        str: Текст с HTML разметкой
        
    Examples:
        >>> convert_markdown_to_html("**жирный** и __курсив__")
        '<b>жирный</b> и <i>курсив</i>'
    """
    if not text:
        return text
    
    # Жирный текст
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Курсив
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    
    # Моноширинный
    text = re.sub(r'```(.*?)```', r'<code>\1</code>', text)
    
    # Зачеркнутый
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    
    # Подчеркнутый
    text = re.sub(r'<u>(.*?)</u>', r'<u>\1</u>', text)
    
    return text

def clean_telegram_username(username: str) -> str:
    """
    Очищает username для безопасного использования в Telegram
    
    Args:
        username: Исходный username
        
    Returns:
        str: Очищенный username
        
    Examples:
        >>> clean_telegram_username("@user_name")
        'user_name'
        
        >>> clean_telegram_username("user@name")
        'username'
    """
    if not username:
        return ""
    
    # Убираем символ @ если есть
    username = username.lstrip('@')
    
    # Убираем недопустимые символы
    username = re.sub(r'[^\w\d_]', '', username)
    
    return username[:32]  # Telegram ограничение на длину username

# --- ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ---

def example_usage():
    """Примеры использования всех функций"""
    
    print("=== Примеры очистки текста для Telegram ===\n")
    
    # Пример 1: Очистка Markdown
    markdown_text = "**Жирный текст** и __курсив__, а также `код` и ~~зачеркнутый~~"
    cleaned = clean_markdown_text(markdown_text)
    print(f"1. Очистка Markdown:")
    print(f"   Исходный: {markdown_text}")
    print(f"   Очищенный: {cleaned}\n")
    
    # Пример 2: Очистка ответа ИИ
    ai_response = "<think>Это служебный тег</think>**Важная информация** с [метаданными]"
    cleaned_ai = clean_ai_response(ai_response)
    print(f"2. Очистка ответа ИИ:")
    print(f"   Исходный: {ai_response}")
    print(f"   Очищенный: {cleaned_ai}\n")
    
    # Пример 3: Экранирование Markdown
    text_to_escape = "Текст с *звездочками* и _подчеркиваниями_"
    escaped = escape_markdown(text_to_escape)
    print(f"3. Экранирование Markdown:")
    print(f"   Исходный: {text_to_escape}")
    print(f"   Экранированный: {escaped}\n")
    
    # Пример 4: Конвертация в HTML
    markdown_for_html = "**Жирный** и __курсив__ текст"
    html_text = convert_markdown_to_html(markdown_for_html)
    print(f"4. Конвертация в HTML:")
    print(f"   Markdown: {markdown_for_html}")
    print(f"   HTML: {html_text}\n")
    
    # Пример 5: Безопасное форматирование
    unsafe_text = "Текст с **форматированием** и [ссылками]"
    safe_text, recommended_mode = format_telegram_message_safe(unsafe_text)
    print(f"5. Безопасное форматирование:")
    print(f"   Исходный: {unsafe_text}")
    print(f"   Безопасный: {safe_text}")
    print(f"   Рекомендуемый режим: {recommended_mode}\n")
    
    # Пример 6: Очистка GitHub релиза
    github_body = """<!-- Release notes -->
    **Новые возможности:**
    - Улучшенная производительность
    - Исправлены баги
    
    [Подробнее](https://github.com/repo)"""
    cleaned_github = clean_github_release_body(github_body, max_length=100)
    print(f"6. Очистка GitHub релиза:")
    print(f"   Исходный: {github_body}")
    print(f"   Очищенный: {cleaned_github}\n")

if __name__ == "__main__":
    example_usage()

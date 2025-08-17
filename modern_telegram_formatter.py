#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Современные утилиты для форматирования текста в Telegram

Этот модуль содержит функции для работы с современными библиотеками:
- telegramify-markdown: Конвертация Markdown в Telegram MarkdownV2
- formatter-chatgpt-telegram: Специализированный конвертер для ChatGPT
- tgentity: Конвертация Telegram entities

Основные возможности:
- Автоматическая конвертация Markdown в Telegram-совместимые форматы
- Поддержка LaTeX, таблиц, списков
- Обработка расширяемых цитат и спойлеров
- Безопасная отправка сообщений с автоматическим выбором режима
- Очистка текста от HTML и Markdown разметки
"""

import re
import logging
from typing import Tuple, Optional, Dict, Any
from pathlib import Path

# Настройка логирования
logger = logging.getLogger(__name__)

try:
    import telegramify_markdown
    from telegramify_markdown import customize
    TELEGRAMIFY_AVAILABLE = True
except ImportError:
    TELEGRAMIFY_AVAILABLE = False
    logger.warning("telegramify-markdown не установлен. Установите: pip install telegramify-markdown")



class ModernTelegramFormatter:
    """
    Современный форматтер для Telegram с поддержкой различных библиотек
    """
    
    def __init__(self):
        """Инициализация форматтера"""
        self.setup_telegramify()
    
    def setup_telegramify(self):
        """Настройка telegramify-markdown для оптимальной работы"""
        if not TELEGRAMIFY_AVAILABLE:
            return
        
        try:
            # Настройка для лучшей совместимости с Telegram
            customize.strict_markdown = False  # Разрешить __underline__
            customize.cite_expandable = True   # Включить расширяемые цитаты
            customize.underline = True         # Поддержка подчеркивания
            customize.spoiler = True           # Поддержка спойлеров
            
            logger.info("telegramify-markdown настроен успешно")
        except Exception as e:
            logger.error(f"Ошибка настройки telegramify-markdown: {e}")
    
    def convert_markdown_to_telegram(self, text: str, target_format: str = "markdown_v2") -> Tuple[str, str]:
        """
        Конвертирует Markdown в Telegram-совместимый формат
        
        Args:
            text: Исходный Markdown текст
            target_format: Целевой формат ("markdown_v2", "html", "auto")
            
        Returns:
            Tuple[str, str]: (конвертированный_текст, рекомендуемый_parse_mode)
        """
        if not text:
            return "", None
        
        # Очищаем от служебных тегов
        cleaned_text = self.clean_text_for_telegram(text)
        
        if target_format == "auto":
            # Автоматически определяем лучший формат
            if self._has_complex_markdown(cleaned_text):
                return self._convert_to_html(cleaned_text), "HTML"
            else:
                return self._convert_to_markdown_v2(cleaned_text), "MarkdownV2"
        elif target_format == "html":
            return self._convert_to_html(cleaned_text), "HTML"
        else:  # markdown_v2
            return self._convert_to_markdown_v2(cleaned_text), "MarkdownV2"
    
    def _has_complex_markdown(self, text: str) -> bool:
        """Проверяет, содержит ли текст сложное Markdown форматирование"""
        complex_patterns = [
            r'```[\s\S]*?```',  # Многострочные кодовые блоки
            r'\|.*\|.*\|',       # Таблицы
            r'\[.*?\]\(.*?\)',   # Ссылки
            r'!\[.*?\]\(.*?\)',  # Изображения
            r'<!--.*?-->',       # HTML комментарии
            r'<[^>]+>',          # HTML теги
        ]
        
        for pattern in complex_patterns:
            if re.search(pattern, text, re.MULTILINE | re.DOTALL):
                return True
        
        return False
    
    def _convert_to_markdown_v2(self, text: str) -> str:
        """Конвертирует в Telegram MarkdownV2"""
        if not TELEGRAMIFY_AVAILABLE:
            # Fallback на базовую конвертацию
            return self._basic_markdown_v2_conversion(text)
        
        try:
            # Используем telegramify-markdown
            converted = telegramify_markdown.markdownify(text)
            
            # Проверяем валидность
            if self._validate_markdown_v2(converted):
                return converted
            else:
                logger.warning("telegramify-markdown вернул невалидный MarkdownV2, используем fallback")
                return self._basic_markdown_v2_conversion(text)
                
        except Exception as e:
            logger.error(f"Ошибка конвертации в MarkdownV2: {e}")
            return self._basic_markdown_v2_conversion(text)
    
    def _convert_to_html(self, text: str) -> str:
        """Конвертирует в HTML"""
        # Используем базовую HTML конвертацию
        return self._basic_html_conversion(text)
    
    def _basic_markdown_v2_conversion(self, text: str) -> str:
        """Базовая конвертация в MarkdownV2 с экранированием"""
        if not text:
            return ""
        
        # Экранируем специальные символы для MarkdownV2
        escape_chars = '_*[]()~`>#+=|{}.!'
        escaped_text = ""
        
        for char in text:
            if char in escape_chars:
                escaped_text += f'\\{char}'
            else:
                escaped_text += char
        
        return escaped_text
    
    def _basic_html_conversion(self, text: str) -> str:
        """Базовая конвертация в HTML"""
        if not text:
            return text
        
        # Простые Markdown элементы в HTML
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
        text = re.sub(r'\|\|(.*?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', text)
        
        # Обработка переносов строк
        text = text.replace('\n', '<br>')
        
        return text
    
    def _validate_markdown_v2(self, text: str) -> bool:
        """Проверяет валидность MarkdownV2"""
        if not text:
            return False
        
        # Проверяем на наличие неэкранированных специальных символов
        unescaped_chars = re.findall(r'(?<!\\)[_*[\]()~`>#+=|{}.!]', text)
        
        if unescaped_chars:
            logger.debug(f"Найдены неэкранированные символы в MarkdownV2: {unescaped_chars}")
            return False
        
        return True
    
    def clean_text_for_telegram(self, text: str) -> str:
        """
        Очищает текст от служебных тегов и разметки для отправки в Telegram
        """
        if not text:
            return text
        
        # Удаляем HTML/XML теги
        text = re.sub(r'<[^>]+>', '', text)
        
        # Дополнительная очистка от специфичных артефактов
        text = re.sub(r'\[.*?\]', '', text)  # Удаляем текст в квадратных скобках
        text = re.sub(r'\{.*?\}', '', text)  # Удаляем текст в фигурных скобках
        
        # Удаляем лишние пробелы и переносы строк
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Максимум 2 пустые строки подряд
        text = re.sub(r' +', ' ', text)  # Убираем множественные пробелы
        
        return text.strip()
    

    
    def convert_telegram_entities(self, message) -> Dict[str, str]:
        """
        Конвертирует Telegram entities в различные форматы
        """
        logger.warning("Конвертация entities не поддерживается в текущей версии")
        return {}
    
    def split_long_message(self, text: str, max_length: int = 4096) -> list[str]:
        """
        Разбивает длинное сообщение на части
        """
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        # Разбиваем по строкам
        lines = text.split('\n')
        
        for line in lines:
            # Если добавление строки превысит лимит
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line
                else:
                    # Строка слишком длинная, разбиваем по словам
                    words = line.split()
                    for word in words:
                        if len(current_part) + len(word) + 1 > max_length:
                            if current_part:
                                parts.append(current_part.strip())
                                current_part = word
                            else:
                                # Слово слишком длинное, обрезаем
                                parts.append(word[:max_length-3] + "...")
                                current_part = ""
                        else:
                            current_part += (" " if current_part else "") + word
            else:
                current_part += ("\n" if current_part else "") + line
        
        if current_part:
            parts.append(current_part.strip())
        
        return parts

# Создаем глобальный экземпляр форматтера
formatter = ModernTelegramFormatter()

# Функции для обратной совместимости
def convert_markdown_to_telegram(text: str, target_format: str = "markdown_v2") -> Tuple[str, str]:
    """Упрощенная функция для конвертации Markdown"""
    return formatter.convert_markdown_to_telegram(text, target_format)

def clean_text_for_telegram_modern(text: str) -> str:
    """Современная очистка текста для Telegram"""
    return formatter.clean_text_for_telegram(text)



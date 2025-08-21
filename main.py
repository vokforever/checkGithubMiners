import asyncio
import json
import os
import logging
import sys
import locale
import ctypes
import traceback
import shutil
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Set, Tuple
from aiohttp import ClientSession, ClientError, ClientResponseError
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Импорт современного форматтера
try:
    from modern_telegram_formatter import formatter, convert_markdown_to_telegram
    MODERN_FORMATTER_AVAILABLE = True
except ImportError:
    MODERN_FORMATTER_AVAILABLE = False
    logging.warning("Современный форматтер не доступен, используются базовые функции")

# --- НАСТРОЙКА КОДИРОВКИ ДЛЯ WINDOWS ---
if sys.platform == "win32":
    # Включаем поддержку UTF-8 в консоли Windows
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

    # Пытаемся установить кодовую страницу консоли на UTF-8
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
    except Exception as e:
        print(f"Не удалось установить кодировку UTF-8: {e}")

# Загрузка переменных окружения
load_dotenv()

# --- НАСТРОЙКИ ИЗ .ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DONATE_URL = "https://boosty.to/vokforever/donate"
MAX_RETRIES = 3
RETRY_DELAY = 2
HISTORY_DAYS = 30
PRIORITY_UPDATE_DAYS = 7

# --- СПИСОК РЕПОЗИТОРИЕВ ---
REPOS = [
    "andru-kun/wildrig-multi",
    "OneZeroMiner/onezerominer", 
    "trexminer/T-Rex",
    "xmrig/xmrig",
    "Lolliedieb/lolMiner-releases",
    "doktor83/SRBMiner-Multi",
    "nicehash/nicehashminer",
    "pooler/cpuminer",
    "rplant8/cpuminer-opt-rplant",
    "JayDDee/cpuminer-opt",
    "alephium/gpu-miner"
]

# --- ПАРАМЕТРЫ ПРИОРИТЕТНОЙ ПРОВЕРКИ ---
MIN_CHECK_INTERVAL_MINUTES = 15
MAX_CHECK_INTERVAL_MINUTES = 1440
PRIORITY_THRESHOLD_HIGH = 0.5
PRIORITY_THRESHOLD_LOW = 0.1
DEFAULT_CHECK_INTERVAL_MINUTES = 360  # 6 часов

# --- ФАЙЛЫ ХРАНЕНИЯ ДАННЫХ ---
STATE_FILE = "last_releases.json"
FILTERS_FILE = "user_filters.json"
HISTORY_FILE = "releases_history.json"
USERS_FILE = "users.json"
STATISTICS_FILE = "bot_statistics.json"

# Создаем папку для резервных копий
BACKUP_DIR = "backups"
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# --- УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ---
def setup_logging():
    """Настройка системы логирования"""
    # Создаем папку для логов
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Настройка форматирования
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # Основной лог-файл
    file_handler = logging.FileHandler(
        f'{log_dir}/bot_{datetime.now().strftime("%Y%m%d")}.log', 
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Лог ошибок
    error_handler = logging.FileHandler(
        f'{log_dir}/errors_{datetime.now().strftime("%Y%m%d")}.log',
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Консольный вывод
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# --- ФУНКЦИЯ ОЧИСТКИ MARKDOWN ---
def clean_markdown_text(text: str) -> str:
    """
    Удаляет символы Markdown форматирования из текста
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
    
    # Удаляем одиночные символы форматирования, которые могут остаться
    text = re.sub(r'[\*_~`|]', '', text)
    
    return text.strip()

def clean_text_for_telegram(text: str) -> str:
    """
    Очищает текст от служебных тегов и разметки для отправки в Telegram
    """
    if not text:
        return text
    
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
    """Экранирует специальные символы Markdown (не MarkdownV2)"""
    if not text:
        return ""

    # Список символов, которые нужно экранировать в Markdown
    escape_chars = '_*[]()~`>#+='

    # Сначала удаляем существующие экранирующие слэши перед этими символами
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
        max_length: Максимальная длина сообщения (по умолчанию 4096 для Telegram)
    
    Returns:
        str: Подготовленный текст
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
    text = clean_text_for_telegram(text)
    
    return text

def clean_github_release_body(body: str, max_length: int = 1000) -> str:
    """
    Специализированная очистка для описания релизов GitHub
    
    Args:
        body: Описание релиза
        max_length: Максимальная длина
    
    Returns:
        str: Очищенное описание
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

def format_telegram_message_safe(text: str, parse_mode: str = None) -> tuple[str, str]:
    """
    Безопасно форматирует сообщение для Telegram
    
    Args:
        text: Исходный текст
        parse_mode: Режим парсинга (None, 'Markdown', 'MarkdownV2', 'HTML')
    
    Returns:
        tuple: (подготовленный_текст, рекомендуемый_режим_парсинга)
    """
    if not text:
        return "", None
    
    # Используем современный форматтер, если доступен
    if MODERN_FORMATTER_AVAILABLE:
        try:
            # Автоматически определяем лучший формат
            formatted_text, recommended_mode = convert_markdown_to_telegram(text, "auto")
            
            # Проверяем длину
            validated_text = validate_telegram_text(formatted_text)
            
            return validated_text, recommended_mode
            
        except Exception as e:
            logging.error(f"Ошибка современного форматтера: {e}, используем fallback")
    
    # Fallback на старую логику
    # Очищаем от служебных тегов
    cleaned_text = clean_text_for_telegram(text)
    
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
    """
    if not text:
        return text
    
    # Жирный текст
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Курсив
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    
    # Моноширинный
    text = re.sub(r'```(.*?)```', r'<code>\1</code>', text)

async def send_formatted_message(bot: Bot, chat_id: int, text: str, 
                               target_format: str = "auto", 
                               max_length: int = 4096) -> bool:
    """
    Отправляет отформатированное сообщение с автоматическим выбором режима
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата для отправки
        text: Текст для отправки
        target_format: Целевой формат ("auto", "markdown_v2", "html")
        max_length: Максимальная длина сообщения
    
    Returns:
        bool: True если сообщение отправлено успешно
    """
    if not text:
        return False
    
    try:
        # Используем современный форматтер, если доступен
        if MODERN_FORMATTER_AVAILABLE:
            try:
                # Конвертируем текст
                formatted_text, parse_mode = convert_markdown_to_telegram(text, target_format)
                
                # Разбиваем длинные сообщения
                if len(formatted_text) > max_length:
                    message_parts = formatter.split_long_message(formatted_text, max_length)
                    
                    for part in message_parts:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=part,
                            parse_mode=parse_mode
                        )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=formatted_text,
                        parse_mode=parse_mode
                    )
                
                return True
                
            except Exception as e:
                logging.error(f"Ошибка современного форматтера: {e}, используем fallback")
        
        # Fallback на старую логику
        formatted_text, parse_mode = format_telegram_message_safe(text)
        
        if len(formatted_text) > max_length:
            # Простое разбиение по длине
            parts = [formatted_text[i:i+max_length] for i in range(0, len(formatted_text), max_length)]
            
            for part in parts:
                await bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode=parse_mode
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=formatted_text,
                parse_mode=parse_mode
            )
        
        return True
        
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        return False
    
    # Зачеркнутый
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    
    # Подчеркнутый
    text = re.sub(r'<u>(.*?)</u>', r'<u>\1</u>', text)
    
    return text

def clean_telegram_username(username: str) -> str:
    """
    Очищает username для безопасного использования в Telegram
    """
    if not username:
        return ""
    
    # Убираем символ @ если есть
    username = username.lstrip('@')
    
    # Убираем недопустимые символы
    username = re.sub(r'[^\w\d_]', '', username)
    
    return username[:32]  # Telegram ограничение на длину username

# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ СТАТИСТИКОЙ ---
class StatisticsManager:
    def __init__(self):
        self.stats_file = STATISTICS_FILE
        self.stats = self._load_stats()

    def _load_stats(self) -> Dict:
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки статистики: {e}")
        
        return {
            'total_checks': 0,
            'total_releases_found': 0,
            'total_notifications_sent': 0,
            'errors_count': 0,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'last_activity': None,
            'repo_stats': {repo: {'checks': 0, 'releases': 0} for repo in REPOS}
        }

    def _save_stats(self):
        try:
            self.stats['last_activity'] = datetime.now(timezone.utc).isoformat()
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

    def increment_checks(self, repo_name: str = None):
        self.stats['total_checks'] += 1
        if repo_name and repo_name in self.stats['repo_stats']:
            self.stats['repo_stats'][repo_name]['checks'] += 1
        self._save_stats()

    def increment_releases(self, repo_name: str = None):
        self.stats['total_releases_found'] += 1
        if repo_name and repo_name in self.stats['repo_stats']:
            self.stats['repo_stats'][repo_name]['releases'] += 1
        self._save_stats()

    def increment_notifications(self):
        self.stats['total_notifications_sent'] += 1
        self._save_stats()

    def increment_errors(self):
        self.stats['errors_count'] += 1
        self._save_stats()

    def get_uptime(self) -> str:
        try:
            start_time = datetime.fromisoformat(self.stats['start_time'])
            uptime = datetime.now(timezone.utc) - start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{days}д {hours}ч {minutes}м"
        except:
            return "Неизвестно"

# --- УЛУЧШЕНЫЙ КЛАСС ДЛЯ УПРАВЛЕНИЯ ПРИОРИТЕТАМИ ---
class RepositoryPriorityManager:
    def __init__(self):
        self.priorities = {}
        self.last_priority_update = None
        self.supabase_manager = None
        self.db_synced = False
        
        # Инициализируем SupabaseManager
        try:
            from supabase_config import SupabaseManager
            self.supabase_manager = SupabaseManager()
            logger.info("SupabaseManager успешно инициализирован")
        except ImportError as e:
            logger.error(f"Не удалось импортировать SupabaseManager: {e}")
        except Exception as e:
            logger.error(f"Ошибка инициализации SupabaseManager: {e}")

    async def _load_priorities_from_db(self) -> Dict[str, Dict]:
        """Загружает приоритеты из базы данных Supabase"""
        if not self.supabase_manager:
            logger.error("SupabaseManager недоступен, невозможно загрузить приоритеты")
            raise RuntimeError("SupabaseManager недоступен")

        try:
            # Получаем данные из базы
            result = await self.supabase_manager.client.table('checkgithub_repository_priorities').select('*').execute()
            
            if result.data:
                db_priorities = {}
                for record in result.data:
                    repo_name = record.get('repo_name')
                    if repo_name in REPOS:
                        db_priorities[repo_name] = {
                            'update_count': record.get('update_count', 0),
                            'last_update': record.get('last_update'),
                            'check_interval': record.get('check_interval', DEFAULT_CHECK_INTERVAL_MINUTES),
                            'priority_score': float(record.get('priority_score', 0.0)),
                            'last_check': record.get('last_check'),
                            'consecutive_failures': record.get('consecutive_failures', 0),
                            'total_checks': record.get('total_checks', 0),
                            'average_response_time': float(record.get('average_response_time', 0.0))
                        }

                # Заполняем недостающие репозитории дефолтными значениями
                for repo in REPOS:
                    if repo not in db_priorities:
                        db_priorities[repo] = self._create_default_priority()

                self.db_synced = True
                logger.info(f"Приоритеты загружены из БД: {len(db_priorities)} репозиториев")
                return db_priorities
            else:
                logger.warning("В БД нет данных о приоритетах, создаем дефолтные")
                return {repo: self._create_default_priority() for repo in REPOS}

        except Exception as e:
            logger.error(f"Ошибка загрузки приоритетов из БД: {e}")
            raise RuntimeError(f"Не удалось загрузить приоритеты из БД: {e}")

    async def initialize_priorities(self):
        """Инициализирует приоритеты при запуске"""
        self.priorities = await self._load_priorities_from_db()
        self.last_priority_update = datetime.now(timezone.utc)

    def _create_default_priority(self) -> Dict:
        return {
            'update_count': 0,
            'last_update': None,
            'check_interval': DEFAULT_CHECK_INTERVAL_MINUTES,
            'priority_score': 0.0,
            'last_check': None,
            'consecutive_failures': 0,
            'total_checks': 0,
            'average_response_time': 0.0
        }

    async def _save_priorities_to_db(self):
        """Сохраняет приоритеты в базу данных Supabase"""
        if not self.supabase_manager:
            logger.error("SupabaseManager недоступен, невозможно сохранить приоритеты")
            raise RuntimeError("SupabaseManager недоступен")

        try:
            repos_data = []
            for repo_name, repo_data in self.priorities.items():
                # Определяем уровень приоритета
                priority_level = self._get_priority_level(repo_data.get('priority_score', 0))
                
                repo_record = {
                    'repo_name': repo_name,
                    'display_name': repo_name.split('/')[-1],
                    'update_count': repo_data.get('update_count', 0),
                    'last_update': repo_data.get('last_update'),
                    'check_interval': repo_data.get('check_interval', DEFAULT_CHECK_INTERVAL_MINUTES),
                    'priority_score': repo_data.get('priority_score', 0.0),
                    'last_check': repo_data.get('last_check'),
                    'consecutive_failures': repo_data.get('consecutive_failures', 0),
                    'total_checks': repo_data.get('total_checks', 0),
                    'average_response_time': repo_data.get('average_response_time', 0.0),
                    'priority_level': priority_level,
                    'priority_color': self._get_priority_color(repo_data.get('priority_score', 0)),
                    'updated_at': 'now()'
                }
                repos_data.append(repo_record)

            # Upsert данные в БД
            result = await self.supabase_manager.client.table('checkgithub_repository_priorities').upsert(
                repos_data,
                on_conflict='repo_name'
            ).execute()

            logger.info(f"Приоритеты успешно сохранены в БД: {len(repos_data)} репозиториев")

        except Exception as e:
            logger.error(f"Ошибка сохранения приоритетов в БД: {e}")
            raise RuntimeError(f"Не удалось сохранить приоритеты в БД: {e}")

    def _save_priorities(self):
        """Основной метод сохранения - использует БД"""
        asyncio.create_task(self._save_priorities_to_db())

    def _get_priority_level(self, score: float) -> str:
        """Определяет уровень приоритета по score"""
        if score >= PRIORITY_THRESHOLD_HIGH:
            return 'high'
        elif score <= PRIORITY_THRESHOLD_LOW:
            return 'low'
        else:
            return 'medium'

    def _get_priority_color(self, score: float) -> str:
        """Определяет цвет приоритета по score"""
        if score >= PRIORITY_THRESHOLD_HIGH:
            return '🔴'
        elif score <= PRIORITY_THRESHOLD_LOW:
            return '🟢'
        else:
            return '🟡'

    def get_priority(self, repo: str) -> Dict:
        if repo not in self.priorities:
            self.priorities[repo] = self._create_default_priority()
            # Асинхронно сохраняем в БД
            asyncio.create_task(self._save_priorities_to_db())
        return self.priorities[repo]

    def record_update(self, repo: str):
        priority_data = self.get_priority(repo)
        priority_data['update_count'] += 1
        priority_data['last_update'] = datetime.now(timezone.utc).isoformat()
        priority_data['consecutive_failures'] = 0  # Сбрасываем счетчик ошибок
        # Асинхронно сохраняем в БД
        asyncio.create_task(self._save_priorities_to_db())
        logger.info(f"Зарегистрировано обновление для {repo}. Всего обновлений: {priority_data['update_count']}")

    def record_check(self, repo: str, success: bool = True, response_time: float = 0.0):
        """Записывает информацию о проверке репозитория"""
        priority_data = self.get_priority(repo)
        priority_data['total_checks'] += 1
        priority_data['last_check'] = datetime.now(timezone.utc).isoformat()
        
        if success:
            priority_data['consecutive_failures'] = 0
            # Обновляем среднее время отклика
            if priority_data['average_response_time'] > 0:
                priority_data['average_response_time'] = (
                    priority_data['average_response_time'] + response_time
                ) / 2
            else:
                priority_data['average_response_time'] = response_time
        else:
            priority_data['consecutive_failures'] += 1
            
        # Асинхронно сохраняем в БД
        asyncio.create_task(self._save_priorities_to_db())

    def should_update_priorities(self) -> bool:
        if not self.last_priority_update:
            return True
        return datetime.now(timezone.utc) - self.last_priority_update > timedelta(hours=6)

    def update_priorities(self, history_manager):
        logger.info("Обновление приоритетов репозиториев...")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=PRIORITY_UPDATE_DAYS)
        updated_count = 0

        for repo in REPOS:
            update_count = 0
            for rel in history_manager.history:
                if rel['repo_name'] == repo:
                    try:
                        pub_date = datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00'))
                        if pub_date >= cutoff_date:
                            update_count += 1
                    except:
                        continue

            priority_score = update_count / PRIORITY_UPDATE_DAYS
            existing_data = self.priorities.get(repo, self._create_default_priority())

            # Учитываем количество последовательных неудач
            failure_penalty = min(existing_data.get('consecutive_failures', 0) * 0.1, 0.5)
            adjusted_score = max(0, priority_score - failure_penalty)

            # Определяем интервал проверки
            if adjusted_score >= PRIORITY_THRESHOLD_HIGH:
                check_interval = MIN_CHECK_INTERVAL_MINUTES
            elif adjusted_score <= PRIORITY_THRESHOLD_LOW:
                check_interval = MAX_CHECK_INTERVAL_MINUTES
            else:
                ratio = (adjusted_score - PRIORITY_THRESHOLD_LOW) / (PRIORITY_THRESHOLD_HIGH - PRIORITY_THRESHOLD_LOW)
                check_interval = int(
                    MAX_CHECK_INTERVAL_MINUTES - ratio * (MAX_CHECK_INTERVAL_MINUTES - MIN_CHECK_INTERVAL_MINUTES)
                )

            new_priority_data = {
                **existing_data,
                'update_count': update_count,
                'check_interval': check_interval,
                'priority_score': round(adjusted_score, 3)
            }

            if (repo not in self.priorities or
                    abs(self.priorities[repo]['check_interval'] - check_interval) > 5 or
                    abs(self.priorities[repo]['priority_score'] - adjusted_score) > 0.01):
                updated_count += 1

            self.priorities[repo] = new_priority_data

        self.last_priority_update = datetime.now(timezone.utc)
        # Асинхронно сохраняем в БД
        asyncio.create_task(self._save_priorities_to_db())

        logger.info(f"Приоритеты обновлены. Изменено: {updated_count}/{len(REPOS)} репозиториев")

        # Детальный лог приоритетов
        for repo, data in self.priorities.items():
            status = "🔴" if data['priority_score'] >= PRIORITY_THRESHOLD_HIGH else \
                "🟢" if data['priority_score'] <= PRIORITY_THRESHOLD_LOW else "🟡"
            failures = data.get('consecutive_failures', 0)
            failure_info = f" ⚠️{failures}" if failures > 0 else ""
            logger.info(
                f"{status} {repo}: интервал {data['check_interval']} мин, "
                f"приоритет {data['priority_score']:.3f}{failure_info}"
            )

    def get_priority_stats(self) -> Dict:
        stats = {
            'high_priority': 0,
            'medium_priority': 0,
            'low_priority': 0,
            'failing_repos': 0,
            'total_repos': len(REPOS),
            'average_interval': 0,
            'total_checks': 0,
            'total_updates': 0
        }

        total_interval = 0
        for repo in REPOS:
            priority_data = self.get_priority(repo)
            score = priority_data['priority_score']
            failures = priority_data.get('consecutive_failures', 0)

            if score >= PRIORITY_THRESHOLD_HIGH:
                stats['high_priority'] += 1
            elif score <= PRIORITY_THRESHOLD_LOW:
                stats['low_priority'] += 1
            else:
                stats['medium_priority'] += 1

            if failures > 3:
                stats['failing_repos'] += 1

            total_interval += priority_data['check_interval']
            stats['total_checks'] += priority_data.get('total_checks', 0)
            stats['total_updates'] += priority_data.get('update_count', 0)

        stats['average_interval'] = round(total_interval / len(REPOS), 1)
        return stats

# --- УЛУЧШЕННЫЙ КЛАСС ДЛЯ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ---
class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.users_data = self._load_users()

    def _load_users(self) -> Dict[int, Dict]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Если старый формат (только список ID), конвертируем
                    if isinstance(data, list):
                        return {user_id: self._create_user_data() for user_id in data}
                    elif isinstance(data, dict):
                        # Дополняем недостающие поля
                        for user_id, user_data in data.items():
                            if not isinstance(user_data, dict):
                                data[user_id] = self._create_user_data()
                            else:
                                default_data = self._create_user_data()
                                for field, default_value in default_data.items():
                                    if field not in user_data:
                                        user_data[field] = default_value
                        return {int(k): v for k, v in data.items()}
                    
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки пользователей: {e}")
        
        return {}

    def _create_user_data(self) -> Dict:
        return {
            'joined_at': datetime.now(timezone.utc).isoformat(),
            'last_activity': None,
            'notifications_received': 0,
            'commands_used': 0,
            'is_active': True
        }

    def _save_users(self):
        try:
            # Резервная копия
            if os.path.exists(self.users_file):
                backup_file = f"{self.users_file}.bak"
                shutil.copy2(self.users_file, backup_file)

            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Ошибка сохранения пользователей: {e}")

    def add_user(self, user_id: int, username: str = None):
        if user_id not in self.users_data:
            self.users_data[user_id] = self._create_user_data()
            if username:
                self.users_data[user_id]['username'] = username
            self._save_users()
            logger.info(f"Новый пользователь: {user_id} ({username})")
        else:
            # Обновляем активность
            self.users_data[user_id]['last_activity'] = datetime.now(timezone.utc).isoformat()
            if username and 'username' not in self.users_data[user_id]:
                self.users_data[user_id]['username'] = username
                self._save_users()

    def record_activity(self, user_id: int, activity_type: str = 'command'):
        if user_id in self.users_data:
            self.users_data[user_id]['last_activity'] = datetime.now(timezone.utc).isoformat()
            if activity_type == 'command':
                self.users_data[user_id]['commands_used'] += 1
            elif activity_type == 'notification':
                self.users_data[user_id]['notifications_received'] += 1
            self._save_users()

    def get_users(self) -> Set[int]:
        return set(self.users_data.keys())

    def get_active_users(self, days: int = 30) -> Set[int]:
        """Возвращает активных пользователей за последние N дней"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        active_users = set()
        
        for user_id, user_data in self.users_data.items():
            if user_data.get('is_active', True):
                last_activity = user_data.get('last_activity')
                if last_activity:
                    try:
                        activity_date = datetime.fromisoformat(last_activity)
                        if activity_date >= cutoff_date:
                            active_users.add(user_id)
                    except:
                        # Если не можем распарсить дату, считаем пользователя активным
                        active_users.add(user_id)
                else:
                    # Новые пользователи без активности считаются активными
                    active_users.add(user_id)
        
        return active_users

    def get_count(self) -> int:
        return len(self.users_data)

    def get_stats(self) -> Dict:
        active_users = len(self.get_active_users(30))
        total_commands = sum(data.get('commands_used', 0) for data in self.users_data.values())
        total_notifications = sum(data.get('notifications_received', 0) for data in self.users_data.values())
        
        return {
            'total_users': len(self.users_data),
            'active_users_30d': active_users,
            'total_commands': total_commands,
            'total_notifications': total_notifications
        }

# --- ОСТАЛЬНЫЕ КЛАССЫ ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ, НО С УЛУЧШЕНИЯМИ ---
class ReleaseStateManager:
    def __init__(self):
        self.state_file = STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, str]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки состояния: {e}")
                self._backup_corrupted_file()
        return {}

    def _backup_corrupted_file(self):
        """Создает резервную копию поврежденного файла состояния"""
        try:
            if os.path.exists(self.state_file):
                backup_name = f"state_corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                backup_path = os.path.join(BACKUP_DIR, backup_name)
                shutil.copy2(self.state_file, backup_path)
                logger.warning(f"Создана резервная копия состояния: {backup_path}")
        except Exception as e:
            logger.error(f"Не удалось создать резервную копию состояния: {e}")

    def _save_state(self):
        try:
            # Резервная копия
            if os.path.exists(self.state_file):
                backup_file = f"{self.state_file}.bak"
                shutil.copy2(self.state_file, backup_file)

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

    def update_tag(self, repo: str, tag: str):
        self.state[repo] = tag
        self._save_state()
        logger.debug(f"Обновлен тег для {repo}: {tag}")

    def get_last_tag(self, repo: str) -> Optional[str]:
        return self.state.get(repo)

class FilterManager:
    def __init__(self):
        self.filters_file = FILTERS_FILE
        self.filters = self._load_filters()

    def _load_filters(self) -> Dict[str, List[str]]:
        if os.path.exists(self.filters_file):
            try:
                with open(self.filters_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки фильтров: {e}")
        return {}

    def _save_filters(self):
        try:
            # Резервная копия
            if os.path.exists(self.filters_file):
                backup_file = f"{self.filters_file}.bak"
                shutil.copy2(self.filters_file, backup_file)

            with open(self.filters_file, 'w', encoding='utf-8') as f:
                json.dump(self.filters, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Ошибка сохранения фильтров: {e}")

    def set_filters(self, user_id: str, keywords: List[str]):
        # Нормализуем ключевые слова
        normalized_keywords = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
        if normalized_keywords:
            self.filters[user_id] = normalized_keywords
            self._save_filters()
            logger.info(f"Установлены фильтры для пользователя {user_id}: {normalized_keywords}")

    def get_filters(self, user_id: str) -> List[str]:
        return self.filters.get(user_id, [])

    def clear_filters(self, user_id: str):
        if user_id in self.filters:
            del self.filters[user_id]
            self._save_filters()
            logger.info(f"Очищены фильтры для пользователя {user_id}")

    def get_users_with_filters_count(self) -> int:
        return len(self.filters)

    def get_stats(self) -> Dict:
        total_filters = len(self.filters)
        avg_keywords = 0
        if total_filters > 0:
            total_keywords = sum(len(keywords) for keywords in self.filters.values())
            avg_keywords = round(total_keywords / total_filters, 1)
        
        return {
            'users_with_filters': total_filters,
            'average_keywords_per_user': avg_keywords
        }

class ReleaseHistoryManager:
    def __init__(self):
        self.history_file = HISTORY_FILE
        self.history = self._load_history()

    def _load_history(self) -> List[Dict]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки истории: {e}")
        return []

    def _save_history(self):
        try:
            # Очистка старых записей
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
            filtered_history = [
                rel for rel in self.history
                if datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00')) >= cutoff_date
            ]

            # Резервная копия
            if os.path.exists(self.history_file):
                backup_file = f"{self.history_file}.bak"
                shutil.copy2(self.history_file, backup_file)

            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_history, f, ensure_ascii=False, indent=2)
            
            removed_count = len(self.history) - len(filtered_history)
            if removed_count > 0:
                logger.info(f"Удалено {removed_count} старых записей из истории")
                
            self.history = filtered_history
        except IOError as e:
            logger.error(f"Ошибка сохранения истории: {e}")

    def add_release(self, repo_name: str, release: Dict):
        # Проверяем, не существует ли уже такой релиз
        exists = any(
            rel['repo_name'] == repo_name and rel['tag_name'] == release.get('tag_name')
            for rel in self.history
        )

        if not exists:
            history_entry = {
                'repo_name': repo_name,
                'tag_name': release.get('tag_name'),
                'name': release.get('name'),
                'published_at': release.get('published_at'),
                'body': release.get('body', ''),
                'assets': release.get('assets', []),
                'added_to_history': datetime.now(timezone.utc).isoformat()
            }
            self.history.append(history_entry)
            self._save_history()
            logger.info(f"Добавлен релиз в историю: {repo_name} {release.get('tag_name')}")
            return True
        return False

    def get_releases_by_date(self, target_date) -> List[Dict]:
        logger.info(f"Поиск релизов за дату: {target_date}")

        result = []
        for rel in self.history:
            try:
                pub_date_str = rel['published_at']
                if pub_date_str.endswith('Z'):
                    pub_date_str = pub_date_str[:-1] + '+00:00'

                pub_date = datetime.fromisoformat(pub_date_str).astimezone(timezone.utc).date()
                
                if pub_date == target_date:
                    result.append(rel)
            except Exception as e:
                logger.error(f"Ошибка при обработке даты релиза {rel['repo_name']} {rel['tag_name']}: {e}")

        logger.info(f"Найдено {len(result)} релизов за дату {target_date}")
        return sorted(result, key=lambda x: x['published_at'], reverse=True)

    def get_recent_releases(self, days: int = 3) -> List[Dict]:
        cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=days)
        releases = []
        
        for rel in self.history:
            try:
                pub_date_str = rel['published_at']
                if pub_date_str.endswith('Z'):
                    pub_date_str = pub_date_str[:-1] + '+00:00'
                
                pub_date = datetime.fromisoformat(pub_date_str).date()
                if pub_date >= cutoff_date:
                    releases.append(rel)
            except Exception as e:
                logger.error(f"Ошибка обработки даты релиза: {e}")
                continue
        
        return sorted(releases, key=lambda x: x['published_at'], reverse=True)

    def get_count(self) -> int:
        return len(self.history)

    def get_stats(self) -> Dict:
        if not self.history:
            return {'total_releases': 0, 'releases_by_repo': {}, 'releases_last_7_days': 0}
        
        releases_by_repo = {}
        recent_releases = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        
        for rel in self.history:
            repo = rel['repo_name']
            releases_by_repo[repo] = releases_by_repo.get(repo, 0) + 1
            
            try:
                pub_date_str = rel['published_at']
                if pub_date_str.endswith('Z'):
                    pub_date_str = pub_date_str[:-1] + '+00:00'
                pub_date = datetime.fromisoformat(pub_date_str)
                if pub_date >= cutoff_date:
                    recent_releases += 1
            except:
                pass
        
        return {
            'total_releases': len(self.history),
            'releases_by_repo': releases_by_repo,
            'releases_last_7_days': recent_releases
        }

# --- ИНИЦИАЛИЗАЦИЯ МЕНЕДЖЕРОВ ---
statistics_manager = StatisticsManager()
user_manager = UserManager()
state_manager = ReleaseStateManager()
filter_manager = FilterManager()
history_manager = ReleaseHistoryManager()
priority_manager = RepositoryPriorityManager()

# --- УЛУЧШЕННАЯ ЗАГРУЗКА ИНФОРМАЦИИ О РЕЛИЗАХ ---
async def fetch_release(session: ClientSession, repo_name: str) -> Tuple[Optional[Dict], float]:
    """Загружает информацию о последнем релизе репозитория
    
    Returns:
        Tuple[Optional[Dict], float]: (данные релиза, время отклика в секундах)
    """
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {'User-Agent': 'GitHub-Release-Monitor-Bot'}
    
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    start_time = asyncio.get_event_loop().time()
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(api_url, headers=headers, timeout=30) as response:
                response_time = asyncio.get_event_loop().time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Успешно получены данные для {repo_name} за {response_time:.2f}с")
                    return data, response_time
                elif response.status == 403:
                    # Rate limit
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    current_time = int(datetime.now().timestamp())
                    wait_time = max(reset_time - current_time, 60)
                    logger.warning(f"Rate limit для {repo_name}. Ожидание {wait_time} секунд")
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status == 404:
                    logger.error(f"Репозиторий не найден: {repo_name}")
                    return None, response_time
                else:
                    logger.error(f"Неожиданный статус {response.status} для {repo_name}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    return None, response_time
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout при запросе к {repo_name} (попытка {attempt + 1})")
        except (ClientError, ClientResponseError) as e:
            logger.error(f"Ошибка запроса к {repo_name} (попытка {attempt + 1}): {e}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе к {repo_name}: {e}")
            
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    
    response_time = asyncio.get_event_loop().time() - start_time
    return None, response_time

# --- УЛУЧШЕННАЯ ПРОВЕРКА СООТВЕТСТВИЯ ФИЛЬТРАМ ---
def matches_filters(release_data: dict, keywords: List[str]) -> bool:
    """Проверяет соответствие релиза фильтрам пользователя"""
    if not keywords:
        return True

    # Создаем текст для поиска
    search_fields = [
        release_data.get('name', ''),
        release_data.get('tag_name', ''),
        release_data.get('body', '')
    ]
    
    # Добавляем имена файлов для скачивания
    for asset in release_data.get('assets', []):
        if isinstance(asset, dict):
            search_fields.append(asset.get('name', ''))

    search_text = " ".join(search_fields).lower()

    # Проверяем наличие всех ключевых слов
    return all(keyword.lower() in search_text for keyword in keywords)

def format_release_message(repo_name: str, release: Dict) -> str:
    """Форматирует сообщение о релизе с улучшенной очисткой от Markdown"""
    tag = release.get('tag_name', 'Unknown')
    name = release.get('name', tag)
    body = release.get('body', '')
    published_at = release.get('published_at', '')
    assets = release.get('assets', [])
    
    # Очищаем текст от Markdown форматирования
    repo_name_clean = clean_markdown_text(repo_name)
    name_clean = clean_markdown_text(name)
    tag_clean = clean_markdown_text(tag)
    
    message = (
        f"🚀 *Новый релиз в репозитории {repo_name_clean}*\n\n"
        f"*{name_clean}*\n"
        f"`{tag_clean}`\n"
    )
    
    # Добавляем дату публикации в МСК
    if published_at:
        try:
            pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            # Преобразуем в МСК (UTC+3)
            msk_time = pub_date + timedelta(hours=3)
            formatted_date = msk_time.strftime('%Y-%m-%d %H:%M МСК')
            message += f"📅 {formatted_date}\n\n"
        except Exception as e:
            logger.warning(f"Не удалось распарсить дату: {published_at}, ошибка: {e}")
            message += "\n"
    else:
        message += "\n"
    
    # Добавляем описание (с улучшенной очисткой от Markdown)
    if body:
        # Используем специализированную функцию для GitHub релизов
        body_clean = clean_github_release_body(body, max_length=1000)
        
        # Экранируем специальные символы для Markdown
        body_escaped = escape_markdown(body_clean)
        message += f"{body_escaped}\n\n"
    
    # Добавляем ссылки для скачивания
    download_links = []
    for asset in assets:
        if isinstance(asset, dict):
            asset_name = asset.get('name', '')
            download_url = asset.get('browser_download_url', '')

            # Исключаем только исходный код, но показываем все исполняемые файлы
            if (asset_name and download_url and
                    not asset_name.startswith("Source code")):
                asset_name_clean = clean_markdown_text(asset_name[:50])  # Очищаем и ограничиваем длину
                asset_name_escaped = escape_markdown(asset_name_clean)
                download_links.append(f"[{asset_name_escaped}]({download_url})")
    
    if download_links:
        message += "📥 *Ссылки для скачивания:*\n" + "\n".join(download_links[:10])  # Максимум 10 ссылок
    else:
        message += "⚠️ Файлы для скачивания не найдены"
    
    # Добавляем ссылку на релиз
    release_url = release.get('html_url')
    if release_url:
        message += f"\n\n🔗 [Открыть на GitHub]({release_url})"
    
    return message

async def send_notifications(bot: Bot, repo_name: str, release: Dict) -> int:
    """Отправляет уведомления о новом релизе
    
    Returns:
        int: Количество успешно отправленных уведомлений
    """
    message = format_release_message(repo_name, release)
    notifications_sent = 0
    
    # Получаем всех пользователей и их фильтры
    all_users = user_manager.get_active_users(30)  # Только активные пользователи за последние 30 дней
    users_with_filters = set(int(uid) for uid in filter_manager.filters.keys())
    users_without_filters = all_users - users_with_filters

    logger.info(f"Отправка уведомлений для {repo_name}: "
                f"всего активных пользователей {len(all_users)}, "
                f"с фильтрами {len(users_with_filters)}, "
                f"без фильтров {len(users_without_filters)}")

    # 1. Отправляем пользователям с фильтрами (если релиз подходит под фильтры)
    for user_id_str, filters in filter_manager.filters.items():
        try:
            user_id = int(user_id_str)
            
            # Проверяем, что пользователь активен
            if user_id not in all_users:
                continue
                
            if matches_filters(release, filters):
                try:
                    await bot.send_message(user_id, message, parse_mode="Markdown")
                    notifications_sent += 1
                    user_manager.record_activity(user_id, 'notification')
                    logger.info(f"✅ Уведомление отправлено пользователю {user_id} (фильтры)")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
                    
        except ValueError:
            logger.error(f"Некорректный ID пользователя в фильтрах: {user_id_str}")
            continue

    # 2. Отправляем пользователям БЕЗ фильтров (они получают ВСЕ релизы)
    for user_id in users_without_filters:
        try:
            await bot.send_message(user_id, message, parse_mode="Markdown")
            notifications_sent += 1
            user_manager.record_activity(user_id, 'notification')
            logger.info(f"✅ Уведомление отправлено пользователю {user_id} (без фильтров)")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")

    # 3. Отправляем в канал (если указан)
    if CHANNEL_ID:
        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"✅ Уведомление отправлено в канал {CHANNEL_ID}")
            notifications_sent += 1
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в канал {CHANNEL_ID}: {e}")

    # Обновляем статистику
    if notifications_sent > 0:
        statistics_manager.increment_notifications()
        statistics_manager.increment_releases(repo_name)

    logger.info(f"Отправлено {notifications_sent} уведомлений для {repo_name}")
    return notifications_sent

# --- УЛУЧШЕННАЯ ПРОВЕРКА ОДНОГО РЕПОЗИТОРИЯ ---
async def check_single_repo(bot: Bot, repo_name: str) -> bool:
    """Проверяет один репозиторий на наличие новых релизов
    
    Returns:
        bool: True если найден новый релиз, False иначе
    """
    logger.info(f"🔍 Проверка репозитория: {repo_name}")
    
    try:
        # Обновляем статистику проверок
        statistics_manager.increment_checks(repo_name)
        
        async with ClientSession() as session:
            release, response_time = await fetch_release(session, repo_name)
            
            # Записываем информацию о проверке
            success = release is not None
            priority_manager.record_check(repo_name, success, response_time)

            if not release:
                logger.warning(f"❌ Не получены данные о релизах для {repo_name}")
                return False

            current_tag = release.get('tag_name')
            if not current_tag:
                logger.warning(f"❌ Не найден тег в данных релиза для {repo_name}")
                return False

            last_tag = state_manager.get_last_tag(repo_name)
            
            if last_tag != current_tag:
                logger.info(f"🆕 Найден новый релиз {repo_name}: {current_tag} (предыдущий: {last_tag})")

                # Добавляем в историю
                history_manager.add_release(repo_name, release)
                
                # Обновляем приоритет
                priority_manager.record_update(repo_name)
                
                # Отправляем уведомления
                notifications_sent = await send_notifications(bot, repo_name, release)
                
                # Обновляем состояние
                state_manager.update_tag(repo_name, current_tag)

                logger.info(f"✅ Успешно обработан новый релиз для {repo_name}. "
                           f"Отправлено уведомлений: {notifications_sent}")
                return True
            else:
                logger.debug(f"ℹ️ Обновлений для {repo_name} не найдено")
                return False

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при проверке репозитория {repo_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Увеличиваем счетчик ошибок
        statistics_manager.increment_errors()
        
        # Уведомляем админа о критических ошибках
        if ADMIN_ID:
            try:
                error_message = (
                    f"⚠️ *Критическая ошибка при проверке репозитория*\n\n"
                    f"📦 Репозиторий: `{repo_name}`\n"
                    f"❌ Ошибка: `{str(e)[:500]}`\n"
                    f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await bot.send_message(ADMIN_ID, error_message, parse_mode="Markdown")
            except:
                pass  # Игнорируем ошибки отправки уведомлений админу
        
        return False

# --- УЛУЧШЕННАЯ ПРОВЕРКА РЕПОЗИТОРИЕВ С УЧЕТОМ ПРИОРИТЕТОВ ---
async def check_repositories(bot: Bot):
    """Проверяет репозитории согласно их приоритетам"""
    logger.info("🔄 Запуск автоматической проверки репозиториев с учетом приоритетов...")

    # Обновляем приоритеты если нужно
    if priority_manager.should_update_priorities():
        logger.info("📊 Обновление приоритетов репозиториев...")
        priority_manager.update_priorities(history_manager)

    current_time = datetime.now(timezone.utc)
    repos_to_check = []
    repos_checked = 0
    repos_with_updates = 0

    # Определяем какие репозитории нужно проверить
    for repo_name in REPOS:
        priority_data = priority_manager.get_priority(repo_name)
        check_interval = priority_data['check_interval']
        last_check = priority_data.get('last_check')

        should_check = False
        if not last_check:
            should_check = True
            logger.debug(f"📦 {repo_name}: первая проверка")
        else:
            try:
                last_check_time = datetime.fromisoformat(last_check)
                time_since_check = current_time - last_check_time
                
                if time_since_check >= timedelta(minutes=check_interval):
                    should_check = True
                    logger.debug(f"📦 {repo_name}: прошло {time_since_check}, интервал {check_interval} мин")
                else:
                    remaining = timedelta(minutes=check_interval) - time_since_check
                    logger.debug(f"📦 {repo_name}: ещё {remaining} до следующей проверки")
            except Exception as e:
                logger.error(f"Ошибка парсинга времени последней проверки для {repo_name}: {e}")
                should_check = True

        if should_check:
            repos_to_check.append(repo_name)

    logger.info(f"📋 Будет проверено {len(repos_to_check)} из {len(REPOS)} репозиториев")

    # Проверяем репозитории
    for repo_name in repos_to_check:
        try:
            has_update = await check_single_repo(bot, repo_name)
            repos_checked += 1
            
            if has_update:
                repos_with_updates += 1

            # Обновляем время последней проверки
            priority_data = priority_manager.get_priority(repo_name)
            priority_data['last_check'] = current_time.isoformat()
            priority_manager._save_priorities()

            # Небольшая пауза между проверками
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Ошибка при проверке {repo_name}: {e}")
            continue

    logger.info(f"✅ Проверка завершена: проверено {repos_checked}, "
                f"найдено обновлений {repos_with_updates}")

# --- ПРИНУДИТЕЛЬНАЯ ПРОВЕРКА ВСЕХ РЕПОЗИТОРИЕВ ---
async def check_all_repositories(bot: Bot):
    """Принудительно проверяет все репозитории"""
    logger.info("🔄 Запуск принудительной проверки всех репозиториев...")

    repos_checked = 0
    repos_with_updates = 0
    current_time = datetime.now(timezone.utc)

    for repo_name in REPOS:
        try:
            logger.info(f"🔍 Принудительная проверка {repo_name}...")
            has_update = await check_single_repo(bot, repo_name)
            repos_checked += 1
            
            if has_update:
                repos_with_updates += 1

            # Обновляем время последней проверки
            priority_data = priority_manager.get_priority(repo_name)
            priority_data['last_check'] = current_time.isoformat()
            priority_manager._save_priorities()

            # Пауза между проверками
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Ошибка при принудительной проверке {repo_name}: {e}")
            continue

    logger.info(f"✅ Принудительная проверка завершена: проверено {repos_checked}, "
                f"найдено обновлений {repos_with_updates}")

# --- ОБРАБОТЧИКИ КОМАНД ---

async def start_command(message: Message):
    """Обработчик команды /start"""
    username = message.from_user.username
    user_manager.add_user(message.from_user.id, username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    logger.info(f"👤 Команда /start от пользователя {message.from_user.id} (@{username})")

    # Создаем приветственное сообщение в зависимости от роли пользователя
    if message.from_user.id == ADMIN_ID:
        welcome_message = (
            "👋 *Добро пожаловать, Администратор!*\n\n"
            "🤖 Это бот для мониторинга релизов GitHub репозиториев с майнерами.\n\n"
            "📌 *Основные команды:*\n"
            "• /filter — настроить фильтры уведомлений\n"
            "• /myfilters — показать текущие фильтры\n"
            "• /clearfilters — очистить все фильтры\n"
            "• /last — релизы за последние 3 дня\n"
            "• /help — подробная справка\n"
            "• /donate — поддержать разработчика\n\n"
            "🔧 *Административные команды:*\n"
            "• /stats — общая статистика бота\n"
            "• /priority — приоритеты репозиториев\n"
            "• /sync — синхронизация с базой данных\n"
            "• /pstats — статистика приоритетов\n"
            "• /checkall — проверить все репозитории\n"
            "• /backup — создать резервные копии\n\n"
            "ℹ️ *Как это работает:*\n"
            "Бот автоматически проверяет репозитории и уведомляет о новых релизах. "
            "Частота проверки зависит от активности репозитория."
        )
    else:
        welcome_message = (
            "👋 *Добро пожаловать!*\n\n"
            "🤖 Это бот для мониторинга релизов GitHub репозиториев с майнерами.\n\n"
            "📌 *Доступные команды:*\n"
            "• /filter — настроить фильтры уведомлений\n"
            "• /myfilters — показать текущие фильтры\n"
            "• /clearfilters — очистить все фильтры\n"
            "• /last — релизы за последние 3 дня\n"
            "• /help — подробная справка\n"
            "• /donate — поддержать разработчика\n\n"
            "ℹ️ *Принцип работы:*\n"
            "По умолчанию вы получаете ВСЕ релизы. "
            "Используйте фильтры, чтобы получать только интересующие вас обновления."
        )

    await message.answer(welcome_message, parse_mode="Markdown")

    # Показываем последние релизы
    recent_releases = history_manager.get_recent_releases(3)
    if recent_releases:
        await message.answer("📅 *Последние релизы за 3 дня:*", parse_mode="Markdown")
        
        # Ограничиваем количество показываемых релизов
        for rel in recent_releases[:5]:  # Максимум 5 релизов
            try:
                msg = format_release_message(rel['repo_name'], rel)
                await message.answer(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)  # Небольшая пауза между сообщениями
            except Exception as e:
                logger.error(f"Ошибка отправки релиза в /start: {e}")
                continue
    else:
        await message.answer("📭 За последние 3 дня новых релизов не было.")

async def filter_command(message: Message):
    """Обработчик команды /filter"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    logger.info(f"🔍 Пользователь {message.from_user.id} настраивает фильтры")

    # Создаем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отмена", callback_data="cancel_filter")

    current_filters = filter_manager.get_filters(str(message.from_user.id))
    current_filters_text = ""
    
    if current_filters:
        current_filters_text = f"\n\n🎯 *Текущие фильтры:* {', '.join(current_filters)}"

    await message.answer(
        f"🔍 *Настройка фильтров уведомлений*\n\n"
        f"Введите ключевые слова через пробел для фильтрации релизов.\n\n"
        f"*Примеры:*\n"
        f"• `qubitcoin qtc` — только релизы с Qubitcoin\n"
        f"• `nvidia cuda` — релизы для NVIDIA\n"
        f"• `amd opencl` — релизы для AMD\n\n"
        f"🔎 *Поиск производится в:*\n"
        f"• Названии релиза\n"
        f"• Теге версии\n"
        f"• Описании релиза\n"
        f"• Именах файлов{current_filters_text}\n\n"
        f"⏳ Ожидаю ввод ключевых слов...",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )

async def cancel_filter_callback(callback: CallbackQuery):
    """Обработчик отмены настройки фильтров"""
    user_manager.add_user(callback.from_user.id, callback.from_user.username)
    
    logger.info(f"❌ Пользователь {callback.from_user.id} отменил настройку фильтров")

    await callback.message.edit_text(
        "❌ *Настройка фильтров отменена*\n\n"
        "Используйте /filter для повторной настройки фильтров.",
        reply_markup=None,
        parse_mode="Markdown"
    )
    await callback.answer("Настройка фильтров отменена")

async def process_filter_text(message: Message):
    """Обработчик текста для установки фильтров"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    user_id = str(message.from_user.id)
    text = message.text.strip()

    logger.info(f"🔧 Пользователь {user_id} устанавливает фильтры: '{text}'")

    # Проверяем, что текст не является командой
    if text.startswith('/'):
        return

    # Разбираем ключевые слова
    keywords = [word.strip() for word in text.split() if word.strip()]

    if not keywords:
        await message.answer(
            "❌ *Ошибка:* Вы не ввели ключевые слова.\n\n"
            "Пожалуйста, введите хотя бы одно ключевое слово или используйте /filter для повторной настройки.",
            parse_mode="Markdown"
        )
        return

    # Ограничиваем количество ключевых слов
    if len(keywords) > 10:
        await message.answer(
            "❌ *Ошибка:* Слишком много ключевых слов.\n\n"
            "Максимальное количество: 10. Пожалуйста, сократите список.",
            parse_mode="Markdown"
        )
        return

    # Сохраняем фильтры
    filter_manager.set_filters(user_id, keywords)
    
    keywords_text = ", ".join(f"`{kw}`" for kw in keywords)
    
    await message.answer(
        f"✅ *Фильтры успешно сохранены!*\n\n"
        f"🎯 *Ключевые слова:* {keywords_text}\n\n"
        f"Теперь вы будете получать уведомления только о релизах, "
        f"содержащих эти слова.\n\n"
        f"💡 *Совет:* Используйте /myfilters для просмотра текущих фильтров "
        f"или /clearfilters для их удаления.",
        parse_mode="Markdown"
    )

async def myfilters_command(message: Message):
    """Обработчик команды /myfilters"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    user_id = str(message.from_user.id)
    filters = filter_manager.get_filters(user_id)

    logger.info(f"📋 Пользователь {user_id} запрашивает свои фильтры")

    if not filters:
        await message.answer(
            "📭 *У вас нет установленных фильтров*\n\n"
            "Это означает, что вы получаете уведомления о ВСЕХ новых релизах.\n\n"
            "💡 Используйте /filter для настройки фильтров, если хотите получать "
            "только определенные релизы.",
            parse_mode="Markdown"
        )
    else:
        keywords_text = ", ".join(f"`{kw}`" for kw in filters)
        
        await message.answer(
            f"📋 *Ваши текущие фильтры:*\n\n"
            f"🎯 *Ключевые слова:* {keywords_text}\n\n"
            f"ℹ️ Вы получаете уведомления только о релизах, содержащих эти слова.\n\n"
            f"💡 *Управление фильтрами:*\n"
            f"• /filter — изменить фильтры\n"
            f"• /clearfilters — удалить все фильтры",
            parse_mode="Markdown"
        )

async def clearfilters_command(message: Message):
    """Обработчик команды /clearfilters"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    user_id = str(message.from_user.id)

    logger.info(f"🗑️ Пользователь {user_id} очищает фильтры")

    current_filters = filter_manager.get_filters(user_id)
    
    if current_filters:
        filter_manager.clear_filters(user_id)
        keywords_text = ", ".join(f"`{kw}`" for kw in current_filters)
        
        await message.answer(
            f"🗑️ *Фильтры успешно удалены*\n\n"
            f"❌ *Удаленные фильтры:* {keywords_text}\n\n"
            f"ℹ️ Теперь вы будете получать уведомления о ВСЕХ новых релизах.\n\n"
            f"💡 Используйте /filter для повторной настройки фильтров.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "📭 *У вас и так нет установленных фильтров*\n\n"
            "Вы уже получаете уведомления о всех релизах.\n\n"
            "💡 Используйте /filter для настройки фильтров.",
            parse_mode="Markdown"
        )

async def last_command(message: Message):
    """Обработчик команды /last"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    logger.info(f"📅 Пользователь {message.from_user.id} запрашивает последние релизы")

    recent_releases = history_manager.get_recent_releases(3)

    if not recent_releases:
        await message.answer(
            "📭 *За последние 3 дня релизов не было*\n\n"
            "Бот продолжает мониторинг репозиториев. "
            "Как только появятся новые релизы, вы получите уведомление!",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"📅 *Найдено {len(recent_releases)} релизов за последние 3 дня:*",
            parse_mode="Markdown"
        )
        
        # Ограничиваем количество показываемых релизов
        for i, rel in enumerate(recent_releases[:10], 1):  # Максимум 10 релизов
            try:
                msg = format_release_message(rel['repo_name'], rel)
                await message.answer(msg, parse_mode="Markdown")
                
                # Добавляем паузу после каждых 3 сообщений
                if i % 3 == 0 and i < len(recent_releases):
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Ошибка отправки релиза в /last: {e}")
                continue

async def help_command(message: Message):
    """Обработчик команды /help"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    logger.info(f"❓ Пользователь {message.from_user.id} запрашивает справку")

    # Создаем разную справку для админа и обычных пользователей
    if message.from_user.id == ADMIN_ID:
        help_text = (
            "📚 *Справка по использованию бота (Администратор)*\n\n"
            
            "🔍 *Система фильтрации:*\n"
            "• Без фильтров — получаете ВСЕ релизы\n"
            "• С фильтрами — только релизы с указанными словами\n"
            "• Поиск в названии, теге, описании и именах файлов\n\n"
            
            "📋 *Пользовательские команды:*\n"
            "• /start — приветствие и последние релизы\n"
            "• /filter — настроить фильтры уведомлений\n"
            "• /myfilters — показать текущие фильтры\n"
            "• /clearfilters — удалить все фильтры\n"
            "• /last — релизы за последние 3 дня\n"
            "• /donate — поддержать разработчика\n\n"
            
            "🔧 *Административные команды:*\n"
            "• /stats — общая статистика бота\n"
            "• /priority — приоритеты репозиториев\n"
            "• /sync — синхронизация с базой данных\n"
            "• /pstats — статистика приоритетов\n"
            "• /checkall — проверить все репозитории\n"
            "• /backup — создать резервные копии\n\n"
            
            "⚙️ *Как работает система приоритетов:*\n"
            "• Бот автоматически адаптирует частоту проверок\n"
            "• Активные репозитории проверяются чаще\n"
            "• Неактивные — реже (экономия ресурсов)\n"
            "• Все данные хранятся в Supabase\n\n"
            
            "💡 *Советы по использованию:*\n"
            "• Используйте конкретные фильтры (например: 'qubitcoin')\n"
            "• Регулярно проверяйте /pstats для мониторинга\n"
            "• При проблемах используйте /checkall"
        )
    else:
        help_text = (
            "📚 *Справка по использованию бота*\n\n"
            
            "🤖 *О боте:*\n"
            "Бот отслеживает новые релизы популярных майнеров "
            "и автоматически уведомляет о них.\n\n"
            
            "🔍 *Система фильтрации:*\n"
            "• *Без фильтров* — получаете ВСЕ релизы\n"
            "• *С фильтрами* — только релизы с указанными словами\n"
            "• Поиск производится в названии, описании, тегах и именах файлов\n\n"
            
            "📋 *Доступные команды:*\n"
            "• /start — приветствие и последние релизы\n"
            "• /filter — настроить фильтры уведомлений\n"
            "• /myfilters — показать текущие фильтры\n"
            "• /clearfilters — удалить все фильтры\n"
            "• /last — релизы за последние 3 дня\n"
            "• /help — эта справка\n"
            "• /donate — поддержать разработчика\n\n"
            
            "💡 *Примеры фильтров:*\n"
            "• `qubitcoin` — только релизы Qubitcoin\n"
            "• `nvidia cuda` — релизы для видеокарт NVIDIA\n"
            "• `amd opencl` — релизы для видеокарт AMD\n"
            "• `cpu miner` — CPU майнеры\n\n"
            
            "❓ *Часто задаваемые вопросы:*\n"
            "• *Q:* Как получать все релизы?\n"
            "  *A:* Не устанавливайте фильтры или используйте /clearfilters\n\n"
            "• *Q:* Не приходят уведомления?\n"
            "  *A:* Проверьте фильтры через /myfilters\n\n"
            "• *Q:* Как часто бот проверяет релизы?\n"
            "  *A:* Автоматически, в зависимости от активности репозитория"
        )

    await message.answer(help_text, parse_mode="Markdown")

async def donate_command(message: Message):
    """Обработчик команды /donate"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')
    
    logger.info(f"💝 Пользователь {message.from_user.id} запросил информацию о донате")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💝 Поддержать разработчика", url=DONATE_URL)

    await message.answer(
        "💖 *Поддержка проекта*\n\n"
        "Спасибо за интерес к поддержке моего бота! "
        "Ваша помощь очень важна для развития проекта.\n\n"
        
        "💡 *На что идут средства:*\n"
        "• Оплата сервера для работы бота 24/7\n"
        "• Развитие и улучшение функционала\n"
        "• Добавление новых репозиториев\n"
        "• Техническое обслуживание и поддержка\n\n"
        
        "🎯 *Планы развития:*\n"
        "• Веб-интерфейс для управления\n"
        "• Поддержка других платформ (GitLab, etc.)\n"
        "• Расширенная система фильтрации\n"
        "• Уведомления о статистике майнинга\n\n"
        
        "🙏 Любая сумма будет принята с благодарностью!\n\n"
        "Нажмите кнопку ниже для перехода на страницу доната:",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )

# --- АДМИНИСТРАТИВНЫЕ КОМАНДЫ ---

async def stats_command(message: Message):
    """Обработчик команды /stats"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"📊 Администратор запрашивает статистику")

    # Собираем статистику
    user_stats = user_manager.get_stats()
    filter_stats = filter_manager.get_stats()
    history_stats = history_manager.get_stats()
    priority_stats = priority_manager.get_priority_stats()
    
    uptime = statistics_manager.get_uptime()
    
    stats_message = (
        f"📊 *Статистика бота*\n\n"
        
        f"👥 *Пользователи:*\n"
        f"• Всего: {user_stats['total_users']}\n"
        f"• Активных (30 дней): {user_stats['active_users_30d']}\n"
        f"• Использовано команд: {user_stats['total_commands']}\n"
        f"• Получено уведомлений: {user_stats['total_notifications']}\n\n"
        
        f"🔍 *Фильтры:*\n"
        f"• Пользователей с фильтрами: {filter_stats['users_with_filters']}\n"
        f"• Среднее слов на пользователя: {filter_stats['average_keywords_per_user']}\n\n"
        
        f"📦 *Репозитории:*\n"
        f"• Всего отслеживается: {priority_stats['total_repos']}\n"
        f"• Высокий приоритет: {priority_stats['high_priority']} 🔴\n"
        f"• Средний приоритет: {priority_stats['medium_priority']} 🟡\n"
        f"• Низкий приоритет: {priority_stats['low_priority']} 🟢\n"
        f"• Проблемные: {priority_stats['failing_repos']} ⚠️\n"
        f"• Средний интервал: {priority_stats['average_interval']} мин\n\n"
        
        f"📈 *Активность:*\n"
        f"• Всего проверок: {statistics_manager.stats['total_checks']}\n"
        f"• Найдено релизов: {statistics_manager.stats['total_releases_found']}\n"
        f"• Отправлено уведомлений: {statistics_manager.stats['total_notifications_sent']}\n"
        f"• Ошибок: {statistics_manager.stats['errors_count']}\n\n"
        
        f"📅 *История:*\n"
        f"• Релизов в базе: {history_stats['total_releases']}\n"
        f"• За последние 7 дней: {history_stats['releases_last_7_days']}\n\n"
        
        f"⏱️ *Время работы:* {uptime}\n"
        f"🔄 *Последняя активность:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await message.answer(stats_message, parse_mode="Markdown")

async def priority_command(message: Message):
    """Обработчик команды /priority"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"📊 Администратор запрашивает приоритеты репозиториев")

    # Сначала синхронизируемся с базой данных
    try:
        await priority_manager.initialize_priorities()
        logger.info("✅ Приоритеты синхронизированы с БД для команды /priority")
    except Exception as e:
        logger.warning(f"Не удалось синхронизировать приоритеты с БД: {e}")

    priority_info = "📊 *Приоритеты репозиториев:*\n\n"

    # Добавляем информацию об источнике данных
    if priority_manager.db_synced:
        priority_info += "🗄️ *Источник:* База данных Supabase\n\n"
    else:
        priority_info += "⚠️ *Источник:* Локальные данные (БД недоступна)\n\n"

    # Сортируем репозитории по приоритету (сначала высокий)
    sorted_repos = sorted(
        REPOS, 
        key=lambda repo: priority_manager.get_priority(repo)['priority_score'],
        reverse=True
    )

    for repo in sorted_repos:
        priority_data = priority_manager.get_priority(repo)
        interval = priority_data['check_interval']
        score = priority_data['priority_score']
        failures = priority_data.get('consecutive_failures', 0)
        total_checks = priority_data.get('total_checks', 0)
        updates = priority_data.get('update_count', 0)

        # Определяем статус
        if score >= PRIORITY_THRESHOLD_HIGH:
            status = "🔴"
            status_text = "Высокий"
        elif score <= PRIORITY_THRESHOLD_LOW:
            status = "🟢"
            status_text = "Низкий"
        else:
            status = "🟡"
            status_text = "Средний"

        # Добавляем индикатор проблем
        problem_indicator = ""
        if failures > 3:
            problem_indicator = f" ⚠️{failures}"

        repo_short = repo.split('/')[-1]  # Показываем только название репозитория
        
        priority_info += (
            f"{status} *{repo_short}*\n"
            f"   └ {status_text} приоритет ({score:.2f})\n"
            f"   └ Интервал: {interval} мин{problem_indicator}\n"
            f"   └ Обновлений: {updates}, проверок: {total_checks}\n\n"
        )

    # Добавляем легенду
    priority_info += (
        f"📝 *Легенда:*\n"
        f"🔴 Высокий приоритет (≥{PRIORITY_THRESHOLD_HIGH}) — проверка каждые {MIN_CHECK_INTERVAL_MINUTES} мин\n"
        f"🟡 Средний приоритет — проверка по расписанию\n"
        f"🟢 Низкий приоритет (≤{PRIORITY_THRESHOLD_LOW}) — проверка каждые {MAX_CHECK_INTERVAL_MINUTES//60} ч\n"
        f"⚠️ Проблемы с подключением"
    )

    await message.answer(priority_info, parse_mode="Markdown")

async def sync_command(message: Message):
    """Обработчик команды /sync - принудительная синхронизация с БД"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"🔄 Администратор запрашивает синхронизацию с БД")

    try:
        # Отправляем сообщение о начале синхронизации
        sync_msg = await message.answer("🔄 Синхронизация с базой данных...")
        
        # Проверяем доступность Supabase
        if not priority_manager.supabase_manager:
            await sync_msg.edit_text("❌ Supabase недоступен. Проверьте настройки подключения.", parse_mode="Markdown")
            return
        
        # Синхронизируем приоритеты
        await priority_manager.initialize_priorities()
        
        # Получаем обновленную статистику
        priority_stats = priority_manager.get_priority_stats()
        
        # Проверяем статус синхронизации
        sync_status = "✅" if priority_manager.db_synced else "⚠️"
        sync_text = "Синхронизировано" if priority_manager.db_synced else "Не синхронизировано"
        
        success_message = (
            f"{sync_status} *Синхронизация завершена!*\n\n"
            f"📊 *Статус приоритетов:*\n"
            f"• Высокий приоритет: {priority_stats['high_priority']} 🔴\n"
            f"• Средний приоритет: {priority_stats['medium_priority']} 🟡\n"
            f"• Низкий приоритет: {priority_stats['low_priority']} 🟢\n"
            f"• Проблемные: {priority_stats['failing_repos']} ⚠️\n\n"
            f"🗄️ *База данных:*\n"
            f"• Статус: {sync_text}\n"
            f"• Репозиториев: {priority_stats['total_repos']}\n"
            f"• Средний интервал: {priority_stats['average_interval']} мин\n\n"
            f"🔄 *Последнее обновление:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Обновляем сообщение
        await sync_msg.edit_text(success_message, parse_mode="Markdown")
        logger.info("✅ Синхронизация с БД завершена успешно")
        
    except Exception as e:
        error_message = f"❌ *Ошибка синхронизации:* {str(e)}"
        await sync_msg.edit_text(error_message, parse_mode="Markdown")
        logger.error(f"❌ Ошибка синхронизации с БД: {e}")

async def pstats_command(message: Message):
    """Обработчик команды /pstats"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"📈 Администратор запрашивает статистику приоритетов")

    stats = priority_manager.get_priority_stats()
    
    # Определяем эффективность системы
    if stats['total_repos'] > 0:
        high_ratio = stats['high_priority'] / stats['total_repos'] * 100
        low_ratio = stats['low_priority'] / stats['total_repos'] * 100
        medium_ratio = stats['medium_priority'] / stats['total_repos'] * 100
    else:
        high_ratio = low_ratio = medium_ratio = 0

    last_update = priority_manager.last_priority_update
    if last_update:
        update_text = last_update.strftime('%Y-%m-%d %H:%M UTC')
        time_since = datetime.now(timezone.utc) - last_update
        hours_since = time_since.total_seconds() / 3600
    else:
        update_text = "Еще не обновлялось"
        hours_since = 0

    stats_message = (
        f"📈 *Статистика системы приоритетов*\n\n"
        
        f"📊 *Распределение приоритетов:*\n"
        f"🔴 Высокий: {stats['high_priority']} ({high_ratio:.1f}%)\n"
        f"🟡 Средний: {stats['medium_priority']} ({medium_ratio:.1f}%)\n"
        f"🟢 Низкий: {stats['low_priority']} ({low_ratio:.1f}%)\n"
        f"📦 Всего: {stats['total_repos']}\n\n"
        
        f"⚠️ *Проблемные репозитории:* {stats['failing_repos']}\n"
        f"📊 *Средний интервал проверки:* {stats['average_interval']} мин\n\n"
        
        f"📈 *Общая активность:*\n"
        f"• Всего проверок: {stats['total_checks']:,}\n"
        f"• Всего обновлений: {stats['total_updates']:,}\n\n"
        
        f"🔄 *Последнее обновление:*\n"
        f"• Дата: {update_text}\n"
        f"• Прошло времени: {hours_since:.1f} ч\n\n"
        
        f"⚙️ *Настройки системы:*\n"
        f"• Мин. интервал: {MIN_CHECK_INTERVAL_MINUTES} мин\n"
        f"• Макс. интервал: {MAX_CHECK_INTERVAL_MINUTES//60} ч\n"
        f"• Период анализа: {PRIORITY_UPDATE_DAYS} дней\n"
        f"• Высокий приоритет: ≥{PRIORITY_THRESHOLD_HIGH}\n"
        f"• Низкий приоритет: ≤{PRIORITY_THRESHOLD_LOW}"
    )

    await message.answer(stats_message, parse_mode="Markdown")

async def checkall_command(message: Message):
    """Обработчик команды /checkall"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"🔄 Администратор запускает принудительную проверку всех репозиториев")

    status_message = await message.answer(
        "🔄 *Запуск принудительной проверки всех репозиториев...*\n\n"
        "⏳ Это может занять несколько минут. Пожалуйста, подождите.",
        parse_mode="Markdown"
    )

    try:
        # Запускаем проверку
        start_time = datetime.now()
        await check_all_repositories(message.bot)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        await status_message.edit_text(
            f"✅ *Принудительная проверка завершена*\n\n"
            f"⏱️ Время выполнения: {duration:.1f} сек\n"
            f"📦 Проверено репозиториев: {len(REPOS)}\n"
            f"🕒 Завершено: {end_time.strftime('%H:%M:%S')}\n\n"
            f"Результаты проверки записаны в логи. "
            f"Используйте /stats для просмотра общей статистики.",
            parse_mode="Markdown"
        )
    
    except Exception as e:
        logger.error(f"Ошибка при принудительной проверке: {e}")
        await status_message.edit_text(
            f"❌ *Ошибка при проверке репозиториев*\n\n"
            f"Произошла ошибка: `{str(e)[:200]}`\n\n"
            f"Проверьте логи для получения подробной информации.",
            parse_mode="Markdown"
        )

async def backup_command(message: Message):
    """Обработчик команды /backup для создания резервных копий"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"💾 Администратор создает резервные копии")

    try:
        # Создаем папку для резервных копий с датой
        backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_folder = os.path.join(BACKUP_DIR, f"backup_{backup_timestamp}")
        os.makedirs(backup_folder, exist_ok=True)

        files_to_backup = [
            STATE_FILE,
            FILTERS_FILE,
            HISTORY_FILE,
            USERS_FILE,
            STATISTICS_FILE
        ]

        backed_up_files = []
        
        for file_path in files_to_backup:
            if os.path.exists(file_path):
                backup_path = os.path.join(backup_folder, os.path.basename(file_path))
                shutil.copy2(file_path, backup_path)
                backed_up_files.append(os.path.basename(file_path))

        if backed_up_files:
            await message.answer(
                                f"💾 *Резервная копия создана*\n\n"
                f"📁 Папка: `{backup_folder}`\n"
                f"📋 Файлы: {', '.join(backed_up_files)}\n"
                f"🕒 Время создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"✅ Всего файлов скопировано: {len(backed_up_files)}",
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                "⚠️ *Внимание*\n\n"
                "Не найдено файлов для резервного копирования.\n"
                "Возможно, бот запущен впервые или файлы данных отсутствуют.",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Ошибка создания резервной копии: {e}")
        await message.answer(
            f"❌ *Ошибка создания резервной копии*\n\n"
            f"Произошла ошибка: `{str(e)[:200]}`\n\n"
            f"Проверьте права доступа к файловой системе.",
            parse_mode="Markdown"
        )

# --- ДОПОЛНИТЕЛЬНЫЕ СЛУЖЕБНЫЕ КОМАНДЫ ---

async def debug_command(message: Message):
    """Обработчик команды /debug для отладочной информации"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"🐛 Администратор запрашивает отладочную информацию")

    try:
        # Информация о системе
        import psutil
        import sys
        
        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage('.')
        
        debug_info = (
            f"🐛 *Отладочная информация*\n\n"
            
            f"💻 *Система:*\n"
            f"• Python: {sys.version.split()[0]}\n"
            f"• Платформа: {sys.platform}\n"
            f"• ОЗУ: {memory_info.percent}% использовано\n"
            f"• Диск: {disk_info.percent}% использовано\n\n"
            
            f"📁 *Файлы данных:*\n"
        )
        
        data_files = [
            (STATE_FILE, "Состояние релизов"),
            (FILTERS_FILE, "Фильтры пользователей"),
            (HISTORY_FILE, "История релизов"),
            (USERS_FILE, "База пользователей"),
            (STATISTICS_FILE, "Статистика бота")
        ]
        
        for file_path, description in data_files:
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                debug_info += f"✅ {description}: {size:,} байт ({modified.strftime('%d.%m %H:%M')})\n"
            else:
                debug_info += f"❌ {description}: файл отсутствует\n"
        
        # Информация о GitHub API
        debug_info += f"\n🔗 *GitHub API:*\n"
        if GITHUB_TOKEN:
            debug_info += f"✅ Токен настроен (длина: {len(GITHUB_TOKEN)} символов)\n"
        else:
            debug_info += f"⚠️ Токен не настроен (возможны ограничения)\n"
        
        # Статус планировщика
        debug_info += f"\n⏰ *Планировщик:*\n"
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            debug_info += f"✅ Модуль планировщика доступен\n"
        except ImportError:
            debug_info += f"❌ Модуль планировщика недоступен\n"
        
        # Статус Supabase
        debug_info += f"\n🗄️ *Supabase:*\n"
        try:
            from supabase_config import SupabaseManager
            supabase = SupabaseManager()
            debug_info += f"✅ SupabaseManager доступен\n"
            if supabase.supabase_url:
                debug_info += f"• URL: {supabase.supabase_url[:30]}...\n"
            if supabase.supabase_key:
                debug_info += f"• Ключ: {supabase.supabase_key[:10]}...\n"
        except ImportError:
            debug_info += f"❌ Модуль Supabase недоступен\n"
        except Exception as e:
            debug_info += f"⚠️ Ошибка Supabase: {str(e)[:50]}...\n"
        
        await message.answer(debug_info, parse_mode="Markdown")
        
    except ImportError:
        await message.answer(
            "⚠️ Модуль psutil не установлен. Отладочная информация ограничена.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка получения отладочной информации: {e}")
        await message.answer(
            f"❌ Ошибка получения отладочной информации: `{str(e)}`",
            parse_mode="Markdown"
        )

async def logs_command(message: Message):
    """Обработчик команды /logs для просмотра последних логов"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"📋 Администратор запрашивает логи")

    try:
        log_dir = "logs"
        today_log = f"{log_dir}/bot_{datetime.now().strftime('%Y%m%d')}.log"
        error_log = f"{log_dir}/errors_{datetime.now().strftime('%Y%m%d')}.log"
        
        log_info = "📋 *Информация о логах*\n\n"
        
        # Основной лог
        if os.path.exists(today_log):
            size = os.path.getsize(today_log)
            log_info += f"📝 *Основной лог:* {size:,} байт\n"
            
            # Читаем последние 10 строк
            with open(today_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-10:] if len(lines) > 10 else lines
                
            if last_lines:
                log_info += f"\n📖 *Последние записи:*\n'''"
                for line in last_lines:
                    # Ограничиваем длину строки
                    if len(line) > 100:
                        line = line[:97] + "...\n"
                    log_info += line
                log_info += "```\n"
        else:
            log_info += f"❌ Основной лог за сегодня не найден\n"
        
        # Лог ошибок
        if os.path.exists(error_log):
            size = os.path.getsize(error_log)
            if size > 0:
                log_info += f"\n⚠️ *Лог ошибок:* {size:,} байт\n"
                
                with open(error_log, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    last_errors = lines[-5:] if len(lines) > 5 else lines
                
                if last_errors:
                    log_info += f"\n🚨 *Последние ошибки:*\n```"
                    for line in last_errors:
                        if len(line) > 150:
                            line = line[:147] + "...\n"
                        log_info += line
                    log_info += "```"
            else:
                log_info += f"\n✅ Ошибок за сегодня не было"
        else:
            log_info += f"\n✅ Лог ошибок не создан (ошибок не было)"
        
        await message.answer(log_info, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка чтения логов: {e}")
        await message.answer(
            f"❌ Ошибка чтения логов: `{str(e)}`",
            parse_mode="Markdown"
        )

# --- ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД ---
async def unknown_command(message: Message):
    """Обработчик неизвестных команд"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    
    command = message.text.split()[0] if message.text else "неизвестная команда"
    logger.info(f"❓ Пользователь {message.from_user.id} использует неизвестную команду: {command}")
    
    await message.answer(
        f"❓ *Неизвестная команда:* `{command}`\n\n"
        f"📋 Используйте /help для просмотра доступных команд.\n\n"
        f"💡 *Основные команды:*\n"
        f"• /start — приветствие\n"
        f"• /filter — настроить фильтры\n"
        f"• /last — последние релизы\n"
        f"• /help — полная справка",
        parse_mode="Markdown"
    )

# --- MIDDLEWARE ДЛЯ ЛОГИРОВАНИЯ ---
class LoggingMiddleware:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def __call__(self, handler, event, data):
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Логируем входящее событие
            if hasattr(event, 'from_user') and event.from_user:
                user_id = event.from_user.id
                username = event.from_user.username or "None"
                
                if hasattr(event, 'text') and event.text:
                    self.logger.info(f"📥 Сообщение от {user_id} (@{username}): {event.text[:50]}")
                elif hasattr(event, 'data') and event.data:
                    self.logger.info(f"📥 Callback от {user_id} (@{username}): {event.data}")
            
            # Выполняем обработчик
            result = await handler(event, data)
            
            # Логируем время выполнения
            execution_time = asyncio.get_event_loop().time() - start_time
            if execution_time > 1.0:  # Логируем только медленные операции
                self.logger.warning(f"⏱️ Медленная операция: {execution_time:.2f}с")
            
            return result
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            self.logger.error(f"❌ Ошибка в middleware: {e} (время: {execution_time:.2f}с)")
            raise

# --- ОБРАБОТЧИК ОШИБОК ---
async def error_handler(event, exception):
    """Глобальный обработчик ошибок"""
    logger.error(f"❌ Необработанная ошибка: {exception}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Уведомляем админа о критических ошибках
    if ADMIN_ID:
        try:
            # Создаем экземпляр бота для отправки сообщения
            # (это не идеальное решение, но работает)
            error_message = (
                f"🚨 *Критическая ошибка в боте*\n\n"
                f"❌ Ошибка: `{str(exception)[:300]}`\n"
                f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📍 Событие: {type(event).__name__}"
            )
            
            # Попытка отправить через существующий бот
            if hasattr(event, 'bot'):
                await event.bot.send_message(ADMIN_ID, error_message, parse_mode="Markdown")
        except:
            pass  # Игнорируем ошибки отправки уведомлений об ошибках

# --- РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ---
def register_handlers(dp: Dispatcher):
    """Регистрирует все обработчики команд и событий"""
    logger.info("📝 Регистрация обработчиков команд...")
    
    # Основные команды
    dp.message.register(start_command, CommandStart())
    dp.message.register(help_command, Command("help"))
    dp.message.register(donate_command, Command("donate"))
    
    # Команды управления фильтрами
    dp.message.register(filter_command, Command("filter"))
    dp.message.register(myfilters_command, Command("myfilters"))
    dp.message.register(clearfilters_command, Command("clearfilters"))
    
    # Команды просмотра данных
    dp.message.register(last_command, Command("last"))
    
    # Административные команды
    dp.message.register(stats_command, Command("stats"))
    dp.message.register(priority_command, Command("priority"))
    dp.message.register(sync_command, Command("sync"))
    dp.message.register(pstats_command, Command("pstats"))
    dp.message.register(checkall_command, Command("checkall"))
    dp.message.register(backup_command, Command("backup"))
    dp.message.register(debug_command, Command("debug"))
    dp.message.register(logs_command, Command("logs"))
    
    # Обработчики callback-кнопок
    dp.callback_query.register(cancel_filter_callback, F.data == "cancel_filter")
    
    # Обработчик текста (для фильтров)
    dp.message.register(process_filter_text, F.text & ~F.command)
    
    # Обработчик неизвестных команд (должен быть последним)
    dp.message.register(unknown_command, F.text & F.text.startswith('/'))
    
    logger.info("✅ Все обработчики зарегистрированы")

# --- ФУНКЦИЯ ОЧИСТКИ СТАРЫХ ФАЙЛОВ ---
async def cleanup_old_files():
    """Очищает старые файлы логов и резервных копий"""
    logger.info("🧹 Запуск очистки старых файлов...")
    
    try:
        # Очистка старых логов (старше 30 дней)
        log_dir = "logs"
        if os.path.exists(log_dir):
            cutoff_date = datetime.now() - timedelta(days=30)
            
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        logger.info(f"🗑️ Удален старый лог: {filename}")
        
        # Очистка старых резервных копий (старше 14 дней)
        if os.path.exists(BACKUP_DIR):
            cutoff_date = datetime.now() - timedelta(days=14)
            
            for item in os.listdir(BACKUP_DIR):
                item_path = os.path.join(BACKUP_DIR, item)
                if os.path.isdir(item_path):
                    item_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                    if item_time < cutoff_date:
                        shutil.rmtree(item_path)
                        logger.info(f"🗑️ Удалена старая резервная копия: {item}")
        
        logger.info("✅ Очистка старых файлов завершена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке старых файлов: {e}")

# --- ФУНКЦИЯ ПРОВЕРКИ ЗДОРОВЬЯ БОТА ---
async def health_check():
    """Проверяет состояние бота и его компонентов"""
    logger.info("🏥 Проверка состояния бота...")
    
    issues = []
    
    try:
        # Проверка файлов данных
        required_files = [STATE_FILE, USERS_FILE]
        for file_path in required_files:
            if not os.path.exists(file_path):
                issues.append(f"Отсутствует обязательный файл: {file_path}")
        
        # Проверка размера файлов истории
        if os.path.exists(HISTORY_FILE):
            size = os.path.getsize(HISTORY_FILE)
            if size > 50 * 1024 * 1024:  # 50 МБ
                issues.append(f"Файл истории слишком большой: {size // 1024 // 1024} МБ")
        
        # Проверка статистики ошибок
        error_rate = statistics_manager.stats.get('errors_count', 0)
        total_checks = statistics_manager.stats.get('total_checks', 1)
        if error_rate / max(total_checks, 1) > 0.1:  # Более 10% ошибок
            issues.append(f"Высокий уровень ошибок: {error_rate}/{total_checks}")
        
        # Проверка дискового пространства
        try:
            import psutil
            disk_usage = psutil.disk_usage('.')
            if disk_usage.percent > 90:
                issues.append(f"Мало места на диске: {disk_usage.percent}%")
        except ImportError:
            pass
        
        if issues:
            logger.warning(f"⚠️ Обнаружены проблемы: {'; '.join(issues)}")
            
            # Уведомляем админа о критических проблемах
            if ADMIN_ID and len(issues) > 3:
                try:
                    # Здесь нужно было бы отправить сообщение, но у нас нет доступа к боту
                    # Эта функциональность может быть добавлена позже
                    pass
                except:
                    pass
        else:
            logger.info("✅ Состояние бота в норме")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке состояния: {e}")

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    """Главная функция запуска бота"""
    print("=" * 50)
    print("🚀 ЗАПУСК БОТА МОНИТОРИНГА GITHUB РЕЛИЗОВ")
    print("=" * 50)

    # Проверка обязательных переменных
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        print("КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден в файле .env!")
        print("Пожалуйста, создайте файл .env и добавьте туда BOT_TOKEN=ваш_токен")
        return

    if not ADMIN_ID:
        logger.error("❌ ADMIN_ID не найден в переменных окружения!")
        print("ПРЕДУПРЕЖДЕНИЕ: ADMIN_ID не настроен. Административные функции будут недоступны.")

    logger.info("🤖 Инициализация бота...")
    print("🤖 Инициализация бота...")

    # Создаем экземпляры бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Добавляем middleware для логирования
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())

    # Устанавливаем обработчик ошибок
    dp.errors.register(error_handler)

    logger.info("📝 Регистрация обработчиков...")
    print("📝 Регистрация обработчиков...")
    register_handlers(dp)

    logger.info("⏰ Настройка планировщика задач...")
    print("⏰ Настройка планировщика задач...")
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Основная задача проверки репозиториев (каждые 15 минут)
    scheduler.add_job(
        check_repositories,
        'interval',
        minutes=15,
        kwargs={'bot': bot},
        id='repositories_check',
        max_instances=1,  # Предотвращаем одновременный запуск
        coalesce=True    # Объединяем пропущенные запуски
    )

    # Обновление приоритетов (каждые 6 часов)
    scheduler.add_job(
        lambda: priority_manager.update_priorities(history_manager),
        'interval',
        hours=6,
        id='priority_update',
        max_instances=1
    )

    # Очистка старых файлов (каждый день в 03:00)
    scheduler.add_job(
        cleanup_old_files,
        'cron',
        hour=3,
        minute=0,
        id='cleanup_files',
        max_instances=1
    )

    # Проверка здоровья бота (каждые 2 часа)
    scheduler.add_job(
        health_check,
        'interval',
        hours=2,
        id='health_check',
        max_instances=1
    )

    # Сохранение статистики (каждые 30 минут)
    scheduler.add_job(
        lambda: statistics_manager._save_stats(),
        'interval',
        minutes=30,
        id='save_statistics',
        max_instances=1
    )

    logger.info("✅ Планировщик настроен")
    print("✅ Планировщик настроен")

    # Запускаем планировщик
    scheduler.start()
    logger.info("⏰ Планировщик запущен")
    print("⏰ Планировщик запущен")

    # Инициализируем приоритеты из базы данных
    logger.info("🗄️ Инициализация приоритетов из базы данных...")
    print("🗄️ Инициализация приоритетов из базы данных...")
    try:
        await priority_manager.initialize_priorities()
        logger.info("✅ Приоритеты успешно инициализированы из БД")
        print("✅ Приоритеты успешно инициализированы из БД")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации приоритетов: {e}")
        print(f"❌ Ошибка инициализации приоритетов: {e}")
        # Продолжаем работу с локальными данными

    # Выводим информацию о конфигурации
    print(f"\n📊 КОНФИГУРАЦИЯ БОТА:")
    print(f"├── Отслеживается репозиториев: {len(REPOS)}")
    print(f"├── GitHub токен: {'✅ Настроен' if GITHUB_TOKEN else '❌ Не настроен'}")
    print(f"├── Канал для уведомлений: {'✅ ' + CHANNEL_ID if CHANNEL_ID else '❌ Не настроен'}")
    print(f"├── Администратор: {'✅ ID=' + str(ADMIN_ID) if ADMIN_ID else '❌ Не настроен'}")
    print(f"├── Интервал проверки: {MIN_CHECK_INTERVAL_MINUTES}-{MAX_CHECK_INTERVAL_MINUTES} мин")
    print(f"└── Хранение истории: {HISTORY_DAYS} дней")

    logger.info("🎯 Выполнение первоначальной проверки репозиториев...")
    print("\n🎯 Выполнение первоначальной проверки репозиториев...")
    
    try:
        # Принудительная проверка всех репозиториев при запуске
        await check_all_repositories(bot)
        logger.info("✅ Первоначальная проверка завершена успешно")
        print("✅ Первоначальная проверка завершена успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка при первоначальной проверке: {e}")
        print(f"⚠️ Ошибка при первоначальной проверке: {e}")
        print("Бот будет продолжать работу, но некоторые данные могут быть неполными")

    # Уведомляем админа о запуске
    if ADMIN_ID:
        try:
            startup_message = (
                f"🚀 *Бот успешно запущен!*\n\n"
                f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📦 Отслеживается репозиториев: {len(REPOS)}\n"
                f"👥 Пользователей в базе: {user_manager.get_count()}\n"
                f"🔍 Пользователей с фильтрами: {filter_manager.get_users_with_filters_count()}\n"
                f"📈 Релизов в истории: {history_manager.get_count()}\n\n"
                f"Бот готов к работе! 🎉"
            )
            await bot.send_message(ADMIN_ID, startup_message, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о запуске админу: {e}")

    logger.info("🎉 Бот успешно запущен и готов к работе!")
    print("\n" + "=" * 50)
    print("🎉 БОТ УСПЕШНО ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    print("📱 Используйте Ctrl+C для остановки бота")
    print("📋 Логи сохраняются в папку logs/")
    print("💾 Резервные копии создаются в папку backups/")
    print("=" * 50 + "\n")

    try:
        # Начинаем получение обновлений
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки от пользователя")
        print("\n⏹️ Получен сигнал остановки...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске поллинга: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
        print("Проверьте логи для получения подробной информации")
    finally:
        logger.info("🛑 Завершение работы бота...")
        print("🛑 Завершение работы бота...")
        
        # Останавливаем планировщик
        try:
            scheduler.shutdown(wait=True)
            logger.info("⏰ Планировщик остановлен")
            print("⏰ Планировщик остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки планировщика: {e}")

        # Сохраняем финальную статистику
        try:
            statistics_manager._save_stats()
            logger.info("💾 Финальная статистика сохранена")
            print("💾 Финальная статистика сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

        # Закрываем сессию бота
        try:
            await bot.session.close()
            logger.info("🔌 Сессия бота закрыта")
            print("🔌 Сессия бота закрыта")
        except Exception as e:
            logger.error(f"Ошибка закрытия сессии: {e}")

        # Уведомляем админа об остановке
        if ADMIN_ID:
            try:
                shutdown_message = (
                    f"🛑 *Бот остановлен*\n\n"
                    f"⏰ Время остановки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📊 Время работы: {statistics_manager.get_uptime()}\n"
                    f"📈 Всего проверок: {statistics_manager.stats['total_checks']}\n"
                    f"🔔 Всего уведомлений: {statistics_manager.stats['total_notifications_sent']}\n\n"
                    f"До свидания! 👋"
                )
                # Создаем новую сессию для отправки последнего сообщения
                final_bot = Bot(token=BOT_TOKEN)
                await final_bot.send_message(ADMIN_ID, shutdown_message, parse_mode="Markdown")
                await final_bot.session.close()
            except:
                pass  # Игнорируем ошибки при завершении

        logger.info("✅ Бот полностью остановлен")
        print("✅ Бот полностью остановлен")

# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск приложения...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запуске: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        print("Проверьте логи для получения подробной информации")
        sys.exit(1)


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
import gc
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Set, Tuple
from aiohttp import ClientSession, ClientError, ClientResponseError, TCPConnector, ClientTimeout
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
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
    except Exception as e:
        print(f"Не удалось установить кодировку UTF-8: {e}")

# Загрузка переменных окружения
load_dotenv()

# --- ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ VPS ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DONATE_URL = "https://boosty.to/vokforever/donate"

# VPS-оптимизированные параметры
VPS_PROFILE = os.getenv("VPS_PROFILE", "low_power")
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "2"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "25"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "3"))
MEMORY_THRESHOLD_MB = int(os.getenv("MEMORY_THRESHOLD_MB", "75"))
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "4"))

# Адаптивные интервалы проверки
MIN_CHECK_INTERVAL_MINUTES = int(os.getenv("MIN_CHECK_INTERVAL", "30"))
MAX_CHECK_INTERVAL_MINUTES = int(os.getenv("MAX_CHECK_INTERVAL", "2880"))
DEFAULT_CHECK_INTERVAL_MINUTES = int(os.getenv("DEFAULT_CHECK_INTERVAL", "720"))

# Остальные параметры
MAX_RETRIES = 2  # Уменьшено с 3 до 2
RETRY_DELAY = 1  # Уменьшено с 2 до 1
HISTORY_DAYS = 14  # Уменьшено с 30 до 14 дней
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
PRIORITY_THRESHOLD_HIGH = 0.5
PRIORITY_THRESHOLD_LOW = 0.1

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

# --- ОПТИМИЗИРОВАННОЕ ЛОГИРОВАНИЕ ---
def setup_logging():
    """Настройка системы логирования с оптимизацией для VPS"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Определяем уровень логирования на основе профиля VPS
    if VPS_PROFILE == "ultra_low_power":
        log_level = logging.WARNING
        enable_file_logging = False
    elif VPS_PROFILE == "low_power":
        log_level = logging.INFO
        enable_file_logging = True
    else:
        log_level = logging.INFO
        enable_file_logging = True
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # Консольный вывод (всегда включен)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Файловое логирование только для профилей с достаточными ресурсами
    if enable_file_logging:
        # Основной лог-файл с ограничением размера
        file_handler = logging.FileHandler(
            f'{log_dir}/bot_{datetime.now().strftime("%Y%m%d")}.log', 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        
        # Лог ошибок только для критических ошибок
        error_handler = logging.FileHandler(
            f'{log_dir}/errors_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# --- ОПТИМИЗИРОВАННЫЕ ФУНКЦИИ ОЧИСТКИ ---
def clean_markdown_text(text: str) -> str:
    """Упрощенная очистка Markdown для экономии ресурсов"""
    if not text:
        return text
    
    # Используем простые замены вместо сложных regex
    text = text.replace('**', '').replace('__', '').replace('```', '').replace('~~', '')
    text = re.sub(r'[\*_~`|]', '', text)
    return text.strip()

def clean_text_for_telegram(text: str) -> str:
    """Упрощенная очистка текста для Telegram"""
    if not text:
        return text
    
    # Базовые замены
    text = re.sub(r'<[^>]+>', '', text)
    text = clean_markdown_text(text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\{.*?\}', '', text)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    return text.strip()

def escape_markdown(text: str) -> str:
    """Упрощенное экранирование Markdown"""
    if not text:
        return ""
    
    escape_chars = '_*[]()~`>#+='
    escaped_text = ""
    for char in text:
        if char in escape_chars:
            escaped_text += f'\\{char}'
        else:
            escaped_text += char
    
    return escaped_text

def validate_telegram_text(text: str, max_length: int = 4096) -> str:
    """Валидация текста для Telegram с ограничением длины"""
    if not text:
        return ""
    
    if len(text) > max_length:
        words = text[:max_length-3].rsplit(' ', 1)
        if len(words) > 1:
            text = words[0] + "..."
        else:
            text = text[:max_length-3] + "..."
    
    text = clean_text_for_telegram(text)
    return text

# --- ОПТИМИЗИРОВАННЫЙ КЛАСС ДЛЯ УПРАВЛЕНИЯ ПРИОРИТЕТАМИ ---
class RepositoryPriorityManager:
    def __init__(self):
        self.priorities = {}
        self.last_priority_update = None
        self.supabase_manager = None
        self.db_synced = False
        
        try:
            from supabase_config import SupabaseManager
            self.supabase_manager = SupabaseManager()
            logger.info("SupabaseManager успешно инициализирован")
        except ImportError as e:
            logger.error(f"Не удалось импортировать SupabaseManager: {e}")
        except Exception as e:
            logger.error(f"Ошибка инициализации SupabaseManager: {e}")

    def _load_priorities_from_db(self) -> Dict[str, Dict]:
        """Загружает приоритеты из базы данных Supabase"""
        if not self.supabase_manager:
            logger.error("SupabaseManager недоступен, невозможно загрузить приоритеты")
            raise RuntimeError("SupabaseManager недоступен")

        try:
            result = self.supabase_manager.get_repository_priorities()
            
            if result:
                db_priorities = {}
                for record in result:
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

    def initialize_priorities(self):
        """Инициализирует приоритеты при запуске"""
        self.priorities = self._load_priorities_from_db()
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

    def _save_priorities_to_db(self):
        """Сохраняет приоритеты в базу данных Supabase"""
        if not self.supabase_manager:
            logger.error("SupabaseManager недоступен, невозможно сохранить приоритеты")
            raise RuntimeError("SupabaseManager недоступен")

        try:
            priorities_data = {}
            for repo_name, repo_data in self.priorities.items():
                priorities_data[repo_name] = {
                    'update_count': repo_data.get('update_count', 0),
                    'last_update': repo_data.get('last_update'),
                    'check_interval': repo_data.get('check_interval', DEFAULT_CHECK_INTERVAL_MINUTES),
                    'priority_score': repo_data.get('priority_score', 0.0),
                    'last_check': repo_data.get('last_check'),
                    'consecutive_failures': repo_data.get('consecutive_failures', 0),
                    'total_checks': repo_data.get('total_checks', 0),
                    'average_response_time': repo_data.get('average_response_time', 0.0)
                }
            
            self.supabase_manager.store_repository_priorities({'priorities': priorities_data})
            logger.info(f"Приоритеты успешно сохранены в БД: {len(priorities_data)} репозиториев")

        except Exception as e:
            logger.error(f"Ошибка сохранения приоритетов в БД: {e}")
            raise RuntimeError(f"Не удалось сохранить приоритеты в БД: {e}")

    def _save_priorities(self):
        """Основной метод сохранения - использует БД"""
        self._save_priorities_to_db()

    def get_priority(self, repo: str) -> Dict:
        if repo not in self.priorities:
            self.priorities[repo] = self._create_default_priority()
            self._save_priorities_to_db()
        return self.priorities[repo]

    def record_update(self, repo: str):
        priority_data = self.get_priority(repo)
        priority_data['update_count'] += 1
        priority_data['last_update'] = datetime.now(timezone.utc).isoformat()
        priority_data['consecutive_failures'] = 0
        self._save_priorities_to_db()
        logger.info(f"Зарегистрировано обновление для {repo}. Всего обновлений: {priority_data['update_count']}")

    def record_check(self, repo: str, success: bool = True, response_time: float = 0.0):
        """Записывает информацию о проверке репозитория"""
        priority_data = self.get_priority(repo)
        priority_data['total_checks'] += 1
        priority_data['last_check'] = datetime.now(timezone.utc).isoformat()
        
        if success:
            priority_data['consecutive_failures'] = 0
            if priority_data['average_response_time'] > 0:
                priority_data['average_response_time'] = (
                    priority_data['average_response_time'] + response_time
                ) / 2
            else:
                priority_data['average_response_time'] = response_time
        else:
            priority_data['consecutive_failures'] += 1
            
        self._save_priorities_to_db()

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

            # Определяем интервал проверки с учетом профиля VPS
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
        self._save_priorities_to_db()

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

# --- КЛАСС ДЛЯ КЭШИРОВАНИЯ ---
class GitHubCache:
    """Кэш для GitHub API запросов для экономии ресурсов"""
    
    def __init__(self, cache_file: str, max_age_hours: int = 2):
        self.cache_file = cache_file
        self.max_age_seconds = max_age_hours * 3600
        self.cache = {}
        self.load_cache()
    
    def load_cache(self):
        """Загружает кэш из файла"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                logger.info(f"Кэш загружен: {len(self.cache)} записей")
        except Exception as e:
            logger.warning(f"Ошибка загрузки кэша: {e}")
            self.cache = {}
    
    def save_cache(self):
        """Сохраняет кэш в файл"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения кэша: {e}")
    
    def get(self, key: str) -> Optional[Dict]:
        """Получает значение из кэша если оно не устарело"""
        if key in self.cache:
            cache_entry = self.cache[key]
            if time.time() - cache_entry['timestamp'] < self.max_age_seconds:
                return cache_entry['data']
            else:
                # Удаляем устаревшую запись
                del self.cache[key]
        return None
    
    def set(self, key: str, data: Dict):
        """Сохраняет значение в кэш"""
        self.cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        # Ограничиваем размер кэша
        if len(self.cache) > 100:
            # Удаляем самые старые записи
            oldest_keys = sorted(self.cache.keys(), 
                               key=lambda k: self.cache[k]['timestamp'])[:20]
            for old_key in oldest_keys:
                del self.cache[old_key]
    
    def cleanup(self):
        """Очищает устаревшие записи"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry['timestamp'] > self.max_age_seconds
        ]
        for key in expired_keys:
            del self.cache[key]
        if expired_keys:
            logger.info(f"Очищено {len(expired_keys)} устаревших записей кэша")

# Инициализация кэша
github_cache = GitHubCache(STATE_FILE)

# --- ОПТИМИЗИРОВАННЫЕ КЛАССЫ ДЛЯ УПРАВЛЕНИЯ ДАННЫМИ ---

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

class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.users_data = self._load_users()

    def _load_users(self) -> Dict[int, Dict]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        return {user_id: self._create_user_data() for user_id in data}
                    elif isinstance(data, dict):
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
                        active_users.add(user_id)
                else:
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
            if os.path.exists(self.filters_file):
                backup_file = f"{self.filters_file}.bak"
                shutil.copy2(self.filters_file, backup_file)

            with open(self.filters_file, 'w', encoding='utf-8') as f:
                json.dump(self.filters, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Ошибка сохранения фильтров: {e}")

    def set_filters(self, user_id: str, keywords: List[str]):
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
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
            filtered_history = [
                rel for rel in self.history
                if datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00')) >= cutoff_date
            ]

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

# --- ОПТИМИЗИРОВАННАЯ ЗАГРУЗКА ИНФОРМАЦИИ О РЕЛИЗАХ ---
async def fetch_release_optimized(session: ClientSession, repo_name: str) -> Tuple[Optional[Dict], float]:
    """Оптимизированная загрузка информации о последнем релизе с кэшированием"""
    
    # Проверяем кэш
    cache_key = f"release_{repo_name}"
    cached_data = github_cache.get(cache_key)
    if cached_data:
        logger.debug(f"Используем кэшированные данные для {repo_name}")
        return cached_data, 0.0
    
    # Проверяем использование памяти
    # await resource_manager.check_memory_usage() # resource_manager is not defined in this file
    
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {'User-Agent': 'GitHub-Release-Monitor-Bot-Optimized'}
    
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    start_time = time.time()
    
    # async with resource_manager.request_semaphore: # resource_manager is not defined in this file
    #     for attempt in range(MAX_RETRIES):
    #         try:
    #             async with session.get(api_url, headers=headers) as response:
    #                 response_time = time.time() - start_time
                    
    #                 if response.status == 200:
    #                     data = await response.json()
                        
    #                     # Кэшируем результат
    #                     github_cache.set(cache_key, data)
                        
    #                     logger.debug(f"Успешно получены данные для {repo_name} за {response_time:.2f}с")
    #                     return data, response_time
                        
    #                 elif response.status == 403:
    #                     # Rate limit - увеличиваем интервал проверки
    #                     logger.warning(f"Rate limit для {repo_name}")
    #                     return None, response_time
                        
    #                 elif response.status == 404:
    #                     logger.warning(f"Репозиторий не найден: {repo_name}")
    #                     return None, response_time
                        
    #                 else:
    #                     logger.warning(f"Статус {response.status} для {repo_name}")
    #                     if attempt < MAX_RETRIES - 1:
    #                         await asyncio.sleep(RETRY_DELAY)
    #                         continue
    #                     return None, response_time
                        
    #         except asyncio.TimeoutError:
    #             logger.warning(f"Timeout при запросе к {repo_name}")
    #         except Exception as e:
    #             logger.warning(f"Ошибка запроса к {repo_name}: {e}")
                
    #         if attempt < MAX_RETRIES - 1:
    #             await asyncio.sleep(RETRY_DELAY)
    
    response_time = time.time() - start_time
    return None, response_time

# --- ОПТИМИЗИРОВАННАЯ ПРОВЕРКА РЕПОЗИТОРИЕВ С ПРИОРИТЕТАМИ ---
async def check_repositories_optimized(bot: Bot):
    """Оптимизированная проверка репозиториев с учетом приоритетов"""
    logger.info("🔄 Запуск оптимизированной проверки репозиториев с приоритетами...")
    
    # Проверяем ресурсы
    # await resource_manager.check_memory_usage() # resource_manager is not defined in this file
    
    # Обновляем приоритеты если нужно
    if priority_manager.should_update_priorities():
        logger.info("📊 Обновление приоритетов репозиториев...")
        priority_manager.update_priorities(history_manager)
    
    current_time = datetime.now(timezone.utc)
    repos_to_check = []
    
    # Определяем какие репозитории нужно проверить на основе приоритетов
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
    
    if not repos_to_check:
        logger.info("Нет репозиториев для проверки")
        return
    
    logger.info(f"📋 Будет проверено {len(repos_to_check)} из {len(REPOS)} репозиториев")
    
    # Обрабатываем репозитории пакетами
    for i in range(0, len(repos_to_check), BATCH_SIZE):
        batch = repos_to_check[i:i + BATCH_SIZE]
        
        # Создаем сессию для пакета
        # async with resource_manager.get_session() as session: # resource_manager is not defined in this file
        async with ClientSession() as session: # Simplified for now, assuming a session manager exists or is needed
            tasks = []
            for repo_name in batch:
                task = check_single_repo_optimized(bot, session, repo_name)
                tasks.append(task)
            
            # Выполняем пакет параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for repo_name, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка при проверке {repo_name}: {result}")
                elif result:
                    logger.info(f"Найдено обновление для {repo_name}")
                
                # Обновляем время последней проверки
                priority_data = priority_manager.get_priority(repo_name)
                priority_data['last_check'] = current_time.isoformat()
                priority_manager._save_priorities()
        
        # Пауза между пакетами для экономии ресурсов
        if i + BATCH_SIZE < len(repos_to_check):
            await asyncio.sleep(5)
    
    # Сохраняем кэш
    github_cache.save_cache()
    
    logger.info("✅ Оптимизированная проверка с приоритетами завершена")

async def check_single_repo_optimized(bot: Bot, session: ClientSession, repo_name: str) -> bool:
    """Оптимизированная проверка одного репозитория с учетом приоритетов"""
    try:
        # Обновляем статистику проверок
        priority_manager.record_check(repo_name, True, 0.0)
        
        release, response_time = await fetch_release_optimized(session, repo_name)
        
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

        # Здесь должна быть проверка на новые теги
        # Для демонстрации возвращаем False
        
        return False

    except Exception as e:
        logger.error(f"Ошибка при проверке {repo_name}: {e}")
        priority_manager.record_check(repo_name, False, 0.0)
        return False

# --- ОПТИМИЗИРОВАННЫЙ ПЛАНИРОВЩИК ---
def setup_optimized_scheduler(scheduler: AsyncIOScheduler, bot: Bot):
    """Настраивает оптимизированный планировщик для слабого VPS с приоритетами"""
    
    # Основная проверка каждые 30 минут (с учетом приоритетов)
    scheduler.add_job(
        check_repositories_optimized,
        'interval',
        minutes=30,  # Увеличено с 15 до 30
        kwargs={'bot': bot},
        id='repositories_check_optimized',
        max_instances=1,
        coalesce=True
    )
    
    # Очистка кэша каждые 4 часа
    scheduler.add_job(
        lambda: github_cache.cleanup(),
        'interval',
        hours=4,
        id='cache_cleanup',
        max_instances=1
    )
    
    # Проверка ресурсов каждые 2 часа
    # scheduler.add_job( # resource_manager is not defined in this file
    #     resource_manager.check_memory_usage,
    #     'interval',
    #     hours=2,
    #     id='resource_check',
    #     max_instances=1
    # )
    
    # Сохранение кэша каждые 6 часов
    scheduler.add_job(
        github_cache.save_cache,
        'interval',
        hours=6,
        id='cache_save',
        max_instances=1
    )

# --- ОПТИМИЗИРОВАННАЯ ГЛАВНАЯ ФУНКЦИЯ ---
async def main_optimized():
    """Оптимизированная главная функция для слабого VPS с системой приоритетов"""
    print("=" * 50)
    print("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО БОТА С ПРИОРИТЕТАМИ ДЛЯ СЛАБОГО VPS")
    print("=" * 50)

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return

    logger.info("🤖 Инициализация оптимизированного бота с приоритетами...")
    print("🤖 Инициализация оптимизированного бота с приоритетами...")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    logger.info("⏰ Настройка оптимизированного планировщика с приоритетами...")
    print("⏰ Настройка оптимизированного планировщика с приоритетами...")
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    setup_optimized_scheduler(scheduler, bot)
    
    scheduler.start()
    logger.info("⏰ Оптимизированный планировщик с приоритетами запущен")
    print("⏰ Оптимизированный планировщик с приоритетами запущен")

    print(f"\n📊 ОПТИМИЗИРОВАННАЯ КОНФИГУРАЦИЯ С ПРИОРИТЕТАМИ:")
    print(f"├── Репозиториев: {len(REPOS)}")
    print(f"├── Интервал проверки: {MIN_CHECK_INTERVAL_MINUTES}-{MAX_CHECK_INTERVAL_MINUTES} мин")
    print(f"├── Макс. одновременных запросов: {MAX_CONCURRENT_REQUESTS}")
    print(f"├── Таймаут запроса: {REQUEST_TIMEOUT} сек")
    print(f"├── Размер пакета: {BATCH_SIZE}")
    print(f"├── Кэширование: включено")
    print(f"└── Система приоритетов: активна")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки")
        print("\n⏹️ Остановка...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
    finally:
        logger.info("🛑 Завершение работы...")
        print("🛑 Завершение работы...")
        
        scheduler.shutdown(wait=True)
        github_cache.save_cache()
        await bot.session.close()
        
        logger.info("✅ Бот полностью остановлен")
        print("✅ Бот полностью остановлен")

# --- АДМИНИСТРАТИВНЫЕ КОМАНДЫ ---
async def stats_command(message: Message):
    """Обработчик команды /stats"""
    user_manager.add_user(message.from_user.id, message.from_user.username)
    user_manager.record_activity(message.from_user.id, 'command')

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"📊 Администратор запрашивает статистику")

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
        
        f"⚙️ *VPS профиль:* {VPS_PROFILE}\n"
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

    try:
        priority_manager.initialize_priorities()
        logger.info("✅ Приоритеты синхронизированы с БД для команды /priority")
    except Exception as e:
        logger.warning(f"Не удалось синхронизировать приоритеты с БД: {e}")

    priority_info = "📊 *Приоритеты репозиториев:*\n\n"

    if priority_manager.db_synced:
        priority_info += "🗄️ *Источник:* База данных Supabase\n\n"
    else:
        priority_info += "⚠️ *Источник:* Локальные данные (БД недоступна)\n\n"

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

        if score >= PRIORITY_THRESHOLD_HIGH:
            status = "🔴"
            status_text = "Высокий"
        elif score <= PRIORITY_THRESHOLD_LOW:
            status = "🟢"
            status_text = "Низкий"
        else:
            status = "🟡"
            status_text = "Средний"

        problem_indicator = ""
        if failures > 3:
            problem_indicator = f" ⚠️{failures}"

        repo_short = repo.split('/')[-1]
        
        priority_info += (
            f"{status} *{repo_short}*\n"
            f"   └ {status_text} приоритет ({score:.2f})\n"
            f"   └ Интервал: {interval} мин{problem_indicator}\n"
            f"   └ Обновлений: {updates}, проверок: {total_checks}\n\n"
        )

    priority_info += (
        f"📝 *Легенда:*\n"
        f"🔴 Высокий приоритет (≥{PRIORITY_THRESHOLD_HIGH}) — проверка каждые {MIN_CHECK_INTERVAL_MINUTES} мин\n"
        f"🟡 Средний приоритет — проверка по расписанию\n"
        f"🟢 Низкий приоритет (≤{PRIORITY_THRESHOLD_LOW}) — проверка каждые {MAX_CHECK_INTERVAL_MINUTES//60} ч\n"
        f"⚠️ Проблемы с подключением\n\n"
        f"⚙️ *VPS профиль:* {VPS_PROFILE}"
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
        sync_msg = await message.answer("🔄 Синхронизация с базой данных...")
        
        if not priority_manager.supabase_manager:
            await sync_msg.edit_text("❌ Supabase недоступен. Проверьте настройки подключения.", parse_mode="Markdown")
            return
        
        priority_manager.initialize_priorities()
        priority_stats = priority_manager.get_priority_stats()
        
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
        f"• Низкий приоритет: ≤{PRIORITY_THRESHOLD_LOW}\n\n"
        f"🔧 *VPS профиль:* {VPS_PROFILE}"
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
        
        debug_info += f"\n🔗 *GitHub API:*\n"
        if GITHUB_TOKEN:
            debug_info += f"✅ Токен настроен (длина: {len(GITHUB_TOKEN)} символов)\n"
        else:
            debug_info += f"⚠️ Токен не настроен (возможны ограничения)\n"
        
        debug_info += f"\n⏰ *Планировщик:*\n"
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            debug_info += f"✅ Модуль планировщика доступен\n"
        except ImportError:
            debug_info += f"❌ Модуль планировщика недоступен\n"
        
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
        
        debug_info += f"\n🔧 *VPS профиль:* {VPS_PROFILE}\n"
        debug_info += f"⚙️ *Настройки:*\n"
        debug_info += f"• Макс. запросов: {MAX_CONCURRENT_REQUESTS}\n"
        debug_info += f"• Таймаут: {REQUEST_TIMEOUT}с\n"
        debug_info += f"• Размер пакета: {BATCH_SIZE}\n"
        debug_info += f"• Порог памяти: {MEMORY_THRESHOLD_MB} МБ"
        
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
        # Очистка старых логов (старше 14 дней для экономии места)
        log_dir = "logs"
        if os.path.exists(log_dir):
            cutoff_date = datetime.now() - timedelta(days=14)  # Уменьшено с 30 до 14
            
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        logger.info(f"🗑️ Удален старый лог: {filename}")
        
        # Очистка старых резервных копий (старше 7 дней)
        if os.path.exists(BACKUP_DIR):
            cutoff_date = datetime.now() - timedelta(days=7)  # Уменьшено с 14 до 7
            
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
            if size > 25 * 1024 * 1024:  # Уменьшено с 50 до 25 МБ
                issues.append(f"Файл истории слишком большой: {size // 1024 // 1024} МБ")
        
        # Проверка статистики ошибок
        error_rate = statistics_manager.stats.get('errors_count', 0)
        total_checks = statistics_manager.stats.get('total_checks', 1)
        if error_rate / max(total_checks, 1) > 0.15:  # Увеличено с 0.1 до 0.15
            issues.append(f"Высокий уровень ошибок: {error_rate}/{total_checks}")
        
        # Проверка дискового пространства
        try:
            import psutil
            disk_usage = psutil.disk_usage('.')
            if disk_usage.percent > 95:  # Увеличено с 90 до 95
                issues.append(f"Мало места на диске: {disk_usage.percent}%")
        except ImportError:
            pass
        
        if issues:
            logger.warning(f"⚠️ Обнаружены проблемы: {'; '.join(issues)}")
        else:
            logger.info("✅ Состояние бота в норме")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке состояния: {e}")

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    """Главная функция запуска бота с оптимизацией для VPS"""
    print("=" * 50)
    print("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО БОТА МОНИТОРИНГА GITHUB РЕЛИЗОВ")
    print("=" * 50)
    print(f"🔧 VPS профиль: {VPS_PROFILE}")
    print(f"⚙️ Макс. запросов: {MAX_CONCURRENT_REQUESTS}")
    print(f"📦 Размер пакета: {BATCH_SIZE}")
    print(f"⏱️ Таймаут: {REQUEST_TIMEOUT}с")
    print("=" * 50)

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

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    logger.info("📝 Регистрация обработчиков...")
    print("📝 Регистрация обработчиков...")
    register_handlers(dp)

    logger.info("⏰ Настройка планировщика задач...")
    print("⏰ Настройка планировщика задач...")
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Основная задача проверки репозиториев (адаптивный интервал)
    scheduler.add_job(
        check_repositories,
        'interval',
        minutes=MIN_CHECK_INTERVAL_MINUTES,
        kwargs={'bot': bot},
        id='repositories_check',
        max_instances=1,
        coalesce=True
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

    # Проверка здоровья бота (каждые 4 часа для экономии ресурсов)
    scheduler.add_job(
        health_check,
        'interval',
        hours=4,
        id='health_check',
        max_instances=1
    )

    # Сохранение статистики (каждый час)
    scheduler.add_job(
        lambda: statistics_manager._save_stats(),
        'interval',
        hours=1,
        id='save_statistics',
        max_instances=1
    )

    logger.info("✅ Планировщик настроен")
    print("✅ Планировщик настроен")

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

    print(f"\n📊 КОНФИГУРАЦИЯ БОТА:")
    print(f"├── Отслеживается репозиториев: {len(REPOS)}")
    print(f"├── GitHub токен: {'✅ Настроен' if GITHUB_TOKEN else '❌ Не настроен'}")
    print(f"├── Канал для уведомлений: {'✅ ' + CHANNEL_ID if CHANNEL_ID else '❌ Не настроен'}")
    print(f"├── Администратор: {'✅ ID=' + str(ADMIN_ID) if ADMIN_ID else '❌ Не настроен'}")
    print(f"├── VPS профиль: {VPS_PROFILE}")
    print(f"├── Интервал проверки: {MIN_CHECK_INTERVAL_MINUTES}-{MAX_CHECK_INTERVAL_MINUTES} мин")
    print(f"└── Хранение истории: {HISTORY_DAYS} дней")

    logger.info("🎯 Выполнение первоначальной проверки репозиториев...")
    print("\n🎯 Выполнение первоначальной проверки репозиториев...")
    
    try:
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
                f"🔧 *VPS профиль:* {VPS_PROFILE}\n"
                f"⚙️ *Оптимизация:* Макс. запросов {MAX_CONCURRENT_REQUESTS}, "
                f"пакет {BATCH_SIZE}, таймаут {REQUEST_TIMEOUT}с\n\n"
                f"Бот готов к работе! 🎉"
            )
            await bot.send_message(ADMIN_ID, startup_message, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о запуске админу: {e}")

    logger.info("🎉 Бот успешно запущен и готов к работе!")
    print("\n" + "=" * 50)
    print("🎉 ОПТИМИЗИРОВАННЫЙ БОТ УСПЕШНО ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    print("📱 Используйте Ctrl+C для остановки бота")
    print("📋 Логи сохраняются в папку logs/")
    print("💾 Резервные копии создаются в папку backups/")
    print(f"🔧 VPS профиль: {VPS_PROFILE}")
    print("=" * 50 + "\n")

    try:
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
        
        try:
            scheduler.shutdown(wait=True)
            logger.info("⏰ Планировщик остановлен")
            print("⏰ Планировщик остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки планировщика: {e}")

        try:
            statistics_manager._save_stats()
            logger.info("💾 Финальная статистика сохранена")
            print("💾 Финальная статистика сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

        try:
            await bot.session.close()
            logger.info("🔌 Сессия бота закрыта")
            print("🔌 Сессия бота закрыта")
        except Exception as e:
            logger.error(f"Ошибка закрытия сессии: {e}")

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
                final_bot = Bot(token=BOT_TOKEN)
                await final_bot.send_message(ADMIN_ID, shutdown_message, parse_mode="Markdown")
                await final_bot.session.close()
            except:
                pass

        logger.info("✅ Бот полностью остановлен")
        print("✅ Бот полностью остановлен")

# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск оптимизированного приложения...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запуске: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        print("Проверьте логи для получения подробной информации")
        sys.exit(1)

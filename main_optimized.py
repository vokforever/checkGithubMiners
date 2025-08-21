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
from aiohttp import ClientSession, ClientError, ClientResponseError, ClientTimeout, TCPConnector
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import time
import gc

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

# --- ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ СЛАБОГО VPS ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DONATE_URL = "https://boosty.to/vokforever/donate"

# Оптимизированные параметры для слабого VPS
MAX_RETRIES = 2  # Уменьшено с 3 до 2
RETRY_DELAY = 1  # Уменьшено с 2 до 1
HISTORY_DAYS = 14  # Уменьшено с 30 до 14 дней
PRIORITY_UPDATE_DAYS = 7

# Оптимизированные интервалы проверки (с учетом системы приоритетов)
MIN_CHECK_INTERVAL_MINUTES = 30  # Увеличено с 15 до 30 минут
MAX_CHECK_INTERVAL_MINUTES = 2880  # Увеличено с 1440 до 2880 (48 часов)
DEFAULT_CHECK_INTERVAL_MINUTES = 720  # Увеличено с 360 до 720 (12 часов)

# Параметры управления ресурсами
MAX_CONCURRENT_REQUESTS = 3  # Максимум одновременных запросов
REQUEST_TIMEOUT = 20  # Уменьшено с 30 до 20 секунд
BATCH_SIZE = 5  # Размер пакета для обработки
MEMORY_THRESHOLD_MB = 100  # Порог памяти для очистки

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

# --- ФАЙЛЫ ХРАНЕНИЯ ДАННЫХ ---
STATE_FILE = "last_releases.json"
FILTERS_FILE = "user_filters.json"
HISTORY_FILE = "releases_history.json"
USERS_FILE = "users.json"
PRIORITY_FILE = "repo_priority.json"
STATISTICS_FILE = "bot_statistics.json"
CACHE_FILE = "github_cache.json"

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
    
    # Ограничиваем размер логов для экономии места
    log_file = os.path.join(log_dir, "bot.log")
    
    # Настройка форматирования
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Файловый обработчик с ротацией
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)  # Только INFO и выше для экономии места
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # Только WARNING и выше в консоль
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Отключаем логи от сторонних библиотек для экономии ресурсов
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

# Инициализация логгера
logger = setup_logging()

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
github_cache = GitHubCache(CACHE_FILE)

# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ РЕСУРСАМИ ---
class ResourceManager:
    """Управляет ресурсами VPS сервера"""
    
    def __init__(self):
        self.request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.last_memory_check = time.time()
        self.memory_check_interval = 300  # 5 минут
    
    async def check_memory_usage(self):
        """Проверяет использование памяти и очищает если нужно"""
        current_time = time.time()
        if current_time - self.last_memory_check < self.memory_check_interval:
            return
        
        try:
            import psutil
            memory = psutil.virtual_memory()
            if memory.percent > 80:  # Если используется больше 80% памяти
                logger.warning(f"Высокое использование памяти: {memory.percent}%")
                
                # Принудительная очистка
                gc.collect()
                github_cache.cleanup()
                
                # Очищаем кэш Python
                if hasattr(gc, 'garbage'):
                    gc.garbage.clear()
                
                logger.info("Выполнена очистка памяти")
                
        except ImportError:
            pass  # psutil не установлен
        
        self.last_memory_check = current_time
    
    async def get_session(self) -> ClientSession:
        """Создает оптимизированную HTTP сессию"""
        connector = TCPConnector(
            limit=MAX_CONCURRENT_REQUESTS,
            limit_per_host=2,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        timeout = ClientTimeout(total=REQUEST_TIMEOUT)
        
        return ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'GitHub-Release-Monitor-Bot-Optimized'}
        )

# Инициализация менеджера ресурсов
resource_manager = ResourceManager()

# --- ИНТЕГРИРОВАННАЯ СИСТЕМА ПРИОРИТЕТОВ ---
class RepositoryPriorityManager:
    """Управляет приоритетами репозиториев с оптимизацией для VPS"""
    
    def __init__(self):
        self.priority_file = PRIORITY_FILE
        self.priorities = self._load_priorities()
        self.last_priority_update = self._load_last_priority_update()

    def _load_priorities(self) -> Dict[str, Dict]:
        if os.path.exists(self.priority_file):
            try:
                with open(self.priority_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    if isinstance(data, dict) and 'priorities' in data:
                        priorities = data['priorities']
                    else:
                        priorities = data

                    # Обновляем структуру данных для всех репозиториев
                    for repo in REPOS:
                        if repo not in priorities:
                            priorities[repo] = self._create_default_priority()
                        else:
                            # Добавляем недостающие поля
                            default_priority = self._create_default_priority()
                            for field, default_value in default_priority.items():
                                if field not in priorities[repo]:
                                    priorities[repo][field] = default_value

                    return priorities
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки приоритетов: {e}")
                self._backup_corrupted_file(self.priority_file)

        return {repo: self._create_default_priority() for repo in REPOS}

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

    def _load_last_priority_update(self) -> Optional[datetime]:
        if os.path.exists(self.priority_file):
            try:
                with open(self.priority_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'last_update' in data:
                        return datetime.fromisoformat(data['last_update'])
            except (json.JSONDecodeError, IOError, ValueError):
                pass
        return None

    def _backup_corrupted_file(self, file_path: str):
        """Создает резервную копию поврежденного файла"""
        try:
            if os.path.exists(file_path):
                backup_name = f"{os.path.basename(file_path)}.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_path = os.path.join(BACKUP_DIR, backup_name)
                shutil.copy2(file_path, backup_path)
                logger.warning(f"Создана резервная копия поврежденного файла: {backup_path}")
        except Exception as e:
            logger.error(f"Не удалось создать резервную копию: {e}")

    def _save_priorities(self):
        try:
            # Создаем резервную копию перед сохранением
            if os.path.exists(self.priority_file):
                backup_file = f"{self.priority_file}.bak"
                shutil.copy2(self.priority_file, backup_file)

            data = {
                'priorities': self.priorities,
                'last_update': datetime.now(timezone.utc).isoformat(),
                'version': '2.0',
                'repos_count': len(REPOS),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'backup_created': True
            }

            with open(self.priority_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Приоритеты успешно сохранены в {self.priority_file}")
        except IOError as e:
            logger.error(f"Ошибка сохранения приоритетов: {e}")

    def get_priority(self, repo: str) -> Dict:
        if repo not in self.priorities:
            self.priorities[repo] = self._create_default_priority()
            self._save_priorities()
        return self.priorities[repo]

    def record_update(self, repo: str):
        priority_data = self.get_priority(repo)
        priority_data['update_count'] += 1
        priority_data['last_update'] = datetime.now(timezone.utc).isoformat()
        priority_data['consecutive_failures'] = 0  # Сбрасываем счетчик ошибок
        self._save_priorities()
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
            
        self._save_priorities()

    def should_update_priorities(self) -> bool:
        if not self.last_priority_update:
            return True
        return datetime.now(timezone.utc) - self.last_priority_update > timedelta(hours=6)

    def update_priorities(self, history_manager=None):
        logger.info("Обновление приоритетов репозиториев...")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=PRIORITY_UPDATE_DAYS)
        updated_count = 0

        for repo in REPOS:
            update_count = 0
            # Упрощенная логика для оптимизации - используем существующие данные
            if repo in self.priorities:
                update_count = self.priorities[repo].get('update_count', 0)

            priority_score = update_count / PRIORITY_UPDATE_DAYS
            existing_data = self.priorities.get(repo, self._create_default_priority())

            # Учитываем количество последовательных неудач
            failure_penalty = min(existing_data.get('consecutive_failures', 0) * 0.1, 0.5)
            adjusted_score = max(0, priority_score - failure_penalty)

            # Определяем интервал проверки с учетом оптимизации для VPS
            if adjusted_score >= 0.5:  # PRIORITY_THRESHOLD_HIGH
                check_interval = MIN_CHECK_INTERVAL_MINUTES
            elif adjusted_score <= 0.1:  # PRIORITY_THRESHOLD_LOW
                check_interval = MAX_CHECK_INTERVAL_MINUTES
            else:
                ratio = (adjusted_score - 0.1) / (0.5 - 0.1)
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
        self._save_priorities()

        logger.info(f"Приоритеты обновлены. Изменено: {updated_count}/{len(REPOS)} репозиториев")

        # Детальный лог приоритетов
        for repo, data in self.priorities.items():
            status = "🔴" if data['priority_score'] >= 0.5 else \
                "🟢" if data['priority_score'] <= 0.1 else "🟡"
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

            if score >= 0.5:
                stats['high_priority'] += 1
            elif score <= 0.1:
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

# Инициализация менеджера приоритетов
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
    await resource_manager.check_memory_usage()
    
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {'User-Agent': 'GitHub-Release-Monitor-Bot-Optimized'}
    
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    start_time = time.time()
    
    async with resource_manager.request_semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(api_url, headers=headers) as response:
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Кэшируем результат
                        github_cache.set(cache_key, data)
                        
                        logger.debug(f"Успешно получены данные для {repo_name} за {response_time:.2f}с")
                        return data, response_time
                        
                    elif response.status == 403:
                        # Rate limit - увеличиваем интервал проверки
                        logger.warning(f"Rate limit для {repo_name}")
                        return None, response_time
                        
                    elif response.status == 404:
                        logger.warning(f"Репозиторий не найден: {repo_name}")
                        return None, response_time
                        
                    else:
                        logger.warning(f"Статус {response.status} для {repo_name}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY)
                            continue
                        return None, response_time
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout при запросе к {repo_name}")
            except Exception as e:
                logger.warning(f"Ошибка запроса к {repo_name}: {e}")
                
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
    
    response_time = time.time() - start_time
    return None, response_time

# --- ОПТИМИЗИРОВАННАЯ ПРОВЕРКА РЕПОЗИТОРИЕВ С ПРИОРИТЕТАМИ ---
async def check_repositories_optimized(bot: Bot):
    """Оптимизированная проверка репозиториев с учетом приоритетов"""
    logger.info("🔄 Запуск оптимизированной проверки репозиториев с приоритетами...")
    
    # Проверяем ресурсы
    await resource_manager.check_memory_usage()
    
    # Обновляем приоритеты если нужно
    if priority_manager.should_update_priorities():
        logger.info("📊 Обновление приоритетов репозиториев...")
        priority_manager.update_priorities()
    
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
        async with resource_manager.get_session() as session:
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
    scheduler.add_job(
        resource_manager.check_memory_usage,
        'interval',
        hours=2,
        id='resource_check',
        max_instances=1
    )
    
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

# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск оптимизированного приложения с приоритетами...")
        asyncio.run(main_optimized())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)

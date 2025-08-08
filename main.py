import asyncio
import json
import os
import logging
import sys
import locale
import ctypes
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Set
from aiohttp import ClientSession, ClientError, ClientResponseError
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- НАСТРОЙКА КОДИРОВКИ ДЛЯ WINDOWS ---
if sys.platform == "win32":
    # Включаем поддержку UTF-8 в консоли Windows
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

    # Пытаемся установить кодовую страницу консоли на UTF-8
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
    except:
        pass

# Загрузка переменных окружения
load_dotenv()

# --- НАСТРОЙКИ ИЗ .ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
# BASE_CHECK_INTERVAL_MINUTES убираем, чтобы система была полностью адаптивной
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
DEFAULT_CHECK_INTERVAL_MINUTES = 360  # 6 часов - средний интервал для новых репозиториев

# --- ФАЙЛЫ ХРАНЕНИЯ ДАННЫХ ---
STATE_FILE = "last_releases.json"
FILTERS_FILE = "user_filters.json"
HISTORY_FILE = "releases_history.json"
USERS_FILE = "users.json"
PRIORITY_FILE = "repo_priority.json"

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ ПРИОРИТЕТАМИ РЕПОЗИТОРИЕВ ---
class RepositoryPriorityManager:
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

                    for repo in REPOS:
                        if repo not in priorities:
                            priorities[repo] = self._create_default_priority()
                        else:
                            for field in ['update_count', 'last_update', 'check_interval', 'priority_score',
                                          'last_check']:
                                if field not in priorities[repo]:
                                    priorities[repo][field] = 0 if field == 'update_count' else None

                    return priorities
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки приоритетов: {e}")
                logger.info("Создание новых приоритетов по умолчанию")

        return {repo: self._create_default_priority() for repo in REPOS}

    def _create_default_priority(self) -> Dict:
        return {
            'update_count': 0,
            'last_update': None,
            'check_interval': DEFAULT_CHECK_INTERVAL_MINUTES,  # Используем средний интервал по умолчанию
            'priority_score': 0.0,
            'last_check': None
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

    def _save_priorities(self):
        try:
            data = {
                'priorities': self.priorities,
                'last_update': datetime.now(timezone.utc).isoformat(),
                'version': '1.0',
                'repos_count': len(REPOS),
                'created_at': datetime.now(timezone.utc).isoformat()
            }

            if os.path.exists(self.priority_file):
                backup_file = f"{self.priority_file}.bak"
                try:
                    import shutil
                    shutil.copy2(self.priority_file, backup_file)
                except Exception as e:
                    logger.warning(f"Не удалось создать резервную копию: {e}")

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
        self._save_priorities()
        logger.debug(f"Зарегистрировано обновление для {repo}. Всего обновлений: {priority_data['update_count']}")

    def should_update_priorities(self) -> bool:
        if not self.last_priority_update:
            return True
        return datetime.now(timezone.utc) - self.last_priority_update > timedelta(days=1)

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

            if priority_score >= PRIORITY_THRESHOLD_HIGH:
                check_interval = MIN_CHECK_INTERVAL_MINUTES
            elif priority_score <= PRIORITY_THRESHOLD_LOW:
                check_interval = MAX_CHECK_INTERVAL_MINUTES
            else:
                ratio = (priority_score - PRIORITY_THRESHOLD_LOW) / (PRIORITY_THRESHOLD_HIGH - PRIORITY_THRESHOLD_LOW)
                check_interval = int(
                    MAX_CHECK_INTERVAL_MINUTES - ratio * (MAX_CHECK_INTERVAL_MINUTES - MIN_CHECK_INTERVAL_MINUTES))

            existing_data = self.priorities.get(repo, {})
            last_check = existing_data.get('last_check')

            new_priority_data = {
                'update_count': update_count,
                'last_update': existing_data.get('last_update'),
                'check_interval': check_interval,
                'priority_score': round(priority_score, 3),
                'last_check': last_check
            }

            if (repo not in self.priorities or
                    self.priorities[repo]['check_interval'] != check_interval or
                    abs(self.priorities[repo]['priority_score'] - priority_score) > 0.001):
                updated_count += 1

            self.priorities[repo] = new_priority_data

        self.last_priority_update = datetime.now(timezone.utc)
        self._save_priorities()

        logger.info(f"Приоритеты обновлены. Изменено: {updated_count}/{len(REPOS)} репозиториев")

        for repo, data in self.priorities.items():
            status = "🔴" if data['priority_score'] >= PRIORITY_THRESHOLD_HIGH else \
                "🟢" if data['priority_score'] <= PRIORITY_THRESHOLD_LOW else "🟡"
            logger.info(
                f"{status} {repo}: интервал {data['check_interval']} мин, приоритет {data['priority_score']:.3f}")

    def get_priority_stats(self) -> Dict:
        stats = {
            'high_priority': 0,
            'medium_priority': 0,
            'low_priority': 0,
            'total_repos': len(REPOS)
        }

        for repo in REPOS:
            priority_data = self.get_priority(repo)
            score = priority_data['priority_score']

            if score >= PRIORITY_THRESHOLD_HIGH:
                stats['high_priority'] += 1
            elif score <= PRIORITY_THRESHOLD_LOW:
                stats['low_priority'] += 1
            else:
                stats['medium_priority'] += 1

        return stats


# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ---
class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.users = self._load_users()

    def _load_users(self) -> Set[int]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка загрузки пользователей: {e}")
        return set()

    def _save_users(self):
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.users), f, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Ошибка сохранения пользователей: {e}")

    def add_user(self, user_id: int):
        if user_id not in self.users:
            self.users.add(user_id)
            self._save_users()
            logger.info(f"Новый пользователь: {user_id}")

    def get_count(self) -> int:
        return len(self.users)


# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ СОСТОЯНИЕМ РЕЛИЗОВ ---
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
        return {}

    def _save_state(self):
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

    def update_tag(self, repo: str, tag: str):
        self.state[repo] = tag
        self._save_state()

    def get_last_tag(self, repo: str) -> Optional[str]:
        return self.state.get(repo)


# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ ФИЛЬТРАМИ ---
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
            with open(self.filters_file, 'w', encoding='utf-8') as f:
                json.dump(self.filters, f, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Ошибка сохранения фильтров: {e}")

    def set_filters(self, user_id: str, keywords: List[str]):
        self.filters[user_id] = keywords
        self._save_filters()

    def get_filters(self, user_id: str) -> List[str]:
        return self.filters.get(user_id, [])

    def clear_filters(self, user_id: str):
        if user_id in self.filters:
            del self.filters[user_id]
            self._save_filters()

    def get_users_with_filters_count(self) -> int:
        return len(self.filters)


# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ ИСТОРИЕЙ РЕЛИЗОВ ---
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

            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_history, f, ensure_ascii=False, indent=2)
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
                'body': release.get('body'),
                'assets': release.get('assets', [])
            }
            self.history.append(history_entry)
            self._save_history()
            logger.info(f"Добавлен релиз в историю: {repo_name} {release.get('tag_name')}")

    def get_releases_by_date(self, target_date) -> List[Dict]:
        logger.info(f"Ищем релизы за дату: {target_date}")

        result = []
        for rel in self.history:
            try:
                # Преобразуем дату публикации в UTC и сравниваем с целевой датой
                pub_date_str = rel['published_at']
                if pub_date_str.endswith('Z'):
                    pub_date_str = pub_date_str[:-1] + '+00:00'

                pub_date = datetime.fromisoformat(pub_date_str).astimezone(timezone.utc).date()
                logger.info(f"Релиз {rel['repo_name']} {rel['tag_name']} опубликован {pub_date} (цель: {target_date})")

                if pub_date == target_date:
                    result.append(rel)
            except Exception as e:
                logger.error(f"Ошибка при обработке даты релиза {rel['repo_name']} {rel['tag_name']}: {e}")

        logger.info(f"Найдено {len(result)} релизов за дату {target_date}")
        return result

    def get_recent_releases(self, days: int = 3) -> List[Dict]:
        cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=days)
        releases = [
            rel for rel in self.history
            if datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00')).date() >= cutoff_date
        ]
        return sorted(releases, key=lambda x: x['published_at'], reverse=True)

    def get_count(self) -> int:
        return len(self.history)


# --- ИНИЦИАЛИЗАЦИЯ МЕНЕДЖЕРОВ ---
user_manager = UserManager()
state_manager = ReleaseStateManager()
filter_manager = FilterManager()
history_manager = ReleaseHistoryManager()
priority_manager = RepositoryPriorityManager()


# --- ЗАГРУЗКА ИНФЫ О РЕЛИЗАХ ---
async def fetch_release(session: ClientSession, repo_name: str) -> Optional[Dict]:
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(api_url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 403:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    current_time = int(datetime.now().timestamp())
                    wait_time = max(reset_time - current_time, 60)
                    logger.warning(f"Rate limit exceeded. Waiting {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status == 404:
                    logger.error(f"Repository not found via API: {repo_name}")
                    return None
                else:
                    logger.error(f"Unexpected status {response.status} for {repo_name}")
                    return None
        except (ClientError, ClientResponseError) as e:
            logger.error(f"Request failed (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return None
    return None


# --- ПРОВЕРКА СООТВЕТСТВИЯ ФИЛЬТРАМ ---
def matches_filters(release_data: dict, keywords: List[str]) -> bool:
    if not keywords:
        return True

    search_text = " ".join([
        release_data.get('name', ''),
        release_data.get('tag_name', ''),
        release_data.get('body', '')
    ]).lower()

    return all(keyword.lower() in search_text for keyword in keywords)


# --- ЭКРАНИРОВАНИЕ СИМВОЛОВ MARKDOWN ---
def escape_markdown(text: str) -> str:
    escape_chars = '_*`[]()'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)


# --- ФОРМАТИРОВАНИЕ СООБЩЕНИЯ ---
def format_release_message(repo_name: str, release: Dict) -> str:
    tag = release.get('tag_name', 'Unknown')
    name = release.get('name', tag)
    body = release.get('body', '')
    published_at = release.get('published_at', '')
    assets = release.get('assets', [])

    repo_name_escaped = escape_markdown(repo_name)
    name_escaped = escape_markdown(name)
    tag_escaped = escape_markdown(tag)

    message = (
        f"🚀 *Новый релиз в репозитории {repo_name_escaped}*\n\n"
        f"*{name_escaped}*\n"
        f"`{tag_escaped}`\n"
    )

    if published_at:
        try:
            pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            message += f"📅 {pub_date.strftime('%Y-%m-%d %H:%M')}\n\n"
        except:
            message += "\n"
    else:
        message += "\n"

    if body:
        body_escaped = escape_markdown(body[:1000])
        message += f"{body_escaped}{'...' if len(body) > 1000 else ''}\n\n"

    links = []
    for asset in assets:
        asset_name = asset.get('name', '')
        download_url = asset.get('browser_download_url', '')
        if asset_name and download_url and not asset_name.startswith("Source code"):
            asset_name_escaped = escape_markdown(asset_name)
            links.append(f"[{asset_name_escaped}]({download_url})")

    if links:
        message += "📥 *Ссылки для скачивания:*\n" + "\n".join(links)
    else:
        message += "⚠️ Файлы для скачивания не найдены"

    return message


# --- ОТПРАВКА УВЕДОМЛЕНИЙ ---
async def send_notifications(bot: Bot, repo_name: str, release: Dict):
    message = format_release_message(repo_name, release)
    notified_users = set()

    for user_id, filters in filter_manager.filters.items():
        if matches_filters(release, filters):
            try:
                await bot.send_message(user_id, message, parse_mode="Markdown")
                notified_users.add(user_id)
                logger.info(f"Уведомление отправлено пользователю {user_id} для {repo_name}")
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

    if not notified_users and CHANNEL_ID:
        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"Уведомление отправлено в канал для {repo_name}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в канал: {e}")


# --- ПРОВЕРКА ОДНОГО РЕПОЗИТОРИЯ ---
async def check_single_repo(bot: Bot, repo_name: str):
    logger.info(f"Проверка репозитория: {repo_name}")

    try:
        async with ClientSession() as session:
            release = await fetch_release(session, repo_name)

            if not release:
                logger.warning(f"Не получены данные о релизах для {repo_name}")
                return

            current_tag = release.get('tag_name')
            if not current_tag:
                logger.warning(f"Не найден тег в данных релиза для {repo_name}")
                return

            last_tag = state_manager.get_last_tag(repo_name)
            logger.info(f"Текущий тег: {current_tag}, предыдущий: {last_tag}")

            if last_tag != current_tag:
                logger.info(f"Найден новый релиз: {current_tag}")

                history_manager.add_release(repo_name, release)
                priority_manager.record_update(repo_name)
                await send_notifications(bot, repo_name, release)
                state_manager.update_tag(repo_name, current_tag)

                logger.info(f"Успешно обработан новый релиз для {repo_name}")
            else:
                logger.info(f"Обновлений для {repo_name} не найдено")

    except Exception as e:
        logger.error(f"Ошибка при проверке репозитория {repo_name}: {str(e)}")
        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Ошибка при проверке репозитория {repo_name}: {str(e)}"
                )
            except:
                pass


# --- ПРОВЕРКА РЕПОЗИТОРИЕВ С УЧЕТОМ ПРИОРИТЕТОВ ---
async def check_repositories(bot: Bot):
    logger.info("Запуск проверки репозиториев с учетом приоритетов...")

    if priority_manager.should_update_priorities():
        priority_manager.update_priorities(history_manager)

    current_time = datetime.now(timezone.utc)

    for repo_name in REPOS:
        priority_data = priority_manager.get_priority(repo_name)
        check_interval = priority_data['check_interval']

        if priority_data.get('last_check'):
            last_check = datetime.fromisoformat(priority_data['last_check'])
            if current_time - last_check >= timedelta(minutes=check_interval):
                await check_single_repo(bot, repo_name)
                priority_data['last_check'] = current_time.isoformat()
                priority_manager._save_priorities()
        else:
            await check_single_repo(bot, repo_name)
            priority_data['last_check'] = current_time.isoformat()
            priority_manager._save_priorities()


# --- ПРИНУДИТЕЛЬНАЯ ПРОВЕРКА ВСЕХ РЕПОЗИТОРИЕВ ---
async def check_all_repositories(bot: Bot):
    logger.info("Запуск принудительной проверки всех репозиториев...")

    for repo_name in REPOS:
        await check_single_repo(bot, repo_name)
        priority_data = priority_manager.get_priority(repo_name)
        priority_data['last_check'] = datetime.now(timezone.utc).isoformat()
        priority_manager._save_priorities()


# --- КОМАНДА /start ---
async def start_command(message: Message):
    user_manager.add_user(message.from_user.id)
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")

    # Если пользователь - админ, показываем дополнительные команды
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👋 *Привет, Администратор!*\n\n"
            "📌 *Основные команды:*\n"
            "/filter - установить фильтры для уведомлений\n"
            "/myfilters - посмотреть текущие фильтры\n"
            "/clearfilters - очистить все фильтры\n"
            "/last - релизы за последние 3 дня\n"
            "/donate - поддержать разработчика\n"
            "/help - справка по использованию\n\n"
            "🔧 *Административные команды:*\n"
            "/priority - показать приоритеты репозиториев\n"
            "/pstats - статистика приоритетов\n"
            "/checkall - принудительно проверить все репозитории\n"
            "/stats - общая статистика бота"
        )
    else:
        await message.answer(
            "👋 Привет! Я бот для отслеживания релизов на GitHub.\n\n"
            "📌 *Основные команды:*\n"
            "/filter - установить фильтры для уведомлений\n"
            "/myfilters - посмотреть текущие фильтры\n"
            "/clearfilters - очистить все фильтры\n"
            "/last - релизы за последние 3 дня\n"
            "/donate - поддержать разработчика\n"
            "/help - справка по использованию"
        )

    recent_releases = history_manager.get_recent_releases(3)
    if recent_releases:
        await message.answer("📅 *Последние релизы за 3 дня:*\n")
        for rel in recent_releases:
            msg = format_release_message(rel['repo_name'], rel)
            await message.answer(msg, parse_mode="Markdown")
    else:
        await message.answer("📭 За последние 3 дня релизов не было.")


# --- КОМАНДА /priority ---
async def priority_command(message: Message):
    user_manager.add_user(message.from_user.id)

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    priority_info = "📊 *Приоритеты репозиториев:*\n\n"

    for repo in REPOS:
        priority_data = priority_manager.get_priority(repo)
        interval = priority_data['check_interval']
        score = priority_data['priority_score']

        if score >= PRIORITY_THRESHOLD_HIGH:
            status = "🔴 Высокий"
        elif score <= PRIORITY_THRESHOLD_LOW:
            status = "🟢 Низкий"
        else:
            status = "🟡 Средний"

        priority_info += f"{repo}: {status} (интервал: {interval} мин, приоритет: {score:.2f})\n"

    await message.answer(priority_info, parse_mode="Markdown")


# --- КОМАНДА /pstats ---
async def pstats_command(message: Message):
    user_manager.add_user(message.from_user.id)

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    stats = priority_manager.get_priority_stats()

    stats_message = (
        f"📊 *Статистика приоритетов репозиториев:*\n\n"
        f"🔴 Высокий приоритет: {stats['high_priority']}\n"
        f"🟡 Средний приоритет: {stats['medium_priority']}\n"
        f"🟢 Низкий приоритет: {stats['low_priority']}\n"
        f"📦 Всего репозиториев: {stats['total_repos']}\n\n"
        f"🔄 Последнее обновление: {priority_manager.last_priority_update.strftime('%Y-%m-%d %H:%M') if priority_manager.last_priority_update else 'Еще не обновлялось'}"
    )

    await message.answer(stats_message, parse_mode="Markdown")


# --- КОМАНДА /last ---
async def last_command(message: Message):
    user_manager.add_user(message.from_user.id)
    logger.info(f"Пользователь {message.from_user.id} запрашивает релизы за последние 3 дня")

    recent_releases = history_manager.get_recent_releases(3)

    if not recent_releases:
        await message.answer("📭 За последние 3 дня релизов не было.")
    else:
        await message.answer("📅 *Релизы за последние 3 дня:*\n")
        for rel in recent_releases:
            msg = format_release_message(rel['repo_name'], rel)
            await message.answer(msg, parse_mode="Markdown")


# --- КОМАНДА /checkall ---
async def checkall_command(message: Message):
    user_manager.add_user(message.from_user.id)

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    await message.answer("🔄 Запускаю проверку всех репозиториев...")
    try:
        await check_all_repositories(message.bot)
        await message.answer("✅ Проверка всех репозиториев завершена")
    except Exception as e:
        logger.error(f"Ошибка при проверке всех репозиториев: {e}")
        await message.answer(f"⚠️ Ошибка при проверке: {str(e)}")


# --- КОМАНДА /filter ---
async def filter_command(message: Message):
    user_manager.add_user(message.from_user.id)
    logger.info(f"Пользователь {message.from_user.id} хочет установить фильтры")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отмена", callback_data="cancel_filter")

    await message.answer(
        "🔍 *Настройка фильтров*\n\n"
        "Введите ключевые слова через пробел, по которым будет производиться фильтрация релизов.\n"
        "Например: `qubitcoin qtc`\n\n"
        "Бот будет искать совпадения в названиях релизов и описаниях.",
        reply_markup=keyboard.as_markup()
    )
    await message.answer("⏳ Ожидаю ввод ключевых слов...")


# --- ОБРАБОТКА КНОПКИ ОТМЕНЫ ---
async def cancel_filter_callback(callback: CallbackQuery):
    user_manager.add_user(callback.from_user.id)
    user_id = str(callback.from_user.id)
    logger.info(f"Пользователь {user_id} отменил установку фильтров")

    await callback.message.edit_text(
        "❌ *Настройка фильтров отменена*",
        reply_markup=None
    )
    await callback.answer()


# --- ОБРАБОТКА ТЕКСТА ПОСЛЕ /filter ---
async def process_filter_text(message: Message):
    user_manager.add_user(message.from_user.id)
    user_id = str(message.from_user.id)
    keywords = message.text.strip().split()

    logger.info(f"Пользователь {user_id} вводит фильтры: {keywords}")

    if not keywords:
        await message.answer("❌ Вы не ввели ключевые слова. Попробуйте снова.")
        return

    filter_manager.set_filters(user_id, keywords)
    await message.answer(
        f"✅ *Фильтры сохранены!*\n\n"
        f"Ключевые слова: {', '.join(keywords)}\n\n"
        "Теперь вы будете получать уведомления только о релизах, содержащих эти слова."
    )


# --- КОМАНДА /myfilters ---
async def myfilters_command(message: Message):
    user_manager.add_user(message.from_user.id)
    user_id = str(message.from_user.id)
    filters = filter_manager.get_filters(user_id)

    logger.info(f"Пользователь {user_id} запрашивает свои фильтры: {filters}")

    if not filters:
        await message.answer("📭 У вас нет установленных фильтров.")
    else:
        await message.answer(
            f"📋 *Ваши текущие фильтры:*\n\n"
            f"Ключевые слова: {', '.join(filters)}"
        )


# --- КОМАНДА /clearfilters ---
async def clearfilters_command(message: Message):
    user_manager.add_user(message.from_user.id)
    user_id = str(message.from_user.id)

    logger.info(f"Пользователь {user_id} очищает фильтры")

    if filter_manager.get_filters(user_id):
        filter_manager.clear_filters(user_id)
        await message.answer("🗑️ Ваши фильтры успешно удалены.")
    else:
        await message.answer("📭 У вас и так не было установленных фильтров.")


# --- КОМАНДА /stats ---
async def stats_command(message: Message):
    user_manager.add_user(message.from_user.id)

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    stats_message = (
        f"📊 *Статистика бота:*\n\n"
        f"👥 Всего пользователей: {user_manager.get_count()}\n"
        f"🔍 Пользователей с фильтрами: {filter_manager.get_users_with_filters_count()}\n"
        f"📦 Репозиториев отслеживается: {len(REPOS)}\n"
        f"📈 Релизов в истории: {history_manager.get_count()}"
    )

    await message.answer(stats_message, parse_mode="Markdown")


# --- КОМАНДА /donate ---
async def donate_command(message: Message):
    user_manager.add_user(message.from_user.id)
    logger.info(f"Пользователь {message.from_user.id} запросил информацию о донате")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💝 Поддержать разработчика", url=DONATE_URL)

    await message.answer(
        "💖 *Спасибо за интерес к поддержке моего проекта!*\n\n"
        "Если вам нравится мой бот и вы хотите помочь в его развитии, "
        "вы можете поддержать меня финансово. Любая сумма будет принята с благодарностью! 🙏\n\n"
        "Ваши пожертвования помогут:\n"
        "• Оплачивать сервер для работы бота 24/7\n"
        "• Разрабатывать новые функции\n"
        "• Улучшать существующий функционал\n\n"
        "Нажмите на кнопку ниже, чтобы перейти на страницу доната:",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


# --- КОМАНДА /help ---
async def help_command(message: Message):
    user_manager.add_user(message.from_user.id)
    logger.info(f"Пользователь {message.from_user.id} запрашивает помощь")

    # Если пользователь - админ, показываем дополнительные команды
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "📚 *Справка по использованию бота*\n\n"
            "🔍 *Фильтрация релизов:*\n"
            "1. Используйте команду /filter\n"
            "2. Введите ключевые слова через пробел\n"
            "3. Бот будет присылать только релизы, содержащие эти слова\n\n"
            "📋 *Команды управления фильтрами:*\n"
            "/filter - установить фильтры\n"
            "/myfilters - показать текущие фильтры\n"
            "/clearfilters - удалить все фильтры\n\n"
            "📅 *Просмотр релизов:*\n"
            "/last - показать релизы за последние 3 дня\n"
            "/start - показать последние релизы за 3 дня\n\n"
            "💝 *Поддержка проекта:*\n"
            "/donate - поддержать разработчика\n\n"
            "🔧 *Административные команды:*\n"
            "/priority - показать приоритеты репозиториев\n"
            "/pstats - статистика приоритетов\n"
            "/checkall - принудительно проверить все репозитории\n"
            "/stats - общая статистика бота\n\n"
            "📌 *Как работает фильтрация:*\n"
            "Бот ищет ключевые слова в:\n"
            "• Названии релиза\n"
            "• Теге версии\n"
            "• Описании релиза\n\n"
            "Пример: если вы введете 'qubitcoin qtc', бот будет присылать только релизы, где встречаются эти слова."
        )
    else:
        await message.answer(
            "📚 *Справка по использованию бота*\n\n"
            "🔍 *Фильтрация релизов:*\n"
            "1. Используйте команду /filter\n"
            "2. Введите ключевые слова через пробел\n"
            "3. Бот будет присылать только релизы, содержащие эти слова\n\n"
            "📋 *Команды управления фильтрами:*\n"
            "/filter - установить фильтры\n"
            "/myfilters - показать текущие фильтры\n"
            "/clearfilters - удалить все фильтры\n\n"
            "📅 *Просмотр релизов:*\n"
            "/last - показать релизы за последние 3 дня\n"
            "/start - показать последние релизы за 3 дня\n\n"
            "💝 *Поддержка проекта:*\n"
            "/donate - поддержать разработчика\n\n"
            "📌 *Как работает фильтрация:*\n"
            "Бот ищет ключевые слова в:\n"
            "• Названии релиза\n"
            "• Теге версии\n"
            "• Описании релиза\n\n"
            "Пример: если вы введете 'qubitcoin qtc', бот будет присылать только релизы, где встречаются эти слова."
        )


# --- РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ---
def register_handlers(dp: Dispatcher):
    print("Регистрация обработчиков...")
    dp.message.register(start_command, CommandStart())
    dp.message.register(filter_command, Command("filter"))
    dp.message.register(myfilters_command, Command("myfilters"))
    dp.message.register(clearfilters_command, Command("clearfilters"))
    dp.message.register(last_command, Command("last"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(stats_command, Command("stats"))
    dp.message.register(priority_command, Command("priority"))
    dp.message.register(pstats_command, Command("pstats"))
    dp.message.register(checkall_command, Command("checkall"))
    dp.message.register(donate_command, Command("donate"))
    dp.message.register(process_filter_text, F.text & ~F.command)
    dp.callback_query.register(cancel_filter_callback, F.data == "cancel_filter")
    print("Обработчики зарегистрированы")


# --- MAIN ---
async def main():
    print("=== Запуск бота ===")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в файле .env!")
        print("ОШИБКА: BOT_TOKEN не найден в файле .env!")
        return

    print("Инициализация бота...")
    bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
    dp = Dispatcher()

    print("Регистрация обработчиков...")
    register_handlers(dp)

    print("Настройка планировщика...")
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        check_repositories,
        'interval',
        minutes=15,
        kwargs={'bot': bot},
        id='repositories_check'
    )

    scheduler.add_job(
        lambda: priority_manager.update_priorities(history_manager),
        'interval',
        hours=24,
        id='priority_update'
    )

    scheduler.start()

    logger.info("Бот успешно запущен")
    print("=== Бот запущен и готов к работе ===")

    print("Запускаю первоначальную проверку репозиториев...")
    try:
        # Используем принудительную проверку всех репозиториев при запуске
        await check_all_repositories(bot)
        print("Первоначальная проверка репозиториев завершена")
    except Exception as e:
        logger.error(f"Ошибка при первоначальной проверке: {e}")
        print(f"ОШИБКА при первоначальной проверке: {e}")

    try:
        print("Начинаю получение обновлений...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске поллинга: {e}")
        print(f"ОШИБКА: {e}")
    finally:
        print("Завершение работы бота...")
        await bot.session.close()
        scheduler.shutdown()


if __name__ == "__main__":
    try:
        print("=== Запуск приложения ===")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        print("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
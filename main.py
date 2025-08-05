import asyncio
import json
import os
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Set
from aiohttp import ClientSession, ClientError
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# --- НАСТРОЙКИ ИЗ .ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)  # Можно задать токен прямо здесь: GITHUB_TOKEN = "ваш_токен"
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ID администратора
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))  # По умолчанию 60 минут
DONATE_URL = "https://boosty.to/vokforever/donate"  # Ссылка для доната

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
    "alephium/cpu-miner"
]

STATE_FILE = "last_releases.json"
FILTERS_FILE = "user_filters.json"
HISTORY_FILE = "releases_history.json"
USERS_FILE = "users.json"

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- ПРОВЕРКА КОНФИГУРАЦИИ ---
print("=== Проверка конфигурации ===")
print(f"BOT_TOKEN: {'Установлен' if BOT_TOKEN else 'ОТСУТСТВУЕТ'}")
print(f"CHANNEL_ID: {CHANNEL_ID if CHANNEL_ID else 'ОТСУТСТВУЕТ'}")
print(f"ADMIN_ID: {ADMIN_ID if ADMIN_ID else 'ОТСУТСТВУЕТ'}")
print(f"CHECK_INTERVAL_MINUTES: {CHECK_INTERVAL_MINUTES}")
print(f"Репозитории для отслеживания: {len(REPOS)}")
for i, repo in enumerate(REPOS, 1):
    print(f"  {i}. {repo}")

# --- ХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(list(users), f)

all_users = load_users()

def add_user(user_id):
    if user_id not in all_users:
        all_users.add(user_id)
        save_users(all_users)
        print(f"Новый пользователь: {user_id}")

# --- ХРАНЕНИЕ СОСТОЯНИЯ ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# --- ХРАНЕНИЕ ФИЛЬТРОВ ПОЛЬЗОВАТЕЛЕЙ ---
def load_filters():
    if os.path.exists(FILTERS_FILE):
        with open(FILTERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_filters(filters):
    with open(FILTERS_FILE, 'w') as f:
        json.dump(filters, f)

# --- ХРАНЕНИЕ ИСТОРИИ РЕЛИЗОВ ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(history):
    if history:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        filtered_history = []
        for rel in history:
            try:
                pub_date = datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00'))
                if pub_date >= thirty_days_ago:
                    filtered_history.append(rel)
            except:
                continue
        history = filtered_history
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

user_filters = load_filters()
releases_history = load_history()
print(f"Загружено фильтров для {len(user_filters)} пользователей")
print(f"Загружено записей в истории релизов: {len(releases_history)}")
print(f"Всего пользователей: {len(all_users)}")

# --- ЗАГРУЗКА ИНФЫ О РЕЛИЗАХ (API + HTML) ---
async def fetch_release(session, repo_name, max_retries=3):
    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    for attempt in range(max_retries):
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
                    break
        except ClientError as e:
            logger.error(f"Request failed: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

# --- ПРОВЕРКА СООТВЕТСТВИЯ ФИЛЬТРАМ ---
def matches_filters(release_data: dict, keywords: List[str]) -> bool:
    if not keywords:
        return True
    search_text = ""
    if release_data.get('name'):
        search_text += release_data['name'].lower() + " "
    if release_data.get('tag_name'):
        search_text += release_data['tag_name'].lower() + " "
    if release_data.get('body'):
        search_text += release_data['body'].lower() + " "
    for keyword in keywords:
        if keyword.lower() not in search_text:
            return False
    return True

# --- ЭКРАНИРОВАНИЕ СИМВОЛОВ MARKDOWN ---
def escape_markdown(text: str) -> str:
    escape_chars = '_*`[]()'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# --- ФОРМАТИРОВАНИЕ СООБЩЕНИЯ ---
def format_release_message(repo_name, release):
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
        body_escaped = escape_markdown(body)
        message += f"{body_escaped}\n\n"
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

# --- ДОБАВЛЕНИЕ РЕЛИЗА В ИСТОРИЮ ---
def add_to_history(repo_name, release):
    global releases_history
    exists = any(
        rel['repo_name'] == repo_name and rel['tag_name'] == release.get('tag_name')
        for rel in releases_history
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
        releases_history.append(history_entry)
        save_history(releases_history)
        print(f"Добавлен релиз в историю: {repo_name} {release.get('tag_name')}")

# --- ПОЛУЧЕНИЕ РЕЛИЗОВ ЗА ДАТУ ---
def get_releases_by_date(target_date):
    releases = []
    for rel in releases_history:
        try:
            pub_date = datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00')).date()
            if pub_date == target_date:
                releases.append(rel)
        except:
            continue
    return releases

# --- ПОЛУЧЕНИЕ РЕЛИЗОВ ЗА ПОСЛЕДНИЕ ДНИ ---
def get_recent_releases(days=3):
    releases = []
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=days)
    for rel in releases_history:
        try:
            pub_date = datetime.fromisoformat(rel['published_at'].replace('Z', '+00:00')).date()
            if pub_date >= cutoff_date:
                releases.append(rel)
        except:
            continue
    releases.sort(key=lambda x: x['published_at'], reverse=True)
    return releases

# --- ПРОВЕРКА ОБНОВЛЕНИЙ С ФИЛЬТРАЦИЕЙ ---
async def check_updates(bot: Bot):
    logger.info("Проверка обновлений...")
    print("=== Начинаю проверку обновлений ===")
    state = load_state()
    async with ClientSession() as session:
        for repo_name in REPOS:
            print(f"Проверяю репозиторий: {repo_name}")
            release = await fetch_release(session, repo_name)
            if not release:
                logger.warning(f"Не получены данные о релизах для {repo_name}")
                continue
            current_tag = release.get('tag_name')
            if not current_tag:
                logger.warning(f"Не найден тег в данных релиза для {repo_name}")
                continue
            last_tag = state.get(repo_name)
            print(f"Текущий тег: {current_tag}, предыдущий: {last_tag}")
            if last_tag != current_tag:
                print(f"Найден новый релиз: {current_tag}")
                add_to_history(repo_name, release)
                notified_users = set()
                for user_id, filters in user_filters.items():
                    if matches_filters(release, filters):
                        if user_id not in notified_users:
                            message = format_release_message(repo_name, release)
                            try:
                                await bot.send_message(user_id, message, parse_mode="Markdown")
                                notified_users.add(user_id)
                                logger.info(f"Уведомление отправлено пользователю {user_id} для {repo_name} {current_tag}")
                            except Exception as e:
                                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                if not notified_users and CHANNEL_ID:
                    message = format_release_message(repo_name, release)
                    try:
                        await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                        logger.info(f"Уведомление отправлено в канал для {repo_name} {current_tag}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения в канал: {e}")
                state[repo_name] = current_tag
    save_state(state)
    print("=== Проверка обновлений завершена ===")
    logger.info("Проверка обновлений завершена")

# --- КОМАНДА /start ---
async def start_command(message: Message):
    add_user(message.from_user.id)
    print(f"Получена команда /start от пользователя {message.from_user.id}")
    await message.answer(
        "👋 Привет! Я бот для отслеживания релизов на GitHub.\n\n"
        "📌 *Основные команды:*\n"
        "/filter - установить фильтры для уведомлений\n"
        "/myfilters - посмотреть текущие фильтры\n"
        "/clearfilters - очистить все фильтры\n"
        "/today - релизы за сегодня\n"
        "/donate - поддержать разработчика\n"
        "/help - справка по использованию"
    )
    recent_releases = get_recent_releases(3)
    if recent_releases:
        await message.answer("📅 *Последние релизы за 3 дня:*\n")
        for rel in recent_releases:
            msg = format_release_message(rel['repo_name'], rel)
            await message.answer(msg, parse_mode="Markdown")
    else:
        await message.answer("📭 За последние 3 дня релизов не было.")

# --- КОМАНДА /today ---
async def today_command(message: Message):
    add_user(message.from_user.id)
    print(f"Пользователь {message.from_user.id} запрашивает релизы за сегодня")
    today = datetime.now(timezone.utc).date()
    today_releases = get_releases_by_date(today)
    if not today_releases:
        await message.answer("📭 Сегодня релизов не было.")
    else:
        await message.answer("📅 *Релизы за сегодня:*\n")
        for rel in today_releases:
            msg = format_release_message(rel['repo_name'], rel)
            await message.answer(msg, parse_mode="Markdown")

# --- КОМАНДА /filter ---
async def filter_command(message: Message):
    add_user(message.from_user.id)
    print(f"Пользователь {message.from_user.id} хочет установить фильтры")
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
    add_user(callback.from_user.id)
    user_id = str(callback.from_user.id)
    print(f"Пользователь {user_id} отменил установку фильтров")
    await callback.message.edit_text(
        "❌ *Настройка фильтров отменена*",
        reply_markup=None
    )
    await callback.answer()

# --- ОБРАБОТКА ТЕКСТА ПОСЛЕ /filter ---
async def process_filter_text(message: Message):
    add_user(message.from_user.id)
    user_id = str(message.from_user.id)
    keywords = message.text.strip().split()
    print(f"Пользователь {user_id} вводит фильтры: {keywords}")
    if not keywords:
        await message.answer("❌ Вы не ввели ключевые слова. Попробуйте снова.")
        return
    user_filters[user_id] = keywords
    save_filters(user_filters)
    await message.answer(
        f"✅ *Фильтры сохранены!*\n\n"
        f"Ключевые слова: {', '.join(keywords)}\n\n"
        "Теперь вы будете получать уведомления только о релизах, содержащих эти слова."
    )

# --- КОМАНДА /myfilters ---
async def myfilters_command(message: Message):
    add_user(message.from_user.id)
    user_id = str(message.from_user.id)
    filters = user_filters.get(user_id, [])
    print(f"Пользователь {user_id} запрашивает свои фильтры: {filters}")
    if not filters:
        await message.answer("📭 У вас нет установленных фильтров.")
    else:
        await message.answer(
            f"📋 *Ваши текущие фильтры:*\n\n"
            f"Ключевые слова: {', '.join(filters)}"
        )

# --- КОМАНДА /clearfilters ---
async def clearfilters_command(message: Message):
    add_user(message.from_user.id)
    user_id = str(message.from_user.id)
    print(f"Пользователь {user_id} очищает фильтры")
    if user_id in user_filters:
        del user_filters[user_id]
        save_filters(user_filters)
        await message.answer("🗑️ Ваши фильтры успешно удалены.")
    else:
        await message.answer("📭 У вас и так не было установленных фильтров.")

# --- КОМАНДА /stats (только для админа) ---
async def stats_command(message: Message):
    add_user(message.from_user.id)
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return
    total_users = len(all_users)
    users_with_filters = len(user_filters)
    stats_message = (
        f"📊 *Статистика бота:*\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🔍 Пользователей с фильтрами: {users_with_filters}\n"
        f"📦 Репозиториев отслеживается: {len(REPOS)}\n"
        f"📈 Релизов в истории: {len(releases_history)}"
    )
    await message.answer(stats_message, parse_mode="Markdown")

# --- КОМАНДА /donate ---
async def donate_command(message: Message):
    add_user(message.from_user.id)
    print(f"Пользователь {message.from_user.id} запросил информацию о донате")
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
    add_user(message.from_user.id)
    print(f"Пользователь {message.from_user.id} запрашивает помощь")
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
        "/today - показать релизы за сегодня\n"
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
    dp.message.register(today_command, Command("today"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(stats_command, Command("stats"))
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
    if CHANNEL_ID and CHANNEL_ID.startswith("@https://"):
        logger.warning("Неправильный формат CHANNEL_ID! Используйте @username или числовой ID канала.")
        print(f"ПРЕДУПРЕЖДЕНИЕ: Неправильный формат CHANNEL_ID: {CHANNEL_ID}")
        print("Используйте @username канала (например, @mychannel) или числовой ID (например, -1001234567890)")
    print("Инициализация бота...")
    bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
    dp = Dispatcher()
    print("Регистрация обработчиков...")
    register_handlers(dp)
    print("Настройка планировщика...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_updates,
        'interval',
        minutes=CHECK_INTERVAL_MINUTES,
        kwargs={'bot': bot},
        id='github_release_check'
    )
    scheduler.start()
    logger.info("Бот успешно запущен")
    print("=== Бот запущен и готов к работе ===")
    print("Запускаю первоначальную проверку релизов...")
    try:
        await check_updates(bot)
        print("Первоначальная проверка релизов завершена")
    except Exception as e:
        logger.error(f"Ошибка при первоначальной проверке релизов: {e}")
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
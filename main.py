import asyncio
import json
import os
import logging
import re
import sys
from datetime import datetime
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))

REPOS = [
    "https://github.com/andru-kun/wildrig-multi/releases",
    "https://github.com/OneZeroMiner/onezerominer/releases"
]

STATE_FILE = "last_releases.json"
FILTERS_FILE = "user_filters.json"

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

# Проверка наличия необходимых переменных окружения
print("=== Проверка конфигурации ===")
print(f"BOT_TOKEN: {'Установлен' if BOT_TOKEN else 'ОТСУТСТВУЕТ'}")
print(f"CHANNEL_ID: {CHANNEL_ID if CHANNEL_ID else 'ОТСУТСТВУЕТ'}")
print(f"CHECK_INTERVAL_MINUTES: {CHECK_INTERVAL_MINUTES}")
print(f"Репозитории для отслеживания: {len(REPOS)}")
for i, repo in enumerate(REPOS, 1):
    print(f"  {i}. {repo}")


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


# Глобальное хранилище фильтров
user_filters = load_filters()
print(f"Загружено фильтров для {len(user_filters)} пользователей")


# --- ПАРСИНЧИК HTML СТРАНИЦЫ РЕЛИЗОВ ---
async def parse_html_releases(session, repo_url):
    try:
        async with session.get(repo_url) as response:
            if response.status != 200:
                return None

            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            release_section = soup.find('section', {'class': 'release-entry'})
            if not release_section:
                return None

            release_data = {}

            tag_element = release_section.find('a', {'class': 'Link--primary'})
            if tag_element:
                release_data['tag_name'] = tag_element.get_text(strip=True)

            name_element = release_section.find('div', {'class': 'release-main-section'})
            if name_element:
                h1 = name_element.find('h1')
                if h1:
                    release_data['name'] = h1.get_text(strip=True)

            date_element = release_section.find('relative-time')
            if date_element:
                release_data['published_at'] = date_element.get('datetime')

            desc_element = release_section.find('div', {'class': 'markdown-body'})
            if desc_element:
                release_data['body'] = desc_element.get_text(strip=True)

            assets = []
            asset_links = release_section.find_all('a', {'href': re.compile(r'/releases/download/')})
            for link in asset_links:
                asset_name = link.get_text(strip=True)
                if not asset_name.startswith("Source code"):
                    asset_url = "https://github.com" + link['href']
                    assets.append({
                        'name': asset_name,
                        'browser_download_url': asset_url
                    })

            release_data['assets'] = assets
            return release_data

    except Exception as e:
        logger.error(f"HTML parsing failed for {repo_url}: {e}")
        return None


# --- ЗАГРУЗКА ИНФЫ О РЕЛИЗАХ (API + HTML) ---
async def fetch_release(session, repo_url, max_retries=3):
    api_url = repo_url.replace("https://github.com/", "https://api.github.com/repos/") + "/latest"
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
                    logger.error(f"Repository not found via API: {repo_url}")
                    break

            logger.info(f"Falling back to HTML parsing for {repo_url}")
            html_data = await parse_html_releases(session, repo_url)
            if html_data:
                return html_data

        except ClientError as e:
            logger.error(f"Request failed: {e}")
            if attempt == max_retries - 1:
                return await parse_html_releases(session, repo_url)
            await asyncio.sleep(2 ** attempt)

    return None


# --- ПРОВЕРКА СООТВЕТСТВИЯ ФИЛЬТРАМ ---
def matches_filters(release_data: dict, keywords: List[str]) -> bool:
    if not keywords:
        return True

    search_text = ""

    # Добавляем название релиза
    if release_data.get('name'):
        search_text += release_data['name'].lower() + " "

    # Добавляем тег
    if release_data.get('tag_name'):
        search_text += release_data['tag_name'].lower() + " "

    # Добавляем описание
    if release_data.get('body'):
        search_text += release_data['body'].lower() + " "

    # Проверяем каждое ключевое слово
    for keyword in keywords:
        if keyword.lower() not in search_text:
            return False

    return True


# --- ФОРМАТИРОВАНИЕ СООБЩЕНИЯ ---
def format_release_message(repo_name, release):
    tag = release.get('tag_name', 'Unknown')
    name = release.get('name', tag)
    body = release.get('body', '')
    published_at = release.get('published_at', '')
    assets = release.get('assets', [])

    links = []
    for asset in assets:
        asset_name = asset.get('name', '')
        download_url = asset.get('browser_download_url', '')
        if asset_name and download_url and not asset_name.startswith("Source code"):
            links.append(f"[{asset_name}]({download_url})")

    message = (
        f"🚀 *Новый релиз в репозитории {repo_name}*\n\n"
        f"*{name}*\n"
        f"`{tag}`\n"
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
        message += f"{body}\n\n"

    if links:
        message += "📥 *Ссылки для скачивания:*\n" + "\n".join(links)
    else:
        message += "⚠️ Файлы для скачивания не найдены"

    return message


# --- ПРОВЕРКА ОБНОВЛЕНИЙ С ФИЛЬТРАЦИЕЙ ---
async def check_updates(bot: Bot):
    logger.info("Проверка обновлений...")
    print("=== Начинаю проверку обновлений ===")
    state = load_state()
    async with ClientSession() as session:
        for repo_url in REPOS:
            print(f"Проверяю репозиторий: {repo_url}")
            repo_name = repo_url.split("/")[-2] + "/" + repo_url.split("/")[-1]
            release = await fetch_release(session, repo_url)

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
                # Проверяем для каждого пользователя с его фильтрами
                notified_users = set()
                for user_id, filters in user_filters.items():
                    if matches_filters(release, filters):
                        if user_id not in notified_users:
                            message = format_release_message(repo_name, release)
                            try:
                                await bot.send_message(user_id, message, parse_mode="Markdown")
                                notified_users.add(user_id)
                                logger.info(
                                    f"Уведомление отправлено пользователю {user_id} для {repo_name} {current_tag}")
                            except Exception as e:
                                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

                # Если нет фильтров у пользователей, отправляем в основной канал
                if not notified_users and CHANNEL_ID:
                    message = format_release_message(repo_name, release)
                    await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                    logger.info(f"Уведомление отправлено в канал для {repo_name} {current_tag}")

                state[repo_name] = current_tag

    save_state(state)
    print("=== Проверка обновлений завершена ===")
    logger.info("Проверка обновлений завершена")


# --- КОМАНДА /start ---
async def start_command(message: Message):
    print(f"Получена команда /start от пользователя {message.from_user.id}")
    await message.answer(
        "👋 Привет! Я бот для отслеживания релизов на GitHub.\n\n"
        "📌 *Основные команды:*\n"
        "/filter - установить фильтры для уведомлений\n"
        "/myfilters - посмотреть текущие фильтры\n"
        "/clearfilters - очистить все фильтры\n"
        "/help - справка по использованию"
    )


# --- КОМАНДА /filter ---
async def filter_command(message: Message):
    print(f"Пользователь {message.from_user.id} хочет установить фильтры")
    await message.answer(
        "🔍 *Настройка фильтров*\n\n"
        "Введите ключевые слова через пробел, по которым будет производиться фильтрация релизов.\n"
        "Например: `qubitcoin qtc`\n\n"
        "Бот будет искать совпадения в названиях релизов и описаниях."
    )
    await message.answer("⏳ Ожидаю ввод ключевых слов...")


# --- ОБРАБОТКА ТЕКСТА ПОСЛЕ /filter ---
async def process_filter_text(message: Message):
    user_id = str(message.from_user.id)
    keywords = message.text.strip().split()

    print(f"Пользователь {user_id} вводит фильтры: {keywords}")

    if not keywords:
        await message.answer("❌ Вы не ввели ключевые слова. Попробуйте снова.")
        return

    # Сохраняем фильтры
    user_filters[user_id] = keywords
    save_filters(user_filters)

    await message.answer(
        f"✅ *Фильтры сохранены!*\n\n"
        f"Ключевые слова: {', '.join(keywords)}\n\n"
        "Теперь вы будете получать уведомления только о релизах, содержащих эти слова."
    )


# --- КОМАНДА /myfilters ---
async def myfilters_command(message: Message):
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
    user_id = str(message.from_user.id)

    print(f"Пользователь {user_id} очищает фильтры")

    if user_id in user_filters:
        del user_filters[user_id]
        save_filters(user_filters)
        await message.answer("🗑️ Ваши фильтры успешно удалены.")
    else:
        await message.answer("📭 У вас и так не было установленных фильтров.")


# --- КОМАНДА /help ---
async def help_command(message: Message):
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
    # Команды
    dp.message.register(start_command, CommandStart())
    dp.message.register(filter_command, Command("filter"))
    dp.message.register(myfilters_command, Command("myfilters"))
    dp.message.register(clearfilters_command, Command("clearfilters"))
    dp.message.register(help_command, Command("help"))

    # Обработка текста после команды /filter
    dp.message.register(process_filter_text, F.text & ~F.command)
    print("Обработчики зарегистрированы")


# --- MAIN ---
async def main():
    print("=== Запуск бота ===")

    # Проверка наличия токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в файле .env!")
        print("ОШИБКА: BOT_TOKEN не найден в файле .env!")
        return

    print("Инициализация бота...")
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
    dp = Dispatcher()

    print("Регистрация обработчиков...")
    # Регистрация обработчиков
    register_handlers(dp)

    print("Настройка планировщика...")
    # Настройка планировщика
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

    # Запуск поллинга
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
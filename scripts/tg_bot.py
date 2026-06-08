"""
Telegram-бот для добавления 3D-моделей в каталог.

Использование:
  python tg_bot.py

Бот принимает:
  - Ссылки на MakerWorld / Thingiverse / Printables
  - Опционально: категория, теги

Команды:
  /start   — приветствие
  /help    — справка
  /list    — список последних моделей
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Автоперевод ----------
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR = GoogleTranslator(source='en', target='ru')
except Exception:
    TRANSLATOR = None


def translate_to_ru(text: str) -> str:
    """Переводит текст с английского на русский. В случае ошибки — возвращает оригинал."""
    if not TRANSLATOR:
        return text
    try:
        translated = TRANSLATOR.translate(text)
        return translated if translated else text
    except Exception:
        return text

# ---------- НАСТРОЙКИ ----------
TOKEN = os.environ.get("TG_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TG_BOT_TOKEN не найден в переменных окружения. Проверь файл .env")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "models.json"
SCRIPT_ADD = PROJECT_ROOT / "scripts" / "add_model.py"

# Категории загружаются из models.json


def load_categories() -> dict:
    """Загружает категории из models.json."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {c["id"]: c["name"] for c in data.get("categories", [])}
    except Exception:
        return {}


def load_subcategories(cat_id: str) -> dict:
    """Загружает подкатегории для конкретной категории."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        subs = data.get("subcategories", {}).get(cat_id, [])
        return {s["id"]: s["name"] for s in subs}
    except Exception:
        return {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Вспомогательные функции ----------
def is_model_url(text: str) -> bool:
    """Проверяет, похожа ли строка на URL модели."""
    patterns = [
        r"makerworld\.com/.*/?models/",
        r"thingiverse\.com/thing:",
        r"printables\.com/model/",
    ]
    return any(re.search(p, text) for p in patterns)


def get_recent_models(n: int = 5) -> list:
    """Возвращает последние N моделей из каталога."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models", [])
        return models[-n:][::-1]
    except Exception:
        return []


def run_add_model(url: str, cat: str = None, sub: str = None, tags: str = "", featured: bool = False, name: str = None) -> dict:
    """Запускает add_model.py и возвращает результат."""
    cmd = [sys.executable, str(SCRIPT_ADD), url, "--add"]
    if cat:
        cmd.extend(["--cat", cat])
    if sub:
        cmd.extend(["--sub", sub])
    if tags:
        cmd.extend(["--tags", tags])
    if featured:
        cmd.append("--featured")
    if name:
        cmd.extend(["--name", name])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def git_commit_and_push(message: str) -> dict:
    """Коммитит и пушит изменения на GitHub."""
    # Сначала проверяем, есть ли что коммитить
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if not status.stdout.strip():
        return {"success": True, "log": "Нет изменений для коммита"}

    commands = [
        ["git", "add", "-A"],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    outputs = []
    for cmd in commands:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=60,
        )
        outputs.append(f"{' '.join(cmd)}:\n{r.stdout}{r.stderr}")
        if r.returncode != 0 and "nothing to commit" not in r.stdout:
            return {"success": False, "log": "\n".join(outputs)}
    return {"success": True, "log": "\n".join(outputs)}


# ---------- Обработчики ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    await update.message.reply_text(
        "Привет! Я бот для добавления 3D-моделей на сайт.\n\n"
        "Просто отправь ссылку с MakerWorld, Thingiverse или Printables — "
        "я скачаю фото, обновлю каталог и запушу на сайт.\n\n"
        "Команды:\n"
        "/help — подробная справка\n"
        "/list — последние добавленные модели\n"
        "/addcat — добавить новую категорию\n"
        "/addsub — добавить подкатегорию"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    await update.message.reply_text(
        "Как пользоваться:\n\n"
        "1. Отправь ссылку на модель:\n"
        "   https://makerworld.com/ru/models/2016647\n\n"
        "2. Выбери категорию (бот предложит варианты)\n\n"
        "3. Выбери подкатегорию или пропусти\n\n"
        "4. Выбери название (перевод/оригинал/своё)\n\n"
        "5. Готово! Модель добавлена на сайт\n\n"
        "Команды:\n"
        "/addcat <id> <название> — новая категория\n"
        "/addsub <cat_id> <sub_id> <название> — новая подкатегория\n"
        "/list — последние модели\n\n"
        "Или просто отправь ссылку — я всё покажу!"
    )


def add_category_to_json(cat_id: str, cat_name: str) -> bool:
    """Добавляет новую категорию в models.json."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Проверяем, нет ли уже такой категории
        for c in data.get("categories", []):
            if c["id"] == cat_id:
                return False
        data["categories"].append({"id": cat_id, "name": cat_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def add_subcategory_to_json(cat_id: str, sub_id: str, sub_name: str) -> bool:
    """Добавляет подкатегорию в models.json."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Проверяем, существует ли категория
        cat_exists = any(c["id"] == cat_id for c in data.get("categories", []))
        if not cat_exists:
            return False
        # Инициализируем dict подкатегорий если нужно
        if "subcategories" not in data:
            data["subcategories"] = {}
        if cat_id not in data["subcategories"]:
            data["subcategories"][cat_id] = []
        # Проверяем, нет ли уже такой подкатегории
        for s in data["subcategories"][cat_id]:
            if s["id"] == sub_id:
                return False
        data["subcategories"][cat_id].append({"id": sub_id, "name": sub_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить новую категорию: /addcat <id> <название>"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Формат: /addcat <id> <название>\n"
            "Пример: /addcat figures Фигурки"
        )
        return

    cat_id = context.args[0].lower().strip()
    cat_name = " ".join(context.args[1:])

    if add_category_to_json(cat_id, cat_name):
        git_commit_and_push(f"Добавлена категория: {cat_name} ({cat_id})")
        await update.message.reply_text(
            f"✅ Категория добавлена!\n"
            f"ID: {cat_id}\n"
            f"Название: {cat_name}\n\n"
            f"Теперь можно добавлять модели в неё."
        )
    else:
        await update.message.reply_text("Ошибка: категория уже существует или неверные данные.")


async def add_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить подкатегорию: /addsub <cat_id> <sub_id> <название>"""
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Формат: /addsub <cat_id> <sub_id> <название>\n"
            "Пример: /addsub figures star-wars Star Wars"
        )
        return

    cat_id = context.args[0].lower().strip()
    sub_id = context.args[1].lower().strip()
    sub_name = " ".join(context.args[2:])

    if add_subcategory_to_json(cat_id, sub_id, sub_name):
        git_commit_and_push(f"Добавлена подкатегория: {sub_name} ({cat_id}/{sub_id})")
        await update.message.reply_text(
            f"✅ Подкатегория добавлена!\n"
            f"Категория: {cat_id}\n"
            f"ID: {sub_id}\n"
            f"Название: {sub_name}"
        )
    else:
        await update.message.reply_text(
            "Ошибка: подкатегория уже существует или категория не найдена."
        )


async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать последние модели."""
    models = get_recent_models(5)
    if not models:
        await update.message.reply_text("Каталог пуст.")
        return

    categories = load_categories()
    text = "Последние добавленные модели:\n\n"
    for i, m in enumerate(models, 1):
        cat = categories.get(m.get("category", ""), m.get("category", "?"))
        text += f"{i}. {m['name']}\n   Категория: {cat}\n   {m.get('url', '')}\n\n"

    await update.message.reply_text(text)


def update_model_data(model_id, weight=None, print_time=None):
    """Обновляет вес и время печати модели в models.json."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for m in data.get("models", []):
            if m.get("id") == model_id:
                if weight is not None:
                    m["weight"] = weight
                if print_time is not None:
                    m["printTime"] = print_time
                break
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


async def handle_weight_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода веса."""
    text = update.message.text.strip()

    if text.lower() in ("пропустить", "skip", "-", "дальше"):
        context.user_data["awaiting_weight"] = False
        context.user_data["awaiting_time"] = True
        await update.message.reply_text("Ок. Укажи примерное время печати в минутах (или «пропустить»):")
        return

    try:
        weight = float(text.replace(",", ".").strip())
    except ValueError:
        await update.message.reply_text("Не понял число. Введи вес в граммах (например 45) или «пропустить»:")
        return

    context.user_data["weight"] = weight
    context.user_data["awaiting_weight"] = False
    context.user_data["awaiting_time"] = True
    await update.message.reply_text(f"Вес: {weight} г\n\nУкажи примерное время печати в минутах (или «пропустить»):")


async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода времени печати."""
    text = update.message.text.strip()

    print_time = None
    if text.lower() not in ("пропустить", "skip", "-", "дальше"):
        try:
            print_time = float(text.replace(",", ".").strip())
        except ValueError:
            await update.message.reply_text("Не понял число. Введи время в минутах (например 45) или «пропустить»:")
            return

    weight = context.user_data.get("weight")
    model_id = context.user_data.get("last_model_id")

    if model_id and (weight or print_time):
        ok = update_model_data(model_id, weight=weight, print_time=print_time)
        if ok:
            git_commit_and_push(f"Обновлены данные модели: {model_id}")

    info = []
    if weight:
        info.append(f"Вес: {weight} г")
    if print_time:
        if print_time > 60:
            info.append(f"Время печати: {round(print_time/60, 1)} ч")
        else:
            info.append(f"Время печати: {print_time} мин")
    info_text = "\n".join(info) if info else "Данные не указаны"

    await update.message.reply_text(
        f"🎉 Готово!\n\n"
        f"{info_text}\n"
        f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
    )

    for key in ["pending_url", "pending_cat", "pending_cat_name", "original_name", "translated_name",
                 "awaiting_weight", "awaiting_time", "weight", "last_model_id"]:
        context.user_data.pop(key, None)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на модель."""
    # Если ожидаем вес
    if context.user_data.get("awaiting_weight"):
        await handle_weight_input(update, context)
        return

    # Если ожидаем время печати
    if context.user_data.get("awaiting_time"):
        await handle_time_input(update, context)
        return

    # Если ожидаем название новой категории
    if context.user_data.get("awaiting_new_cat"):
        await handle_new_category(update, context)
        return

    # Если ожидаем название новой подкатегории
    if context.user_data.get("awaiting_new_sub"):
        await handle_new_subcategory(update, context)
        return

    # Если ожидаем кастомное название
    if context.user_data.get("awaiting_custom_name"):
        await handle_model_name(update, context)
        return

    # Если ожидаем название модели
    if context.user_data.get("awaiting_name"):
        await handle_model_name(update, context)
        return

    text = update.message.text.strip()

    if not is_model_url(text):
        await update.message.reply_text(
            "Не похоже на ссылку модели. Отправь URL с MakerWorld, Thingiverse или Printables."
        )
        return

    # Сохраняем URL в контексте пользователя
    context.user_data["pending_url"] = text

    # Пытаемся угадать категорию по URL
    suggested_cat = guess_category_from_url(text)

    # Показываем кнопки категорий
    categories = load_categories()
    keyboard = []
    row = []
    for cat_id, cat_name in categories.items():
        # Если категория угадана — помечаем её звёздочкой
        label = f"⭐ {cat_name}" if cat_id == suggested_cat else cat_name
        row.append(InlineKeyboardButton(label, callback_data=f"cat:{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Добавляем кнопку "Новая категория"
    keyboard.append([InlineKeyboardButton("➕ Новая категория", callback_data="cat:new")])

    hint = ""
    if suggested_cat:
        cat_name = categories.get(suggested_cat, suggested_cat)
        hint = f"💡 Предлагаю: «{cat_name}»\n\n"

    await update.message.reply_text(
        f"{hint}Получил ссылку! Выбери категорию:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


def guess_category_from_url(url: str) -> str:
    """Пытается угадать категорию по URL модели."""
    url_lower = url.lower()

    # Простые правила по ключевым словам в URL
    keywords = {
        "home": ["home", "house", "decor", "interior", "planter", "vase", "lamp", "light", "holder", "hook", "shelf", "box", "container", "storage"],
        "kitchen": ["kitchen", "mug", "cup", "plate", "spoon", "fork", "knife", "organizer", "rack"],
        "figures": ["figure", "statue", "figurine", "character", "robot", "dragon", "warrior", "batman", "star-wars", "marvel", "lotr", "gollum", "gate", "minas"],
        "games": ["game", "chess", "dice", "token", "miniature", "dnd", "warhammer", "puzzle"],
        "tools": ["tool", "wrench", "holder", "clip", "mount", "bracket", "adapter", "gadget"],
        "auto": ["car", "auto", "vehicle", "bike", "motorcycle", "phone-holder", "charger", "cable"],
        "lighting": ["lamp", "light", "led", "chandelier", "sconce", "lantern"],
        "storage": ["storage", "organizer", "drawer", "shelf", "rack", "stand", "case"],
        "wardrobe": ["hanger", "hook", "closet", "wardrobe", "shoe", "belt"],
        "parts": ["part", "gear", "bearing", "bushing", "connector", "screw", "bolt", "nut"],
    }

    for cat_id, words in keywords.items():
        for word in words:
            if word in url_lower:
                return cat_id

    return None


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории — показывает подкатегории."""
    query = update.callback_query
    await query.answer()

    cat_id = query.data.split(":")[1]
    url = context.user_data.get("pending_url")

    if not url:
        await query.edit_message_text("Ошибка: ссылка потерялась. Отправь заново.")
        return

    # Если выбрана "Новая категория"
    if cat_id == "new":
        context.user_data["awaiting_new_cat"] = True
        await query.edit_message_text(
            "Отправь название новой категории на русском.\n"
            "Например: «Одежда» или «Автозапчасти»"
        )
        return

    categories = load_categories()
    cat_name = categories.get(cat_id, cat_id)

    # Сохраняем категорию
    context.user_data["pending_cat"] = cat_id
    context.user_data["pending_cat_name"] = cat_name

    # Загружаем подкатегории
    subcategories = load_subcategories(cat_id)

    # Построение клавиатуры подкатегорий
    keyboard = []
    if subcategories:
        row = []
        for sub_id, sub_name in subcategories.items():
            row.append(InlineKeyboardButton(sub_name, callback_data=f"sub:{sub_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

    # Кнопки "Новая подкатегория" и "Без подкатегории"
    keyboard.append([InlineKeyboardButton("➕ Новая подкатегория", callback_data="sub:new")])
    keyboard.append([InlineKeyboardButton("⏭ Без подкатегории", callback_data="sub:none")])

    if subcategories:
        text = f"Категория: «{cat_name}»\n\nВыбери подкатегорию:"
    else:
        text = f"Категория: «{cat_name}»\n\nПодкатегорий пока нет. Создай новую или пропусти:"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def subcategory_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора подкатегории."""
    query = update.callback_query
    await query.answer()

    sub_id = query.data.split(":")[1]
    url = context.user_data.get("pending_url")
    cat_id = context.user_data.get("pending_cat")
    cat_name = context.user_data.get("pending_cat_name")

    if not url:
        await query.edit_message_text("Ошибка: ссылка потерялась. Отправь заново.")
        return

    # Если выбрана "Новая подкатегория"
    if sub_id == "new":
        context.user_data["awaiting_new_sub"] = True
        await query.edit_message_text(
            "Отправь название новой подкатегории на русском.\n"
            "Например: «Star Wars» или «Миньоны»"
        )
        return

    # Если выбрано "Без подкатегории"
    if sub_id == "none":
        context.user_data["pending_sub"] = None
        context.user_data["pending_sub_name"] = None
    else:
        subcategories = load_subcategories(cat_id)
        sub_name = subcategories.get(sub_id, sub_id)
        context.user_data["pending_sub"] = sub_id
        context.user_data["pending_sub_name"] = sub_name

    # Переходим к выбору названия
    await show_name_selection(update, context)


async def show_name_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать выбор названия модели."""
    url = context.user_data.get("pending_url")
    cat_name = context.user_data.get("pending_cat_name")
    sub_name = context.user_data.get("pending_sub_name")

    # Получаем оригинальное название
    original_name = "модель"
    try:
        if "models/" in url:
            match = re.search(r'models/\d+-(.+?)(?:\?|$)', url)
            if match:
                original_name = match.group(1).replace('-', ' ').title()
    except Exception:
        pass

    # Переводим
    translated_name = translate_to_ru(original_name)

    # Сохраняем варианты
    context.user_data["original_name"] = original_name
    context.user_data["translated_name"] = translated_name

    # Показываем варианты с кнопками
    keyboard = [
        [InlineKeyboardButton(f"✅ «{translated_name}»", callback_data="name:translated")],
        [InlineKeyboardButton(f"Оригинал: «{original_name}»", callback_data="name:original")],
        [InlineKeyboardButton("✏️ Написать своё", callback_data="name:custom")],
    ]

    category_text = f"Категория: «{cat_name}»"
    if sub_name:
        category_text += f" → «{sub_name}»"

    # Определяем, откуда вызвано — callback или message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"{category_text}\n\n"
            f"Оригинал: {original_name}\n"
            f"Перевод: {translated_name}\n\n"
            f"Выбери название или напиши своё:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            f"{category_text}\n\n"
            f"Оригинал: {original_name}\n"
            f"Перевод: {translated_name}\n\n"
            f"Выбери название или напиши своё:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия новой категории."""
    cat_name = update.message.text.strip()

    # Генерируем ID из названия
    cat_id = re.sub(r'[^a-zа-я0-9]', '-', cat_name.lower()).strip('-')
    cat_id = re.sub(r'-+', '-', cat_id)

    if not cat_id:
        await update.message.reply_text("Некорректное название. Попробуй ещё раз.")
        return

    # Добавляем категорию
    if add_category_to_json(cat_id, cat_name):
        git_commit_and_push(f"Добавлена категория: {cat_name} ({cat_id})")

        # Сохраняем и показываем кнопки категорий заново
        context.user_data["awaiting_new_cat"] = False
        url = context.user_data.get("pending_url")

        categories = load_categories()
        keyboard = []
        row = []
        for cid, cname in categories.items():
            label = f"⭐ {cname}" if cid == cat_id else cname
            row.append(InlineKeyboardButton(label, callback_data=f"cat:{cid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("➕ Новая категория", callback_data="cat:new")])

        await update.message.reply_text(
            f"✅ Категория «{cat_name}» создана!\n\nТеперь выбери её:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text("Ошибка: категория уже существует.")


async def handle_new_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия новой подкатегории."""
    sub_name = update.message.text.strip()
    cat_id = context.user_data.get("pending_cat")
    cat_name = context.user_data.get("pending_cat_name")

    # Генерируем ID из названия
    sub_id = re.sub(r'[^a-zа-я0-9]', '-', sub_name.lower()).strip('-')
    sub_id = re.sub(r'-+', '-', sub_id)

    if not sub_id:
        await update.message.reply_text("Некорректное название. Попробуй ещё раз.")
        return

    # Добавляем подкатегорию
    if add_subcategory_to_json(cat_id, sub_id, sub_name):
        git_commit_and_push(f"Добавлена подкатегория: {sub_name} ({cat_id}/{sub_id})")

        context.user_data["awaiting_new_sub"] = False
        context.user_data["pending_sub"] = sub_id
        context.user_data["pending_sub_name"] = sub_name

        # Переходим к выбору названия
        await show_name_selection(update, context)
    else:
        await update.message.reply_text("Ошибка: подкатегория уже существует или категория не найдена.")


async def name_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора названия модели."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[1]
    url = context.user_data.get("pending_url")
    cat_id = context.user_data.get("pending_cat")
    cat_name = context.user_data.get("pending_cat_name")
    original_name = context.user_data.get("original_name", "модель")
    translated_name = context.user_data.get("translated_name", "модель")

    if choice == "translated":
        final_name = translated_name
    elif choice == "original":
        final_name = original_name
    else:
        # custom — запрашиваем ввод
        context.user_data["awaiting_custom_name"] = True
        await query.edit_message_text("Отправь название модели на русском:")
        return

    await query.edit_message_text(f"Добавляю «{final_name}» в категорию «{cat_name}»...")

    # Запускаем add_model.py
    sub_id = context.user_data.get("pending_sub")
    try:
        result = run_add_model(url, cat=cat_id, sub=sub_id, name=final_name)
    except subprocess.TimeoutExpired:
        await query.message.reply_text("Ошибка: скрипт завис. Попробуй позже.")
        return
    except Exception as e:
        await query.message.reply_text(f"Ошибка: {e}")
        return

    if result["returncode"] != 0:
        error = result["stderr"].strip() or result["stdout"].strip()
        await query.message.reply_text(f"Ошибка при добавлении:\n{error[:500]}")
        return

    # Коммитим и пушим
    await query.message.reply_text(f"✅ «{final_name}» добавлена! Пушу на сайт...")
    git_result = git_commit_and_push(f"Добавлена модель: {final_name} (из Telegram)")

    if git_result["success"]:
        model_id = None
        try:
            model_json = json.loads(result["stdout"].strip().split('\n')[-1])
            model_id = model_json.get("id")
        except Exception:
            pass
        context.user_data["last_model_id"] = model_id
        context.user_data["awaiting_weight"] = True
        await query.message.reply_text(
            f"✅ «{final_name}» добавлена и запушена!\n\n"
            f"Укажи вес модели в граммах (или «пропустить»):"
        )
    else:
        await query.message.reply_text(
            f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
        )
        for key in ["pending_url", "pending_cat", "pending_cat_name", "original_name", "translated_name"]:
            context.user_data.pop(key, None)


async def handle_model_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия модели от пользователя."""
    # Если ожидаем кастомное название
    if context.user_data.get("awaiting_custom_name"):
        context.user_data["awaiting_custom_name"] = False
        text = update.message.text.strip()
        url = context.user_data.get("pending_url")
        cat_id = context.user_data.get("pending_cat")
        cat_name = context.user_data.get("pending_cat_name")

        final_name = text

        await update.message.reply_text(f"Добавляю «{final_name}» в категорию «{cat_name}»...")

        # Запускаем add_model.py
        sub_id = context.user_data.get("pending_sub")
        try:
            result = run_add_model(url, cat=cat_id, sub=sub_id, name=final_name)
        except subprocess.TimeoutExpired:
            await update.message.reply_text("Ошибка: скрипт завис. Попробуй позже.")
            return True
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
            return True

        if result["returncode"] != 0:
            error = result["stderr"].strip() or result["stdout"].strip()
            await update.message.reply_text(f"Ошибка при добавлении:\n{error[:500]}")
            return True

        # Коммитим и пушим
        await update.message.reply_text(f"✅ «{final_name}» добавлена! Пушу на сайт...")
        git_result = git_commit_and_push(f"Добавлена модель: {final_name} (из Telegram)")

        if git_result["success"]:
            model_id = None
            try:
                model_json = json.loads(result["stdout"].strip().split('\n')[-1])
                model_id = model_json.get("id")
            except Exception:
                pass
            context.user_data["last_model_id"] = model_id
            context.user_data["awaiting_weight"] = True
            await update.message.reply_text(
                f"✅ «{final_name}» добавлена и запушена!\n\n"
                f"Укажи вес модели в граммах (или «пропустить»):"
            )
        else:
            await update.message.reply_text(
                f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
            )

        # Чистим
        for key in ["pending_url", "pending_cat", "pending_cat_name", "pending_sub", "pending_sub_name", "original_name", "translated_name"]:
            context.user_data.pop(key, None)
        return True

    return False
    await update.message.reply_text(f"✅ «{name}» добавлена! Пушу на сайт...")
    git_result = git_commit_and_push(f"Добавлена модель: {name} (из Telegram)")

    if git_result["success"]:
        await update.message.reply_text(
            f"🎉 Готово!\n\n"
            f"Модель: {name}\n"
            f"Категория: {cat_name}\n"
            f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
        )
    else:
        await update.message.reply_text(
            f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
        )

    # Чистим
    context.user_data.pop("pending_url", None)
    context.user_data.pop("pending_cat", None)
    context.user_data.pop("pending_cat_name", None)
    context.user_data.pop("awaiting_name", None)
    return True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка прочего текста."""
    await update.message.reply_text(
        "Отправь ссылку на модель с MakerWorld, Thingiverse или Printables."
    )


def main():
    """Запуск бота."""
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_models))
    app.add_handler(CommandHandler("addcat", add_category))
    app.add_handler(CommandHandler("addsub", add_subcategory))
    app.add_handler(CallbackQueryHandler(category_selected, pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(subcategory_selected, pattern=r"^sub:"))
    app.add_handler(CallbackQueryHandler(name_selected, pattern=r"^name:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    from httpx import Timeout

    logger.info("Бот запущен!")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        timeout=30,
    )


if __name__ == "__main__":
    main()

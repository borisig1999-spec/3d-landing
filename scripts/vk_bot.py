"""
VK-бот для добавления 3D-моделей в каталог.

Использование:
  python vk_bot.py
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# ---------- НАСТРОЙКИ ----------
TOKEN = os.environ.get("VK_BOT_TOKEN")
if not TOKEN:
    raise ValueError("VK_BOT_TOKEN не найден в переменных окружения. Проверь файл .env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "models.json"
SCRIPT_ADD = PROJECT_ROOT / "scripts" / "add_model.py"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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


def is_model_url(text: str) -> bool:
    """Проверяет, похожа ли строка на URL модели."""
    patterns = [
        r"makerworld\.com/.*/?models/",
        r"thingiverse\.com/thing:",
        r"printables\.com/model/",
    ]
    return any(re.search(p, text) for p in patterns)


def translate_to_ru(text: str) -> str:
    """Переводит текст с английского на русский."""
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='en', target='ru').translate(text)
        return translated if translated else text
    except Exception:
        return text


def run_add_model(url: str, cat: str = None, sub: str = None, name: str = None) -> dict:
    """Запускает add_model.py и возвращает результат."""
    cmd = [sys.executable, str(SCRIPT_ADD), url, "--add"]
    if cat:
        cmd.extend(["--cat", cat])
    if sub:
        cmd.extend(["--sub", sub])
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


# ---------- Клавиатуры ----------
def get_main_menu_keyboard():
    """Главное меню."""
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_callback_button("Добавить модель", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "menu:add"})
    keyboard.add_line()
    keyboard.add_callback_button("Редактировать модель", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "menu:edit"})
    return keyboard.get_keyboard()


def get_category_keyboard(highlight_cat=None):
    """Клавиатура категорий. highlight_cat — id категории для подсветки."""
    categories = load_categories()
    keyboard = VkKeyboard(one_time=True)
    row = []
    for cat_id, cat_name in categories.items():
        color = VkKeyboardColor.POSITIVE if cat_id == highlight_cat else VkKeyboardColor.PRIMARY
        label = f"👉 {cat_name}" if cat_id == highlight_cat else cat_name
        row.append((label, color, f"cat:{cat_id}"))
        if len(row) == 2:
            keyboard.add_callback_button(row[0][0], color=row[0][1], payload={"type": "text", "text": row[0][2]})
            keyboard.add_callback_button(row[1][0], color=row[1][1], payload={"type": "text", "text": row[1][2]})
            keyboard.add_line()
            row = []
    if row:
        keyboard.add_callback_button(row[0][0], color=row[0][1], payload={"type": "text", "text": row[0][2]})
        keyboard.add_line()
    keyboard.add_callback_button("➕ Новая категория", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "cat:new"})
    return keyboard.get_keyboard()


def get_subcategory_keyboard(cat_id):
    """Клавиатура подкатегорий."""
    subcategories = load_subcategories(cat_id)
    keyboard = VkKeyboard(one_time=True)
    row = []
    for sub_id, sub_name in subcategories.items():
        row.append((sub_name, VkKeyboardColor.PRIMARY, f"sub:{sub_id}"))
        if len(row) == 2:
            keyboard.add_callback_button(row[0][0], color=row[0][1], payload={"type": "text", "text": row[0][2]})
            keyboard.add_callback_button(row[1][0], color=row[1][1], payload={"type": "text", "text": row[1][2]})
            keyboard.add_line()
            row = []
    if row:
        keyboard.add_callback_button(row[0][0], color=row[0][1], payload={"type": "text", "text": row[0][2]})
        keyboard.add_line()
    keyboard.add_callback_button("➕ Новая подкатегория", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "sub:new"})
    keyboard.add_callback_button("Без подкатегории", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "sub:none"})
    return keyboard.get_keyboard()


def get_name_keyboard(original_name, translated_name):
    """Клавиатура выбора названия."""
    keyboard = VkKeyboard(one_time=True)
    t_label = f"✅ {translated_name}"[:40]
    o_label = f"Оригинал: {original_name}"[:40]
    keyboard.add_callback_button(t_label, color=VkKeyboardColor.POSITIVE, payload={"type": "text", "text": "name:translated"})
    keyboard.add_line()
    keyboard.add_callback_button(o_label, color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "name:original"})
    keyboard.add_line()
    keyboard.add_callback_button("Написать своё", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "name:custom"})
    return keyboard.get_keyboard()


# ---------- Дедупликация ----------
processed_messages = set()
callback_seen = {}  # {(user_id, text): timestamp} — чтобы не дублировать MESSAGE_NEW после callback

# ---------- Состояния пользователей ----------
ALLOWED_USERS = {362356023}

user_states = {}


def get_user_state(user_id):
    """Получает состояние пользователя."""
    if user_id not in user_states:
        user_states[user_id] = {}
    return user_states[user_id]


def clear_user_state(user_id):
    """Очищает состояние пользователя."""
    user_states.pop(user_id, None)


# ---------- Обработчики ----------
def handle_start(vk, event):
    """Приветствие."""
    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message="Привет! Что делаем?",
        keyboard=get_main_menu_keyboard(),
        random_id=event.obj.message["random_id"],
    )


def handle_help(vk, event):
    """Справка."""
    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=(
            "Как пользоваться:\n\n"
            "1. Отправь ссылку на модель:\n"
            "   https://makerworld.com/ru/models/2016647\n\n"
            "2. Выбери категорию\n\n"
            "3. Выбери подкатегорию или пропусти\n\n"
            "4. Выбери название (перевод/оригинал/своё)\n\n"
            "5. Готово! Модель добавлена на сайт\n\n"
            "Или просто отправь ссылку — я всё покажу!"
        ),
        random_id=event.obj.message["random_id"],
    )


def handle_list(vk, event):
    """Последние модели."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models", [])[-5:][::-1]
        categories = load_categories()

        text = "Последние добавленные модели:\n\n"
        for i, m in enumerate(models, 1):
            cat = categories.get(m.get("category", ""), m.get("category", "?"))
            text += f"{i}. {m['name']}\n   Категория: {cat}\n   {m.get('url', '')}\n\n"

        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=text,
            random_id=event.obj.message["random_id"],
        )
    except Exception as e:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )


def handle_message(vk, event):
    """Обработка сообщений."""
    user_id = event.obj.message["from_id"]

    if user_id not in ALLOWED_USERS:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="У тебя нет доступа к этому боту.",
            random_id=event.obj.message["random_id"],
        )
        return

    text = event.obj.message.get("text", "").strip()
    state = get_user_state(user_id)

    # Команды
    if text == "/start":
        handle_start(vk, event)
        return
    elif text == "/help":
        handle_help(vk, event)
        return
    elif text == "/list":
        handle_list(vk, event)
        return

    # Меню
    if text == "menu:add":
        state.clear()
        state["flow"] = "add"
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Отправь ссылку на модель с MakerWorld, Thingiverse или Printables:",
            random_id=event.obj.message["random_id"],
        )
        return
    elif text == "menu:edit":
        state.clear()
        state["flow"] = "edit"
        state["awaiting_edit_url"] = True
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Отправь ссылку на модель, которую нужно отредактировать:",
            random_id=event.obj.message["random_id"],
        )
        return

    # Редактирование: ожидаем URL
    if state.get("awaiting_edit_url"):
        handle_edit_url(vk, event, text, state)
        return

    # Редактирование: выбор поля
    if state.get("awaiting_edit_field"):
        handle_edit_field(vk, event, text, state)
        return

    # Редактирование: ввод нового значения
    if state.get("awaiting_edit_value"):
        handle_edit_value(vk, event, text, state)
        return

    # Если ожидаем название новой категории
    if state.get("awaiting_new_cat"):
        handle_new_category(vk, event, text, state)
        return

    # Если ожидаем название новой подкатегории
    if state.get("awaiting_new_sub"):
        handle_new_subcategory(vk, event, text, state)
        return

    # Если ожидаем кастомное название
    if state.get("awaiting_custom_name"):
        handle_custom_name(vk, event, text, state)
        return

    # Если ожидаем ввод веса
    if state.get("awaiting_weight"):
        try:
            handle_weight_input(vk, event, text, state)
        except Exception as e:
            logger.error(f"Error in weight input: {e}")
            vk.messages.send(
                peer_id=event.obj.message["peer_id"],
                message=f"Ошибка: {e}\n\nПопробуй ещё раз или напиши «пропустить»:",
                random_id=event.obj.message["random_id"],
            )
        return

    # Если ожидаем ввод времени
    if state.get("awaiting_time"):
        try:
            handle_time_input(vk, event, text, state)
        except Exception as e:
            logger.error(f"Error in time input: {e}")
            vk.messages.send(
                peer_id=event.obj.message["peer_id"],
                message=f"Ошибка: {e}\n\nПопробуй ещё раз или напиши «пропустить»:",
                random_id=event.obj.message["random_id"],
            )
        return

    # Если это ссылка на модель (только в режиме добавления)
    if is_model_url(text) and state.get("flow") != "edit":
        state["url"] = text
        state["awaiting_category"] = True

        # Пытаемся угадать категорию
        suggested_cat = guess_category_from_url(text)
        categories = load_categories()

        msg = "Получил ссылку! Выбери категорию:"
        if suggested_cat:
            cat_name = categories.get(suggested_cat, suggested_cat)
            msg = f"💡 Предлагаю: «{cat_name}»\n\nПолучил ссылку! Выбери категорию:"

        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=msg,
            keyboard=get_category_keyboard(highlight_cat=suggested_cat),
            random_id=event.obj.message["random_id"],
        )
        return

    # Если ожидаем выбор категории
    if state.get("awaiting_category"):
        handle_category_selection(vk, event, text, state)
        return

    # Если ожидаем выбор подкатегории
    if state.get("awaiting_subcategory"):
        handle_subcategory_selection(vk, event, text, state)
        return

    # Если ожидаем выбор названия
    if state.get("awaiting_name"):
        handle_name_selection(vk, event, text, state)
        return

    # Если не распознали
    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message="Отправь ссылку на модель с MakerWorld, Thingiverse или Printables.",
        random_id=event.obj.message["random_id"],
    )


def guess_category_from_url(url: str) -> str:
    """Пытается угадать категорию по URL модели."""
    url_lower = url.lower()
    keywords = {
        "home": ["home", "house", "decor", "interior", "planter", "vase", "lamp", "light", "holder", "hook", "shelf", "box", "container", "storage", "rope", "kashpo"],
        "kitchen": ["kitchen", "mug", "cup", "plate", "spoon", "fork", "knife", "organizer", "rack", "tea", "coffee"],
        "figures": ["figure", "statue", "figurine", "character", "robot", "dragon", "warrior", "batman", "star-wars", "marvel", "lotr", "gollum", "gate", "minas", "lord", "rings", "hobbit", "gandalf", "frodo", "aragorn", "elf", "orc", "sauron", "middle-earth", "shire", "argonath", "funko", "pop", "anime", "manga", "pokemon", "mario", "zelda", "link", "hero", "villain", "monster", "creature", "dinosaur", "t-rex", "skeleton", "skull", "face", "head", "body", "animal", "cat", "dog", "bear", "lion", "wolf", "bird", "fish", "insect", "spider", "bug", "bat", "frog", "turtle", "rabbit", "fox", "deer", "horse", "cow", "pig", "sheep", "goat", "chicken", "duck", "swan", "eagle", "owl", "penguin", "whale", "dolphin", "shark", "octopus", "crab", "lobster", "snail", "butterfly", "bee", "ant", "ladybug", "caterpillar", "worm", "snake", "lizard", "turtle", "frog", "toad", "newt", "salamander", "gecko", "chameleon", "iguana", "crocodile", "alligator", "hippo", "rhino", "elephant", "giraffe", "zebra", "monkey", "ape", "gorilla", "chimpanzee", "orangutan", "panda", "koala", "sloth", "raccoon", "hamster", "guinea-pig", "mouse", "rat", "squirrel", "hedgehog", "mole", "bat", "hedgehog"],
        "games": ["game", "chess", "dice", "token", "miniature", "dnd", "warhammer", "puzzle", "csgo", "fortnite", "minecraft", "Among", "Us"],
        "tools": ["tool", "wrench", "holder", "clip", "mount", "bracket", "adapter", "gadget", "keycap", "keychain"],
        "auto": ["car", "auto", "vehicle", "bike", "motorcycle", "phone-holder", "charger", "cable", "tesla", "wheel", "tire"],
        "lighting": ["lamp", "light", "led", "chandelier", "sconce", "lantern", "neon"],
        "storage": ["storage", "organizer", "drawer", "shelf", "rack", "stand", "case", "box", "basket"],
        "wardrobe": ["hanger", "hook", "closet", "wardrobe", "shoe", "belt", "coat", "jacket"],
        "parts": ["part", "gear", "bearing", "bushing", "connector", "screw", "bolt", "nut", "spring", "washer"],
    }
    for cat_id, words in keywords.items():
        for word in words:
            if word in url_lower:
                return cat_id
    return None


def handle_category_selection(vk, event, text, state):
    """Обработка выбора категории."""
    categories = load_categories()

    # Обработка callback кнопок
    if text.startswith("cat:"):
        cat_id = text.split(":")[1]
    else:
        cat_id = text

    if cat_id == "new":
        state["awaiting_new_cat"] = True
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Отправь название новой категории на русском.\nНапример: «Одежда» или «Автозапчасти»",
            random_id=event.obj.message["random_id"],
        )
        return

    if cat_id not in categories:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Такой категории нет. Выбери из списка или создай новую.",
            keyboard=get_category_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    state["cat_id"] = cat_id
    state["cat_name"] = categories[cat_id]
    state["awaiting_category"] = False
    state["awaiting_subcategory"] = True

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=f"Категория: «{categories[cat_id]}»\n\nВыбери подкатегорию:",
        keyboard=get_subcategory_keyboard(cat_id),
        random_id=event.obj.message["random_id"],
    )


def handle_subcategory_selection(vk, event, text, state):
    """Обработка выбора подкатегории."""

    if text.startswith("sub:"):
        sub_id = text.split(":")[1]
    else:
        sub_id = text

    if sub_id == "new":
        state["awaiting_new_sub"] = True
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Отправь название новой подкатегории на русском.\nНапример: «Star Wars» или «Миньоны»",
            random_id=event.obj.message["random_id"],
        )
        return

    if sub_id == "none":
        state["sub_id"] = None
        state["sub_name"] = None
    else:
        subcategories = load_subcategories(state["cat_id"])
        if sub_id in subcategories:
            state["sub_id"] = sub_id
            state["sub_name"] = subcategories[sub_id]
        else:
            vk.messages.send(
                peer_id=event.obj.message["peer_id"],
                message="Такой подкатегории нет. Выбери из списка или создай новую.",
                keyboard=get_subcategory_keyboard(state["cat_id"]),
                random_id=event.obj.message["random_id"],
            )
            return

    state["awaiting_subcategory"] = False
    state["awaiting_name"] = True

    # Получаем оригинальное название
    original_name = "модель"
    url = state.get("url", "")
    try:
        if "models/" in url:
            match = re.search(r'models/\d+-(.+?)(?:\?|$)', url)
            if match:
                original_name = match.group(1).replace('-', ' ').title()
    except Exception:
        pass

    translated_name = translate_to_ru(original_name)
    state["original_name"] = original_name
    state["translated_name"] = translated_name

    category_text = f"Категория: «{state['cat_name']}»"
    if state.get("sub_name"):
        category_text += f" → «{state['sub_name']}»"

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=(
            f"{category_text}\n\n"
            f"Оригинал: {original_name}\n"
            f"Перевод: {translated_name}\n\n"
            f"Выбери название или напиши своё:"
        ),
        keyboard=get_name_keyboard(original_name, translated_name),
        random_id=event.obj.message["random_id"],
    )


def handle_name_selection(vk, event, text, state):
    """Обработка выбора названия."""

    if text.startswith("name:"):
        choice = text.split(":")[1]
    else:
        choice = text

    if choice == "translated":
        final_name = state["translated_name"]
    elif choice == "original":
        final_name = state["original_name"]
    elif choice == "custom":
        state["awaiting_custom_name"] = True
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Отправь название модели на русском:",
            random_id=event.obj.message["random_id"],
        )
        return
    else:
        final_name = text

    add_model(vk, event, state, final_name)


def handle_new_category(vk, event, text, state):
    """Обработка создания новой категории."""
    cat_name = text.strip()
    cat_id = re.sub(r'[^a-zа-я0-9]', '-', cat_name.lower()).strip('-')
    cat_id = re.sub(r'-+', '-', cat_id)

    if not cat_id:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Некорректное название. Попробуй ещё раз.",
            random_id=event.obj.message["random_id"],
        )
        return

    # Добавляем категорию
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("categories", []):
            if c["id"] == cat_id:
                vk.messages.send(
                    peer_id=event.obj.message["peer_id"],
                    message="Такая категория уже существует.",
                    random_id=event.obj.message["random_id"],
                )
                return
        data["categories"].append({"id": cat_id, "name": cat_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )
        return

    git_commit_and_push(f"Добавлена категория: {cat_name} ({cat_id})")

    state["awaiting_new_cat"] = False
    state["cat_id"] = cat_id
    state["cat_name"] = cat_name
    state["awaiting_subcategory"] = True

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=f"✅ Категория «{cat_name}» создана!\n\nВыбери подкатегорию:",
        keyboard=get_subcategory_keyboard(cat_id),
        random_id=event.obj.message["random_id"],
    )


def handle_new_subcategory(vk, event, text, state):
    """Обработка создания новой подкатегории."""
    sub_name = text.strip()
    sub_id = re.sub(r'[^a-zа-я0-9]', '-', sub_name.lower()).strip('-')
    sub_id = re.sub(r'-+', '-', sub_id)

    if not sub_id:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message="Некорректное название. Попробуй ещё раз.",
            random_id=event.obj.message["random_id"],
        )
        return

    # Добавляем подкатегорию
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "subcategories" not in data:
            data["subcategories"] = {}
        cat_id = state["cat_id"]
        if cat_id not in data["subcategories"]:
            data["subcategories"][cat_id] = []
        for s in data["subcategories"][cat_id]:
            if s["id"] == sub_id:
                vk.messages.send(
                    peer_id=event.obj.message["peer_id"],
                    message="Такая подкатегория уже существует.",
                    random_id=event.obj.message["random_id"],
                )
                return
        data["subcategories"][cat_id].append({"id": sub_id, "name": sub_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )
        return

    git_commit_and_push(f"Добавлена подкатегория: {sub_name} ({cat_id}/{sub_id})")

    state["awaiting_new_sub"] = False
    state["sub_id"] = sub_id
    state["sub_name"] = sub_name
    state["awaiting_name"] = True

    # Получаем оригинальное название
    original_name = "модель"
    url = state.get("url", "")
    try:
        if "models/" in url:
            match = re.search(r'models/\d+-(.+?)(?:\?|$)', url)
            if match:
                original_name = match.group(1).replace('-', ' ').title()
    except Exception:
        pass

    translated_name = translate_to_ru(original_name)
    state["original_name"] = original_name
    state["translated_name"] = translated_name

    category_text = f"Категория: «{state['cat_name']}» → «{sub_name}»"

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=(
            f"{category_text}\n\n"
            f"Оригинал: {original_name}\n"
            f"Перевод: {translated_name}\n\n"
            f"Выбери название или напиши своё:"
        ),
        keyboard=get_name_keyboard(original_name, translated_name),
        random_id=event.obj.message["random_id"],
    )


def handle_custom_name(vk, event, text, state):
    """Обработка кастомного названия."""
    final_name = text.strip()
    add_model(vk, event, state, final_name)


def add_model(vk, event, state, final_name):
    """Добавление модели."""
    user_id = event.obj.message["from_id"]
    url = state["url"]
    cat_id = state["cat_id"]
    cat_name = state["cat_name"]
    sub_id = state.get("sub_id")

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=f"Добавляю «{final_name}» в категорию «{cat_name}»...",
        random_id=event.obj.message["random_id"],
    )

    try:
        result = run_add_model(url, cat=cat_id, sub=sub_id, name=final_name)
    except Exception as e:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )
        clear_user_state(user_id)
        return

    if result["returncode"] != 0:
        error = result["stderr"].strip() or result["stdout"].strip()
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Ошибка при добавлении:\n{error[:500]}",
            random_id=event.obj.message["random_id"],
        )
        clear_user_state(user_id)
        return

    vk.messages.send(
        peer_id=event.obj.message["peer_id"],
        message=f"✅ «{final_name}» добавлена! Пушу на сайт...",
        random_id=event.obj.message["random_id"],
    )

    git_result = git_commit_and_push(f"Добавлена модель: {final_name} (из VK)")

    if git_result["success"]:
        state["last_model_id"] = None
        try:
            model_json = json.loads(result["stdout"].strip().split('\n')[-1])
            state["last_model_id"] = model_json.get("id")
        except Exception:
            pass

        keyboard = VkKeyboard(one_time=True)
        keyboard.add_callback_button("Пропустить", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "пропустить"})
        keyboard.add_line()
        keyboard.add_callback_button("Отмена", color=VkKeyboardColor.NEGATIVE, payload={"type": "text", "text": "отмена"})

        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=(
                f"✅ «{final_name}» добавлена и запушена!\n\n"
                f"Укажи вес модели в граммах:"
            ),
            keyboard=keyboard.get_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        state["awaiting_weight"] = True
        state["awaiting_name"] = False
        state["awaiting_category"] = False
        state["awaiting_subcategory"] = False
    else:
        vk.messages.send(
            peer_id=event.obj.message["peer_id"],
            message=f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}",
            random_id=event.obj.message["random_id"],
        )
        clear_user_state(user_id)



def find_model_by_url(url):
    """Ищет модель по URL или части URL в каталоге."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        url_lower = url.lower().strip()
        for m in data.get("models", []):
            m_url = (m.get("url") or "").lower()
            m_id = (m.get("id") or "").lower()
            if url_lower in m_url or url_lower == m_id or m_url.endswith(url_lower):
                return m
        return None
    except Exception:
        return None


def get_edit_keyboard():
    """Клавиатура выбора поля для редактирования."""
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_callback_button("Вес", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "edit:weight"})
    keyboard.add_callback_button("Время печати", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "edit:time"})
    keyboard.add_line()
    keyboard.add_callback_button("Название", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "edit:name"})
    keyboard.add_callback_button("Категория", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "edit:category"})
    keyboard.add_line()
    keyboard.add_callback_button("Назад в меню", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "/start"})
    return keyboard.get_keyboard()


def handle_edit_url(vk, event, text, state):
    """Поиск модели по URL для редактирования."""
    peer_id = event.obj.message["peer_id"]

    if text.lower() in ("/start", "назад", "меню"):
        state.clear()
        vk.messages.send(
            peer_id=peer_id,
            message="Что делаем?",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    model = find_model_by_url(text)
    if not model:
        vk.messages.send(
            peer_id=peer_id,
            message="Модель не найдена. Отправь точную ссылку или ID модели, или «назад» для возврата в меню:",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    state["awaiting_edit_url"] = False
    state["awaiting_edit_field"] = True
    state["edit_model_id"] = model["id"]

    info = f"Нашёл: {model['name']}\n"
    info += f"Категория: {model.get('category', '?')}\n"
    if model.get("weight"):
        info += f"Вес: {model['weight']} г\n"
    if model.get("printTime"):
        pt = model["printTime"]
        if pt > 60:
            info += f"Время: {round(pt/60, 1)} ч\n"
        else:
            info += f"Время: {pt} мин\n"

    vk.messages.send(
        peer_id=peer_id,
        message=f"{info}\nЧто отредактировать?",
        keyboard=get_edit_keyboard(),
        random_id=event.obj.message["random_id"],
    )


def handle_edit_field(vk, event, text, state):
    """Обработка выбора поля для редактирования."""
    peer_id = event.obj.message["peer_id"]

    if text.startswith("edit:"):
        field = text.split(":")[1]
    else:
        field = text.lower()

    field_map = {
        "weight": ("вес", "Введи новый вес в граммах (или «отмена»):"),
        "time": ("printTime", "Введи новое время печати в минутах (или «отмена»):"),
        "name": ("name", "Введи новое название (или «отмена»):"),
        "category": ("category", "Введи новую категорию (или «отмена»):"),
    }

    if field not in field_map:
        vk.messages.send(
            peer_id=peer_id,
            message="Не понял. Выбери кнопку:",
            keyboard=get_edit_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    state["awaiting_edit_field"] = False
    state["awaiting_edit_value"] = True
    state["edit_field"] = field_map[field][0]

    vk.messages.send(
        peer_id=peer_id,
        message=field_map[field][1],
        random_id=event.obj.message["random_id"],
    )


def handle_edit_value(vk, event, text, state):
    """Сохранение нового значения."""
    peer_id = event.obj.message["peer_id"]
    model_id = state.get("edit_model_id")
    field = state.get("edit_field")

    if text.lower() in ("отмена", "меню", "/start"):
        state.clear()
        vk.messages.send(
            peer_id=peer_id,
            message="Отменено. Что делаем?",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    if not model_id or not field:
        state.clear()
        vk.messages.send(
            peer_id=peer_id,
            message="Ошибка состояния. Начни заново:",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for m in data.get("models", []):
            if m.get("id") == model_id:
                if field == "weight":
                    m["weight"] = float(text.replace(",", "."))
                elif field == "printTime":
                    m["printTime"] = float(text.replace(",", "."))
                elif field == "name":
                    m["name"] = text.strip()
                elif field == "category":
                    new_cat = text.strip().lower()
                    categories = {c["id"]: c["name"] for c in data.get("categories", [])}
                    if new_cat not in categories:
                        vk.messages.send(
                            peer_id=peer_id,
                            message=f"Категории «{new_cat}» нет в каталоге. Доступные: {', '.join(categories.values())}\n\nВведи заново или «отмена»:",
                            random_id=event.obj.message["random_id"],
                        )
                        return
                    m["category"] = new_cat
                break

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        git_commit_and_push(f"Обновлена модель {model_id}: {field}")

        vk.messages.send(
            peer_id=peer_id,
            message=f"✅ Готово! Модель {model_id} обновлена.\n\nЧто делаем дальше?",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
    except ValueError:
        vk.messages.send(
            peer_id=peer_id,
            message="Неверное число. Введи заново или «отмена»:",
            random_id=event.obj.message["random_id"],
        )
        return
    except Exception as e:
        vk.messages.send(
            peer_id=peer_id,
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )

    state.clear()


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


def handle_weight_input(vk, event, text, state):
    """Обработка ввода веса."""
    user_id = event.obj.message["from_id"]
    peer_id = event.obj.message["peer_id"]

    if text.lower() in ("отмена", "меню", "/start"):
        clear_user_state(user_id)
        vk.messages.send(
            peer_id=peer_id,
            message="Отменено. Что делаем?",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    if text.lower() in ("пропустить", "skip", "-", "дальше"):
        state["awaiting_weight"] = False
        state["awaiting_time"] = True

        keyboard = VkKeyboard(one_time=True)
        keyboard.add_callback_button("Пропустить", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "пропустить"})
        keyboard.add_line()
        keyboard.add_callback_button("Отмена", color=VkKeyboardColor.NEGATIVE, payload={"type": "text", "text": "отмена"})

        vk.messages.send(
            peer_id=peer_id,
            message="Ок. Укажи примерное время печати в минутах:",
            keyboard=keyboard.get_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    try:
        weight = float(text.replace(",", ".").strip())
    except ValueError:
        vk.messages.send(
            peer_id=peer_id,
            message="Не понял число. Введи вес в граммах (например 45) или «пропустить»:",
            random_id=event.obj.message["random_id"],
        )
        return

    state["weight"] = weight
    state["awaiting_weight"] = False
    state["awaiting_time"] = True

    keyboard = VkKeyboard(one_time=True)
    keyboard.add_callback_button("Пропустить", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "пропустить"})
    keyboard.add_line()
    keyboard.add_callback_button("Отмена", color=VkKeyboardColor.NEGATIVE, payload={"type": "text", "text": "отмена"})

    vk.messages.send(
        peer_id=peer_id,
        message=f"Вес: {weight} г\n\nУкажи примерное время печати в минутах:",
        keyboard=keyboard.get_keyboard(),
        random_id=event.obj.message["random_id"],
    )


def handle_time_input(vk, event, text, state):
    """Обработка ввода времени печати."""
    user_id = event.obj.message["from_id"]
    peer_id = event.obj.message["peer_id"]

    if text.lower() in ("отмена", "меню", "/start"):
        clear_user_state(user_id)
        vk.messages.send(
            peer_id=peer_id,
            message="Отменено. Что делаем?",
            keyboard=get_main_menu_keyboard(),
            random_id=event.obj.message["random_id"],
        )
        return

    print_time = None
    if text.lower() not in ("пропустить", "skip", "-", "дальше"):
        try:
            print_time = float(text.replace(",", ".").strip())
        except ValueError:
            vk.messages.send(
                peer_id=peer_id,
                message="Не понял число. Введи время в минутах (например 45) или «пропустить»:",
                random_id=event.obj.message["random_id"],
            )
            return

    weight = state.get("weight")
    model_id = state.get("last_model_id")

    if model_id and (weight is not None or print_time is not None):
        ok = update_model_data(model_id, weight=weight, print_time=print_time)
        if ok:
            git_commit_and_push(f"Обновлены данные модели: {model_id}")

    # Финальное сообщение
    info = []
    if weight is not None:
        info.append(f"Вес: {weight} г")
    if print_time is not None:
        if print_time > 60:
            info.append(f"Время печати: {round(print_time/60, 1)} ч")
        else:
            info.append(f"Время печати: {print_time} мин")
    info_text = "\n".join(info) if info else "Данные не указаны"

    vk.messages.send(
        peer_id=peer_id,
        message=(
            f"🎉 Готово!\n\n"
            f"{info_text}\n"
            f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
        ),
        random_id=event.obj.message["random_id"],
    )

    clear_user_state(user_id)


# ---------- Main ----------
def main():
    """Запуск VK бота."""
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()

    longpoll = VkBotLongPoll(vk_session, group_id=239427899)

    logger.info("VK бот запущен!")

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg_id = event.obj.message.get("id")
            if msg_id in processed_messages:
                continue
            processed_messages.add(msg_id)
            if len(processed_messages) > 1000:
                processed_messages.clear()
            # Пропускаем MESSAGE_NEW если уже обработали как callback
            cb_key = (event.obj.message.get("from_id"), event.obj.message.get("text", "").strip())
            if cb_key in callback_seen:
                del callback_seen[cb_key]
                continue
            # Очистка старых callback-записей (>10 сек)
            now = time.time()
            for k in [k for k, t in callback_seen.items() if now - t > 10]:
                del callback_seen[k]
            handle_message(vk, event)
        elif event.type == VkBotEventType.MESSAGE_EVENT:
            event_id = event.obj.event_id
            if event_id in processed_messages:
                continue
            processed_messages.add(event_id)
            try:
                vk.messages.sendMessageEventAnswer(
                    event_id=event.obj.event_id,
                    user_id=event.obj.user_id,
                    peer_id=event.obj.peer_id,
                    event_data='{"type":"show_snackbar","text":"Обрабатываю..."}'
                )
            except Exception:
                pass
            payload = event.obj.payload if hasattr(event.obj, 'payload') else {}
            if isinstance(payload, dict):
                text = payload.get("text", "")
            else:
                text = ""
            if text:
                # Помечаем что callback обработан — чтобы пропустить дубль MESSAGE_NEW
                callback_seen[(event.obj.user_id, text)] = time.time()

                class DictObj:
                    def __init__(self, d):
                        self._d = d
                    def __getitem__(self, k):
                        return self._d[k]
                    def get(self, k, default=None):
                        return self._d.get(k, default)
                fake_msg = DictObj({
                    "from_id": event.obj.user_id,
                    "peer_id": event.obj.peer_id,
                    "id": 0,
                    "text": text,
                    "random_id": 0,
                })
                event.obj.message = fake_msg
                handle_message(vk, event)


if __name__ == "__main__":
    main()

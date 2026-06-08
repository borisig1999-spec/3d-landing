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
def create_keyboard(buttons, one_time=True):
    """Создаёт клавиатуру."""
    keyboard = VkKeyboard(one_time=one_time)
    for i, (text, color, callback) in enumerate(buttons):
        if i > 0 and i % 2 == 0:
            keyboard.add_line()
        keyboard.add_callback_button(
            text,
            color=color,
            payload={"type": "text", "text": callback}
        )
    return keyboard.get_keyboard()


def get_category_keyboard():
    """Клавиатура категорий."""
    categories = load_categories()
    keyboard = VkKeyboard(one_time=True)
    row = []
    for cat_id, cat_name in categories.items():
        row.append((cat_name, VkKeyboardColor.PRIMARY, f"cat:{cat_id}"))
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
    keyboard.add_callback_button("⏭ Без подкатегории", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "sub:none"})
    return keyboard.get_keyboard()


def get_name_keyboard(original_name, translated_name):
    """Клавиатура выбора названия."""
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_callback_button(f"✅ {translated_name}", color=VkKeyboardColor.POSITIVE, payload={"type": "text", "text": "name:translated"})
    keyboard.add_line()
    keyboard.add_callback_button(f"Оригинал: {original_name}", color=VkKeyboardColor.PRIMARY, payload={"type": "text", "text": "name:original"})
    keyboard.add_line()
    keyboard.add_callback_button("✏️ Написать своё", color=VkKeyboardColor.SECONDARY, payload={"type": "text", "text": "name:custom"})
    return keyboard.get_keyboard()


# ---------- Состояния пользователей ----------
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
        user_id=event.obj.message["from_id"],
        message=(
            "Привет! Я бот для добавления 3D-моделей на сайт.\n\n"
            "Просто отправь ссылку с MakerWorld, Thingiverse или Printables — "
            "я скачаю фото, обновлю каталог и запушу на сайт.\n\n"
            "Команды:\n"
            "/help — подробная справка\n"
            "/list — последние добавленные модели"
        ),
        random_id=event.obj.message["random_id"],
    )


def handle_help(vk, event):
    """Справка."""
    vk.messages.send(
        user_id=event.obj.message["from_id"],
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
            user_id=event.obj.message["from_id"],
            message=text,
            random_id=event.obj.message["random_id"],
        )
    except Exception as e:
        vk.messages.send(
            user_id=event.obj.message["from_id"],
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )


def handle_message(vk, event):
    """Обработка сообщений."""
    user_id = event.obj.message["from_id"]
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

    # Если это ссылка на модель
    if is_model_url(text):
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
            user_id=user_id,
            message=msg,
            keyboard=get_category_keyboard(),
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
        user_id=user_id,
        message="Отправь ссылку на модель с MakerWorld, Thingiverse или Printables.",
        random_id=event.obj.message["random_id"],
    )


def guess_category_from_url(url: str) -> str:
    """Пытается угадать категорию по URL модели."""
    url_lower = url.lower()
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


def handle_category_selection(vk, event, text, state):
    """Обработка выбора категории."""
    user_id = event.obj.message["from_id"]
    categories = load_categories()

    # Обработка callback кнопок
    if text.startswith("cat:"):
        cat_id = text.split(":")[1]
    else:
        cat_id = text

    if cat_id == "new":
        state["awaiting_new_cat"] = True
        vk.messages.send(
            user_id=user_id,
            message="Отправь название новой категории на русском.\nНапример: «Одежда» или «Автозапчасти»",
            random_id=event.obj.message["random_id"],
        )
        return

    if cat_id not in categories:
        vk.messages.send(
            user_id=user_id,
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
        user_id=user_id,
        message=f"Категория: «{categories[cat_id]}»\n\nВыбери подкатегорию:",
        keyboard=get_subcategory_keyboard(cat_id),
        random_id=event.obj.message["random_id"],
    )


def handle_subcategory_selection(vk, event, text, state):
    """Обработка выбора подкатегории."""
    user_id = event.obj.message["from_id"]

    if text.startswith("sub:"):
        sub_id = text.split(":")[1]
    else:
        sub_id = text

    if sub_id == "new":
        state["awaiting_new_sub"] = True
        vk.messages.send(
            user_id=user_id,
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
                user_id=user_id,
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
        user_id=user_id,
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
    user_id = event.obj.message["from_id"]

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
            user_id=user_id,
            message="Отправь название модели на русском:",
            random_id=event.obj.message["random_id"],
        )
        return
    else:
        final_name = text

    add_model(vk, event, state, final_name)


def handle_new_category(vk, event, text, state):
    """Обработка создания новой категории."""
    user_id = event.obj.message["from_id"]
    cat_name = text.strip()
    cat_id = re.sub(r'[^a-zа-я0-9]', '-', cat_name.lower()).strip('-')
    cat_id = re.sub(r'-+', '-', cat_id)

    if not cat_id:
        vk.messages.send(
            user_id=user_id,
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
                    user_id=user_id,
                    message="Такая категория уже существует.",
                    random_id=event.obj.message["random_id"],
                )
                return
        data["categories"].append({"id": cat_id, "name": cat_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        vk.messages.send(
            user_id=user_id,
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
        user_id=user_id,
        message=f"✅ Категория «{cat_name}» создана!\n\nВыбери подкатегорию:",
        keyboard=get_subcategory_keyboard(cat_id),
        random_id=event.obj.message["random_id"],
    )


def handle_new_subcategory(vk, event, text, state):
    """Обработка создания новой подкатегории."""
    user_id = event.obj.message["from_id"]
    sub_name = text.strip()
    sub_id = re.sub(r'[^a-zа-я0-9]', '-', sub_name.lower()).strip('-')
    sub_id = re.sub(r'-+', '-', sub_id)

    if not sub_id:
        vk.messages.send(
            user_id=user_id,
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
                    user_id=user_id,
                    message="Такая подкатегория уже существует.",
                    random_id=event.obj.message["random_id"],
                )
                return
        data["subcategories"][cat_id].append({"id": sub_id, "name": sub_name})
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        vk.messages.send(
            user_id=user_id,
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
        user_id=user_id,
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
        user_id=user_id,
        message=f"Добавляю «{final_name}» в категорию «{cat_name}»...",
        random_id=event.obj.message["random_id"],
    )

    try:
        result = run_add_model(url, cat=cat_id, sub=sub_id, name=final_name)
    except Exception as e:
        vk.messages.send(
            user_id=user_id,
            message=f"Ошибка: {e}",
            random_id=event.obj.message["random_id"],
        )
        clear_user_state(user_id)
        return

    if result["returncode"] != 0:
        error = result["stderr"].strip() or result["stdout"].strip()
        vk.messages.send(
            user_id=user_id,
            message=f"Ошибка при добавлении:\n{error[:500]}",
            random_id=event.obj.message["random_id"],
        )
        clear_user_state(user_id)
        return

    vk.messages.send(
        user_id=user_id,
        message=f"✅ «{final_name}» добавлена! Пушу на сайт...",
        random_id=event.obj.message["random_id"],
    )

    git_result = git_commit_and_push(f"Добавлена модель: {final_name} (из VK)")

    if git_result["success"]:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🎉 Готово!\n\n"
                f"Модель: {final_name}\n"
                f"Категория: {cat_name}\n"
                f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
            ),
            random_id=event.obj.message["random_id"],
        )
    else:
        vk.messages.send(
            user_id=user_id,
            message=f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}",
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
            handle_message(vk, event)


if __name__ == "__main__":
    main()

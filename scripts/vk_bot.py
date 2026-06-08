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

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

try:
    from deep_translator import GoogleTranslator
    _TRANSLATOR = GoogleTranslator(source='en', target='ru')
except Exception:
    _TRANSLATOR = None

# ---------- НАСТРОЙКИ ----------
TOKEN = os.environ.get("VK_BOT_TOKEN")
if not TOKEN:
    raise ValueError("VK_BOT_TOKEN не найден в .env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "models.json"
SCRIPT_ADD = PROJECT_ROOT / "scripts" / "add_model.py"

_allowed_raw = os.environ.get("VK_ALLOWED_USERS", "362356023")
ALLOWED_USERS = {int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip()}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Кэш models.json ----------
_cache = {"data": None, "mtime": 0}


def load_data() -> dict:
    """Читает models.json с кэшем по mtime."""
    try:
        mt = DATA_FILE.stat().st_mtime
    except OSError:
        return {"categories": [], "subcategories": {}, "models": []}
    if mt != _cache["mtime"]:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            _cache["data"] = json.load(f)
        _cache["mtime"] = mt
    return _cache["data"]


def save_data(data: dict):
    """Сохраняет models.json и сбрасывает кэш."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _cache["mtime"] = 0


def load_categories() -> dict:
    return {c["id"]: c["name"] for c in load_data().get("categories", [])}


def load_subcategories(cat_id: str) -> dict:
    return {s["id"]: s["name"] for s in load_data().get("subcategories", {}).get(cat_id, [])}


# ---------- Хелперы ----------
def send_msg(vk, event, text, keyboard=None):
    """Отправка сообщения. Убирает дублирование peer_id/random_id."""
    params = {
        "peer_id": event.obj.message["peer_id"],
        "message": text,
        "random_id": event.obj.message["random_id"],
    }
    if keyboard:
        params["keyboard"] = keyboard
    vk.messages.send(**params)


def slugify(text: str) -> str:
    """Делает slug из текста: lowercase, кириллица→латиница не нужна, просто чистим."""
    s = re.sub(r'[^a-zа-я0-9]', '-', text.lower()).strip('-')
    return re.sub(r'-+', '-', s)


def is_model_url(text: str) -> bool:
    """Проверяет, похожа ли строка на URL модели."""
    patterns = [
        r"makerworld\.com/.*/?models/",
        r"thingiverse\.com/thing:",
        r"printables\.com/model/",
    ]
    return any(re.search(p, text) for p in patterns)


def sanitize_name(name: str) -> str:
    """Очищает название модели от HTML-тегов и ограничивает длину."""
    name = re.sub(r'<[^>]+>', '', name)
    name = name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    name = name.strip()
    return name[:100] if name else "модель"


def translate_to_ru(text: str) -> str:
    """Переводит текст с английского на русский."""
    if not _TRANSLATOR:
        return text
    try:
        result = _TRANSLATOR.translate(text)
        return result if result else text
    except Exception:
        return text


def extract_name_from_url(url: str) -> str:
    """Извлекает название модели из URL."""
    match = re.search(r'models/\d+-(.+?)(?:\?|$)', url)
    if match:
        return match.group(1).replace('-', ' ').title()
    return "модель"


def is_cancel(text: str) -> bool:
    """Проверяет, является ли текст командой отмены."""
    return text.lower() in ("отмена", "меню", "/start")


def is_skip(text: str) -> bool:
    """Проверяет, является ли текст командой пропуска."""
    return text.lower() in ("пропустить", "skip", "-", "дальше")


def make_skip_cancel_kb():
    """Клавиатура «Пропустить» + «Отмена»."""
    kb = VkKeyboard(one_time=True)
    kb.add_callback_button("Пропустить", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "пропустить"})
    kb.add_line()
    kb.add_callback_button("Отмена", color=VkKeyboardColor.NEGATIVE,
                           payload={"type": "text", "text": "отмена"})
    return kb.get_keyboard()


def run_add_model(url: str, cat: str = None, sub: str = None, name: str = None) -> dict:
    """Запускает add_model.py и возвращает результат."""
    cmd = [sys.executable, str(SCRIPT_ADD), url, "--add"]
    if cat:
        cmd.extend(["--cat", cat])
    if sub:
        cmd.extend(["--sub", sub])
    if name:
        cmd.extend(["--name", name])
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(PROJECT_ROOT), timeout=120)
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def git_commit_and_push(message: str) -> dict:
    """Коммитит и пушит изменения на GitHub."""
    status = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if not status.stdout.strip():
        return {"success": True, "log": "Нет изменений"}
    for cmd in [
        ["git", "add", "data/models.json", "images/"],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=str(PROJECT_ROOT), timeout=60)
        if r.returncode != 0 and "nothing to commit" not in r.stdout:
            return {"success": False, "log": r.stderr[:200]}
    return {"success": True, "log": "OK"}


# ---------- Дедупликация / Rate limiting ----------
processed_messages = set()
callback_seen = {}
add_timestamps = {}

user_states = {}


def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {}
    return user_states[user_id]


def clear_user_state(user_id):
    user_states.pop(user_id, None)


def check_rate_limit(user_id, max_per_hour=10):
    now = time.time()
    stamps = add_timestamps.setdefault(user_id, [])
    add_timestamps[user_id] = [t for t in stamps if now - t < 3600]
    if len(add_timestamps[user_id]) >= max_per_hour:
        return False
    add_timestamps[user_id].append(now)
    return True


# ---------- Callback DictObj (один раз) ----------
class _DictObj:
    def __init__(self, d):
        self._d = d
    def __getitem__(self, k):
        return self._d[k]
    def get(self, k, default=None):
        return self._d.get(k, default)


# ---------- Клавиатуры ----------
def get_main_menu_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_callback_button("Добавить модель", color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "menu:add"})
    kb.add_line()
    kb.add_callback_button("Редактировать модель", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "menu:edit"})
    return kb.get_keyboard()


def _add_rows(keyboard, items):
    """Добавляет кнопки items=[(label, color, payload)] по 2 в ряд."""
    row = []
    for label, color, payload in items:
        row.append((label, color, payload))
        if len(row) == 2:
            keyboard.add_callback_button(row[0][0], color=row[0][1],
                                         payload={"type": "text", "text": row[0][2]})
            keyboard.add_callback_button(row[1][0], color=row[1][1],
                                         payload={"type": "text", "text": row[1][2]})
            keyboard.add_line()
            row = []
    if row:
        keyboard.add_callback_button(row[0][0], color=row[0][1],
                                     payload={"type": "text", "text": row[0][2]})
        keyboard.add_line()


def get_category_keyboard(highlight_cat=None):
    categories = load_categories()
    kb = VkKeyboard(one_time=True)
    items = []
    for cat_id, cat_name in categories.items():
        color = VkKeyboardColor.POSITIVE if cat_id == highlight_cat else VkKeyboardColor.PRIMARY
        label = f"👉 {cat_name}" if cat_id == highlight_cat else cat_name
        items.append((label, color, f"cat:{cat_id}"))
    _add_rows(kb, items)
    kb.add_callback_button("➕ Новая категория", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "cat:new"})
    return kb.get_keyboard()


def get_subcategory_keyboard(cat_id):
    subcategories = load_subcategories(cat_id)
    kb = VkKeyboard(one_time=True)
    items = [(name, VkKeyboardColor.PRIMARY, f"sub:{sid}") for sid, name in subcategories.items()]
    _add_rows(kb, items)
    kb.add_callback_button("➕ Новая подкатегория", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "sub:new"})
    kb.add_callback_button("Без подкатегории", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "sub:none"})
    return kb.get_keyboard()


def get_name_keyboard(original_name, translated_name):
    kb = VkKeyboard(one_time=True)
    kb.add_callback_button(f"✅ {translated_name}"[:40], color=VkKeyboardColor.POSITIVE,
                           payload={"type": "text", "text": "name:translated"})
    kb.add_line()
    kb.add_callback_button(f"Оригинал: {original_name}"[:40], color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "name:original"})
    kb.add_line()
    kb.add_callback_button("Написать своё", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "name:custom"})
    return kb.get_keyboard()


def get_edit_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_callback_button("Вес", color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "edit:weight"})
    kb.add_callback_button("Время печати", color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "edit:time"})
    kb.add_line()
    kb.add_callback_button("Название", color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "edit:name"})
    kb.add_callback_button("Категория", color=VkKeyboardColor.PRIMARY,
                           payload={"type": "text", "text": "edit:category"})
    kb.add_line()
    kb.add_callback_button("Назад в меню", color=VkKeyboardColor.SECONDARY,
                           payload={"type": "text", "text": "/start"})
    return kb.get_keyboard()


# ---------- Обработка команд ----------
def guess_category_from_url(url: str) -> str:
    url_lower = url.lower()
    keywords = {
        "home": ["home", "house", "decor", "interior", "planter", "vase", "lamp", "light",
                 "holder", "hook", "shelf", "box", "container", "storage", "rope", "kashpo"],
        "kitchen": ["kitchen", "mug", "cup", "plate", "spoon", "fork", "knife", "organizer",
                     "rack", "tea", "coffee"],
        "figures": ["figure", "statue", "figurine", "character", "robot", "dragon", "warrior",
                    "batman", "star-wars", "marvel", "lotr", "gollum", "gate", "minas", "lord",
                    "rings", "hobbit", "gandalf", "frodo", "aragorn", "elf", "orc", "sauron",
                    "middle-earth", "shire", "argonath", "funko", "pop", "anime", "manga",
                    "pokemon", "mario", "zelda", "link", "hero", "villain", "monster", "creature",
                    "dinosaur", "t-rex", "skeleton", "skull", "animal", "cat", "dog", "bear",
                    "lion", "wolf", "bird", "fish", "spider", "frog", "turtle", "rabbit", "fox",
                    "deer", "horse", "monkey", "panda", "koala"],
        "games": ["game", "chess", "dice", "token", "miniature", "dnd", "warhammer", "puzzle",
                  "minecraft"],
        "tools": ["tool", "wrench", "clip", "mount", "bracket", "adapter", "gadget",
                  "keycap", "keychain"],
        "auto": ["car", "auto", "vehicle", "bike", "motorcycle", "phone-holder", "charger",
                 "cable", "tesla", "wheel", "tire"],
        "parts": ["part", "gear", "bearing", "bushing", "connector", "screw", "bolt", "nut",
                  "spring", "washer"],
    }
    for cat_id, words in keywords.items():
        for word in words:
            if word in url_lower:
                return cat_id
    return None


def create_category(slug: str, name: str) -> bool:
    """Создаёт категорию. Возвращает True если создана, False если уже есть."""
    data = load_data()
    for c in data.get("categories", []):
        if c["id"] == slug:
            return False
    data["categories"].append({"id": slug, "name": name})
    save_data(data)
    return True


def create_subcategory(cat_id: str, slug: str, name: str) -> bool:
    """Создаёт подкатегорию. Возвращает True если создана."""
    data = load_data()
    subs = data.setdefault("subcategories", {}).setdefault(cat_id, [])
    for s in subs:
        if s["id"] == slug:
            return False
    subs.append({"id": slug, "name": name})
    save_data(data)
    return True


def update_model_field(model_id: str, field: str, value) -> bool:
    """Обновляет поле модели. Возвращает True если нашёл модель."""
    data = load_data()
    for m in data.get("models", []):
        if m.get("id") == model_id:
            m[field] = value
            save_data(data)
            return True
    return False


def find_model_by_url(url: str):
    """Ищет модель по URL или части URL."""
    url_lower = url.lower().strip()
    for m in load_data().get("models", []):
        m_url = (m.get("url") or "").lower()
        m_id = (m.get("id") or "").lower()
        if url_lower in m_url or url_lower == m_id or m_url.endswith(url_lower):
            return m
    return None


# ---------- Основные обработчики ----------
def handle_start(vk, event):
    send_msg(vk, event, "Привет! Что делаем?", get_main_menu_keyboard())


def handle_help(vk, event):
    send_msg(vk, event, (
        "Как пользоваться:\n\n"
        "1. Отправь ссылку на модель:\n"
        "   https://makerworld.com/ru/models/2016647\n\n"
        "2. Выбери категорию\n\n"
        "3. Выбери подкатегорию или пропусти\n\n"
        "4. Выбери название (перевод/оригинал/своё)\n\n"
        "5. Готово! Модель добавлена на сайт\n\n"
        "Или просто отправь ссылку — я всё покажу!"
    ))


def handle_list(vk, event):
    models = load_data().get("models", [])[-5:][::-1]
    categories = load_categories()
    text = "Последние добавленные модели:\n\n"
    for i, m in enumerate(models, 1):
        cat = categories.get(m.get("category", ""), m.get("category", "?"))
        text += f"{i}. {m['name']}\n   Категория: {cat}\n   {m.get('url', '')}\n\n"
    send_msg(vk, event, text)


def handle_message(vk, event):
    user_id = event.obj.message["from_id"]
    if user_id not in ALLOWED_USERS:
        send_msg(vk, event, "У тебя нет доступа к этому боту.")
        return

    text = event.obj.message.get("text", "").strip()
    state = get_user_state(user_id)

    # Команды
    if text == "/start":
        return handle_start(vk, event)
    if text == "/help":
        return handle_help(vk, event)
    if text == "/list":
        return handle_list(vk, event)

    # Меню
    if text == "menu:add":
        state.clear()
        return send_msg(vk, event, "Отправь ссылку на модель с MakerWorld, Thingiverse или Printables:")
    if text == "menu:edit":
        state.clear()
        state["awaiting_edit_url"] = True
        return send_msg(vk, event, "Отправь ссылку на модель, которую нужно отредактировать:")

    # Редактирование
    if state.get("awaiting_edit_url"):
        return _handle_edit_url(vk, event, text, state)
    if state.get("awaiting_edit_field"):
        return _handle_edit_field(vk, event, text, state)
    if state.get("awaiting_edit_value"):
        return _handle_edit_value(vk, event, text, state)

    # Создание новой категории/подкатегории
    if state.get("awaiting_new_cat"):
        return _handle_new_category(vk, event, text, state)
    if state.get("awaiting_new_cat_in_edit"):
        return _handle_new_category_in_edit(vk, event, text, state)
    if state.get("awaiting_new_sub"):
        return _handle_new_subcategory(vk, event, text, state)

    # Кастомное название
    if state.get("awaiting_custom_name"):
        state["awaiting_custom_name"] = False
        state["awaiting_name"] = False
        return _add_model(vk, event, state, text.strip())

    # Вес / Время
    if state.get("awaiting_weight"):
        return _handle_weight_input(vk, event, text, state)
    if state.get("awaiting_time"):
        return _handle_time_input(vk, event, text, state)

    # URL на модель — режим добавления
    if is_model_url(text):
        state.clear()
        state["url"] = text
        state["awaiting_category"] = True
        suggested = guess_category_from_url(text)
        categories = load_categories()
        msg = "Получил ссылку! Выбери категорию:"
        if suggested:
            msg = f"💡 Предлагаю: «{categories.get(suggested, suggested)}»\n\nПолучил ссылку! Выбери категорию:"
        send_msg(vk, event, msg, get_category_keyboard(highlight_cat=suggested))
        return

    # Выбор категории / подкатегории / названия
    if state.get("awaiting_category"):
        return _handle_category_selection(vk, event, text, state)
    if state.get("awaiting_subcategory"):
        return _handle_subcategory_selection(vk, event, text, state)
    if state.get("awaiting_name"):
        return _handle_name_selection(vk, event, text, state)

    send_msg(vk, event, "Отправь ссылку на модель с MakerWorld, Thingiverse или Printables.")


# ---------- Добавление модели ----------
def _add_model(vk, event, state, final_name):
    user_id = event.obj.message["from_id"]
    final_name = sanitize_name(final_name)

    if not check_rate_limit(user_id):
        send_msg(vk, event, "Слишком много добавлений. Подожди час и попробуй снова.")
        return clear_user_state(user_id)

    send_msg(vk, event, f"Добавляю «{final_name}» в категорию «{state['cat_name']}»...")

    result = run_add_model(state["url"], cat=state["cat_id"],
                           sub=state.get("sub_id"), name=final_name)
    if result["returncode"] != 0:
        send_msg(vk, event, "Ошибка при добавлении модели. Попробуй позже или напиши /start заново.")
        logger.error(f"add_model failed: {result['stderr'][:300]}")
        return clear_user_state(user_id)

    send_msg(vk, event, f"✅ «{final_name}» добавлена! Пушу на сайт...")

    git_result = git_commit_and_push(f"Добавлена модель: {final_name} (из VK)")
    if not git_result["success"]:
        send_msg(vk, event, "Модель добавлена, но не удалось запушить на сайт. Попробуй позже.")
        logger.error(f"git push failed: {git_result['log'][:200]}")
        return clear_user_state(user_id)

    # Извлекаем ID добавленной модели
    state["last_model_id"] = None
    try:
        model_json = json.loads(result["stdout"].strip().split('\n')[-1])
        state["last_model_id"] = model_json.get("id")
    except Exception:
        pass

    send_msg(vk, event,
             f"✅ «{final_name}» добавлена и запушена!\n\nУкажи вес модели в граммах:",
             make_skip_cancel_kb())
    state["awaiting_weight"] = True


def _handle_weight_input(vk, event, text, state):
    user_id = event.obj.message["from_id"]
    if is_cancel(text):
        clear_user_state(user_id)
        return send_msg(vk, event, "Отменено. Что делаем?", get_main_menu_keyboard())

    if is_skip(text):
        state["awaiting_weight"] = False
        state["awaiting_time"] = True
        return send_msg(vk, event, "Ок. Укажи примерное время печати в минутах:",
                        make_skip_cancel_kb())

    try:
        weight = float(text.replace(",", ".").strip())
    except ValueError:
        return send_msg(vk, event, "Не понял число. Введи вес в граммах (например 45) или «пропустить»:")

    state["weight"] = weight
    state["awaiting_weight"] = False
    state["awaiting_time"] = True
    send_msg(vk, event, f"Вес: {weight} г\n\nУкажи примерное время печати в минутах:",
             make_skip_cancel_kb())


def _handle_time_input(vk, event, text, state):
    user_id = event.obj.message["from_id"]
    if is_cancel(text):
        clear_user_state(user_id)
        return send_msg(vk, event, "Отменено. Что делаем?", get_main_menu_keyboard())

    print_time = None
    if not is_skip(text):
        try:
            print_time = float(text.replace(",", ".").strip())
        except ValueError:
            return send_msg(vk, event, "Не понял число. Введи время в минутах (например 45) или «пропустить»:")

    weight = state.get("weight")
    model_id = state.get("last_model_id")

    if model_id and (weight is not None or print_time is not None):
        data = load_data()
        for m in data.get("models", []):
            if m.get("id") == model_id:
                if weight is not None:
                    m["weight"] = weight
                if print_time is not None:
                    m["printTime"] = print_time
                break
        save_data(data)
        git_commit_and_push(f"Обновлены данные модели: {model_id}")

    info = []
    if weight is not None:
        info.append(f"Вес: {weight} г")
    if print_time is not None:
        info.append(f"Время печати: {round(print_time/60, 1)} ч" if print_time > 60
                    else f"Время печати: {print_time} мин")

    send_msg(vk, event,
             f"🎉 Готово!\n\n{'  '.join(info) if info else 'Данные не указаны'}\n"
             f"Сайт: https://borisig1999-spec.github.io/3d-landing/")
    clear_user_state(user_id)


# ---------- Категории / Подкатегории ----------
def _handle_category_selection(vk, event, text, state):
    cat_id = text.split(":")[1] if text.startswith("cat:") else text
    categories = load_categories()

    if cat_id == "new":
        state["awaiting_new_cat"] = True
        return send_msg(vk, event, "Отправь название новой категории на русском.\nНапример: «Одежда» или «Автозапчасти»")

    if cat_id not in categories:
        return send_msg(vk, event, "Такой категории нет. Выбери из списка или создай новую.",
                        get_category_keyboard())

    state["cat_id"] = cat_id
    state["cat_name"] = categories[cat_id]
    state["awaiting_category"] = False
    state["awaiting_subcategory"] = True
    send_msg(vk, event, f"Категория: «{categories[cat_id]}»\n\nВыбери подкатегорию:",
             get_subcategory_keyboard(cat_id))


def _handle_subcategory_selection(vk, event, text, state):
    sub_id = text.split(":")[1] if text.startswith("sub:") else text

    if sub_id == "new":
        state["awaiting_new_sub"] = True
        return send_msg(vk, event, "Отправь название новой подкатегории на русском.\nНапример: «Star Wars» или «Миньоны»")

    if sub_id == "none":
        state["sub_id"] = None
        state["sub_name"] = None
    else:
        subcategories = load_subcategories(state["cat_id"])
        if sub_id not in subcategories:
            return send_msg(vk, event, "Такой подкатегории нет. Выбери из списка или создай новую.",
                            get_subcategory_keyboard(state["cat_id"]))
        state["sub_id"] = sub_id
        state["sub_name"] = subcategories[sub_id]

    state["awaiting_subcategory"] = False
    state["awaiting_name"] = True

    original_name = extract_name_from_url(state.get("url", ""))
    translated_name = translate_to_ru(original_name)
    state["original_name"] = original_name
    state["translated_name"] = translated_name

    cat_text = f"Категория: «{state['cat_name']}»"
    if state.get("sub_name"):
        cat_text += f" → «{state['sub_name']}»"

    send_msg(vk, event,
             f"{cat_text}\n\nОригинал: {original_name}\nПеревод: {translated_name}\n\n"
             f"Выбери название или напиши своё:",
             get_name_keyboard(original_name, translated_name))


def _handle_name_selection(vk, event, text, state):
    choice = text.split(":")[1] if text.startswith("name:") else text

    if choice == "translated":
        final_name = state["translated_name"]
    elif choice == "original":
        final_name = state["original_name"]
    elif choice == "custom":
        state["awaiting_custom_name"] = True
        return send_msg(vk, event, "Отправь название модели на русском:")
    else:
        final_name = text

    _add_model(vk, event, state, final_name)


def _handle_new_category(vk, event, text, state):
    cat_name = text.strip()
    cat_id = slugify(cat_name)
    if not cat_id:
        return send_msg(vk, event, "Некорректное название. Попробуй ещё раз.")

    if not create_category(cat_id, cat_name):
        return send_msg(vk, event, "Такая категория уже существует.")

    git_commit_and_push(f"Добавлена категория: {cat_name} ({cat_id})")

    state["awaiting_new_cat"] = False
    state["cat_id"] = cat_id
    state["cat_name"] = cat_name
    state["awaiting_subcategory"] = True
    send_msg(vk, event, f"✅ Категория «{cat_name}» создана!\n\nВыбери подкатегорию:",
             get_subcategory_keyboard(cat_id))


def _handle_new_category_in_edit(vk, event, text, state):
    peer_id = event.obj.message["peer_id"]
    model_id = state.get("edit_model_id")
    cat_name = text.strip()
    cat_id = slugify(cat_name)
    if not cat_id:
        return send_msg(vk, event, "Некорректное название. Попробуй ещё раз.")

    if not create_category(cat_id, cat_name):
        return send_msg(vk, event, "Такая категория уже существует.")

    update_model_field(model_id, "category", cat_id)
    git_commit_and_push(f"Добавлена категория и обновлена модель {model_id}: {cat_name}")

    state.clear()
    send_msg(vk, event, f"✅ Категория «{cat_name}» создана и модель обновлена!\n\nЧто делаем дальше?",
             get_main_menu_keyboard())


def _handle_new_subcategory(vk, event, text, state):
    sub_name = text.strip()
    sub_id = slugify(sub_name)
    if not sub_id:
        return send_msg(vk, event, "Некорректное название. Попробуй ещё раз.")

    cat_id = state["cat_id"]
    if not create_subcategory(cat_id, sub_id, sub_name):
        return send_msg(vk, event, "Такая подкатегория уже существует.")

    git_commit_and_push(f"Добавлена подкатегория: {sub_name} ({cat_id}/{sub_id})")

    state["awaiting_new_sub"] = False
    state["sub_id"] = sub_id
    state["sub_name"] = sub_name
    state["awaiting_name"] = True

    original_name = extract_name_from_url(state.get("url", ""))
    translated_name = translate_to_ru(original_name)
    state["original_name"] = original_name
    state["translated_name"] = translated_name

    send_msg(vk, event,
             f"Категория: «{state['cat_name']}» → «{sub_name}»\n\n"
             f"Оригинал: {original_name}\nПеревод: {translated_name}\n\n"
             f"Выбери название или напиши своё:",
             get_name_keyboard(original_name, translated_name))


# ---------- Редактирование ----------
def _handle_edit_url(vk, event, text, state):
    if text.lower() in ("/start", "назад", "меню"):
        state.clear()
        return send_msg(vk, event, "Что делаем?", get_main_menu_keyboard())

    model = find_model_by_url(text)
    if not model:
        return send_msg(vk, event, "Модель не найдена. Отправь точную ссылку или ID модели, или «назад»:",
                        get_main_menu_keyboard())

    state["awaiting_edit_url"] = False
    state["awaiting_edit_field"] = True
    state["edit_model_id"] = model["id"]

    info = f"Нашёл: {model['name']}\nКатегория: {model.get('category', '?')}\n"
    if model.get("weight"):
        info += f"Вес: {model['weight']} г\n"
    if model.get("printTime"):
        pt = model["printTime"]
        info += f"Время: {round(pt/60, 1)} ч\n" if pt > 60 else f"Время: {pt} мин\n"

    send_msg(vk, event, f"{info}\nЧто отредактировать?", get_edit_keyboard())


def _handle_edit_field(vk, event, text, state):
    peer_id = event.obj.message["peer_id"]
    field = text.split(":")[1] if text.startswith("edit:") else text.lower()

    field_map = {
        "weight": ("weight", "Введи новый вес в граммах (или «отмена»):"),
        "time": ("printTime", "Введи новое время печати в минутах (или «отмена»):"),
        "name": ("name", "Введи новое название (или «отмена»):"),
        "category": ("category", "Выбери новую категорию:"),
    }

    if field not in field_map:
        return send_msg(vk, event, "Не понял. Выбери кнопку:", get_edit_keyboard())

    state["awaiting_edit_field"] = False
    state["awaiting_edit_value"] = True
    state["edit_field"] = field_map[field][0]

    if field == "category":
        send_msg(vk, event, field_map[field][1], get_category_keyboard())
    else:
        kb = VkKeyboard(one_time=True)
        kb.add_callback_button("Отмена", color=VkKeyboardColor.NEGATIVE,
                               payload={"type": "text", "text": "отмена"})
        send_msg(vk, event, field_map[field][1], kb.get_keyboard())


def _handle_edit_value(vk, event, text, state):
    peer_id = event.obj.message["peer_id"]
    model_id = state.get("edit_model_id")
    field = state.get("edit_field")

    if is_cancel(text):
        state.clear()
        return send_msg(vk, event, "Отменено. Что делаем?", get_main_menu_keyboard())

    if not model_id or not field:
        state.clear()
        return send_msg(vk, event, "Ошибка состояния. Начни заново:", get_main_menu_keyboard())

    try:
        if field == "weight":
            value = float(text.replace(",", "."))
        elif field == "printTime":
            value = float(text.replace(",", "."))
        elif field == "name":
            value = sanitize_name(text)
        elif field == "category":
            new_cat = text.split(":")[1] if text.startswith("cat:") else text.strip().lower()
            if new_cat == "new":
                state["awaiting_edit_value"] = False
                state["awaiting_new_cat_in_edit"] = True
                return send_msg(vk, event, "Отправь название новой категории на русском.\nНапример: «Одежда» или «Автозапчасти»")
            categories = load_categories()
            if new_cat not in categories:
                return send_msg(vk, event, f"Категории «{new_cat}» нет в каталоге.\n\nВыбери из списка или создай новую:",
                                get_category_keyboard())
            value = new_cat
        else:
            value = text.strip()

        update_model_field(model_id, field, value)
        git_commit_and_push(f"Обновлена модель {model_id}: {field}")
        send_msg(vk, event, f"✅ Готово! Модель {model_id} обновлена.\n\nЧто делаем дальше?",
                 get_main_menu_keyboard())
    except ValueError:
        return send_msg(vk, event, "Неверное число. Введи заново или «отмена»:")
    except Exception as e:
        send_msg(vk, event, "Произошла ошибка. Попробуй заново.")
        logger.error(f"edit_value error: {e}")

    state.clear()


# ---------- Main ----------
def main():
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
            cb_key = (event.obj.message.get("from_id"), event.obj.message.get("text", "").strip())
            if cb_key in callback_seen:
                del callback_seen[cb_key]
                continue
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
            text = payload.get("text", "") if isinstance(payload, dict) else ""
            if text:
                callback_seen[(event.obj.user_id, text)] = time.time()
                fake_msg = _DictObj({
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

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
TOKEN = os.environ.get("TG_BOT_TOKEN", "8970161294:AAH7QNp4MUoE586DRTIbPKHVJPJLlqdICu0")
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Вспомогательные функции ----------
def is_model_url(text: str) -> bool:
    """Проверяет, похожа ли строка на URL модели."""
    patterns = [
        r"makerworld\.com/.*/models/",
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


def run_add_model(url: str, cat: str = None, tags: str = "", featured: bool = False, name: str = None) -> dict:
    """Запускает add_model.py и возвращает результат."""
    cmd = [sys.executable, str(SCRIPT_ADD), url, "--add"]
    if cat:
        cmd.extend(["--cat", cat])
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
        "2. Я спрошу категорию — выбери из списка\n\n"
        "3. Готово! Модель добавлена на сайт\n\n"
        "Добавление категорий:\n"
        "/addcat figures Фигурки\n"
        "/addsub figures star-wars Star Wars\n\n"
        "Или просто отправь ссылку — я спрошу категорию."
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


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на модель."""
    # Если ожидаем название модели — передаём в handle_model_name
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

    # Показываем кнопки категорий
    categories = load_categories()
    keyboard = []
    row = []
    for cat_id, cat_name in categories.items():
        row.append(InlineKeyboardButton(cat_name, callback_data=f"cat:{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await update.message.reply_text(
        "Получил ссылку! Выбери категорию:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории — показывает оригинальное название и перевод."""
    query = update.callback_query
    await query.answer()

    cat_id = query.data.split(":")[1]
    url = context.user_data.get("pending_url")

    if not url:
        await query.edit_message_text("Ошибка: ссылка потерялась. Отправь заново.")
        return

    categories = load_categories()
    cat_name = categories.get(cat_id, cat_id)

    # Сохраняем категорию
    context.user_data["pending_cat"] = cat_id
    context.user_data["pending_cat_name"] = cat_name

    # Получаем оригинальное название (быстро, без браузера)
    original_name = "модель"
    try:
        # Пробуем достать название из URL или описания
        if "models/" in url:
            # Извлекаем из URL
            match = re.search(r'models/\d+-(.+?)(?:\?|$)', url)
            if match:
                original_name = match.group(1).replace('-', ' ').title()
    except Exception:
        pass

    # Переводим
    translated_name = translate_to_ru(original_name)

    # Сохраняем оба варианта
    context.user_data["original_name"] = original_name
    context.user_data["translated_name"] = translated_name

    # Показываем варианты с кнопками
    keyboard = [
        [InlineKeyboardButton(f"✅ «{translated_name}»", callback_data="name:translated")],
        [InlineKeyboardButton(f"Оригинал: «{original_name}»", callback_data="name:original")],
        [InlineKeyboardButton("✏️ Написать своё", callback_data="name:custom")],
    ]

    await query.edit_message_text(
        f"Категория: «{cat_name}»\n\n"
        f"Оригинал: {original_name}\n"
        f"Перевод: {translated_name}\n\n"
        f"Выбери название или напиши своё:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


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
    try:
        result = run_add_model(url, cat=cat_id, name=final_name)
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
        await query.message.reply_text(
            f"🎉 Готово!\n\n"
            f"Модель: {final_name}\n"
            f"Категория: {cat_name}\n"
            f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
        )
    else:
        await query.message.reply_text(
            f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
        )

    # Чистим
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
        try:
            result = run_add_model(url, cat=cat_id, name=final_name)
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
            await update.message.reply_text(
                f"🎉 Готово!\n\n"
                f"Модель: {final_name}\n"
                f"Категория: {cat_name}\n"
                f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
            )
        else:
            await update.message.reply_text(
                f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
            )

        # Чистим
        for key in ["pending_url", "pending_cat", "pending_cat_name", "original_name", "translated_name"]:
            context.user_data.pop(key, None)
        return True

    return False

    # Запускаем add_model.py
    try:
        result = run_add_model(url, cat=cat_id, name=custom_name)
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

    # Парсим название из stdout
    name = custom_name or "модель"
    for line in result["stdout"].splitlines():
        if line.startswith("Название:"):
            name = line.split(":", 1)[1].strip()
            break

    # Коммитим и пушим
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
    app.add_handler(CallbackQueryHandler(name_selected, pattern=r"^name:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

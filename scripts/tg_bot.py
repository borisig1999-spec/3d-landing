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

# ---------- НАСТРОЙКИ ----------
TOKEN = os.environ.get("TG_BOT_TOKEN", "8970161294:AAH7QNp4MUoE586DRTIbPKHVJPJLlqdICu0")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "models.json"
SCRIPT_ADD = PROJECT_ROOT / "scripts" / "add_model.py"

# Категории для inline-кнопок
CATEGORIES = {
    "home": "Дом",
    "storage": "Хранение",
    "kitchen": "Кухня",
    "lighting": "Свет",
    "tools": "Инструменты",
    "wardrobe": "Гардероб",
    "figures": "Фигурки",
    "games": "Игры",
    "auto": "Авто и техника",
    "parts": "Запчасти",
}

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


def run_add_model(url: str, cat: str = None, tags: str = "", featured: bool = False) -> dict:
    """Запускает add_model.py и возвращает результат."""
    cmd = [sys.executable, str(SCRIPT_ADD), url, "--add"]
    if cat:
        cmd.extend(["--cat", cat])
    if tags:
        cmd.extend(["--tags", tags])
    if featured:
        cmd.append("--featured")

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
    return {"success": all("nothing to commit" in o or "Everything up-to-date" in o or "main -> main" in o for o in outputs), "log": "\n".join(outputs)}


# ---------- Обработчики ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    await update.message.reply_text(
        "Привет! Я бот для добавления 3D-моделей на сайт.\n\n"
        "Просто отправь ссылку с MakerWorld, Thingiverse или Printables — "
        "я скачаю фото, обновлю каталог и запушу на сайт.\n\n"
        "Команды:\n"
        "/help — подробная справка\n"
        "/list — последние добавленные модели"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    await update.message.reply_text(
        "Как пользоваться:\n\n"
        "1. Отправь ссылку на модель:\n"
        "   https://makerworld.com/ru/models/2016647\n\n"
        "2. Я спрошу категорию — выбери из списка\n\n"
        "3. Готово! Модель добавлена на сайт\n\n"
        "Формат: можно сразу указать категорию после ссылки:\n"
        "/add https://makerworld.com/... home\n\n"
        "Или просто отправь ссылку — я спрошу категорию."
    )


async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать последние модели."""
    models = get_recent_models(5)
    if not models:
        await update.message.reply_text("Каталог пуст.")
        return

    text = "Последние добавленные модели:\n\n"
    for i, m in enumerate(models, 1):
        cat = CATEGORIES.get(m.get("category", ""), m.get("category", "?"))
        text += f"{i}. {m['name']}\n   Категория: {cat}\n   {m.get('url', '')}\n\n"

    await update.message.reply_text(text)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на модель."""
    text = update.message.text.strip()

    if not is_model_url(text):
        await update.message.reply_text(
            "Не похоже на ссылку модели. Отправь URL с MakerWorld, Thingiverse или Printables."
        )
        return

    # Сохраняем URL в контексте пользователя
    context.user_data["pending_url"] = text

    # Показываем кнопки категорий
    keyboard = []
    row = []
    for cat_id, cat_name in CATEGORIES.items():
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
    """Обработка выбора категории."""
    query = update.callback_query
    await query.answer()

    cat_id = query.data.split(":")[1]
    url = context.user_data.get("pending_url")

    if not url:
        await query.edit_message_text("Ошибка: ссылка потерялась. Отправь заново.")
        return

    cat_name = CATEGORIES.get(cat_id, cat_id)
    await query.edit_message_text(f"Добавляю модель в категорию «{cat_name}»...")

    # Запускаем add_model.py
    try:
        result = run_add_model(url, cat=cat_id)
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

    # Парсим название из stdout
    name = "модель"
    for line in result["stdout"].splitlines():
        if line.startswith("Название:"):
            name = line.split(":", 1)[1].strip()
            break

    # Коммитим и пушим
    await query.message.reply_text(f"✅ «{name}» добавлена! Пушу на сайт...")
    git_result = git_commit_and_push(f"Добавлена модель: {name} (из Telegram)")

    if git_result["success"]:
        await query.message.reply_text(
            f"🎉 Готово!\n\n"
            f"Модель: {name}\n"
            f"Категория: {cat_name}\n"
            f"Сайт: https://borisig1999-spec.github.io/3d-landing/"
        )
    else:
        await query.message.reply_text(
            f"Модель добавлена, но пуш не удался:\n{git_result['log'][:500]}"
        )

    # Чистим
    context.user_data.pop("pending_url", None)


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
    app.add_handler(CallbackQueryHandler(category_selected, pattern=r"^cat:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

# Скрипты каталога

## add_model.py — добавить модель по URL

Скачивает фото с сайта-источника (обходит Cloudflare через headless Chromium) и дописывает запись в `data/models.json`.

```bash
# Полный flow: скачать фото + дописать в каталог
python scripts/add_model.py "https://makerworld.com/ru/models/189019-..." \
  --name "Дарт Вейдер — ваза-горшок (Cat Wars)" \
  --cat figures --sub star-wars \
  --material PLA \
  --tags "звёздные войны, ваза, декор" \
  --featured \
  --add

# Только посмотреть что найдётся (ничего не сохраняет)
python scripts/add_model.py "<url>" --dry-run
```

**Извлекает автоматически:** название (og:title), фото (og:image), URL.

**Нужно указать вручную:** категорию, подкатегорию (если есть), материал, теги, featured.

**Название рекомендуется передавать через `--name` переведённым** — og:title на английском не годится для русскоязычного каталога. Конвенция:
- Описательная часть переводится на русский
- Бренды/технические термины в скобках: `(Cat Wars)`, `(low poly)`
- Пример: `Дарт Вейдер — ваза-горшок (Cat Wars, low poly)`

## add_manual.py — добавить модель, когда фото уже в images/

```bash
python scripts/add_manual.py \
  --image "my_model.webp" \
  --name "Моя модель" \
  --cat home \
  --material PLA \
  --tags "круто, полезно" \
  --featured
```

Скрипт проверит:
- Что файл реально есть в `images/`
- Что категория существует в `models.json`
- Что подкатегория (если указана) существует для этой категории
- Что фото ещё не используется (защита от дублей)
- Что id не занят (если занят — добавит `-2`, `-3`...)

## Формат фото

Скрипты автоматически определяют реальный формат картинки по magic bytes.
**MakerWorld отдаёт WebP** — скрипт сохраняет как `.webp`. Это нормально:
- В 2-3 раза меньше JPEG при том же качестве
- Все современные браузеры показывают нативно
- `<img src="...webp">` работает в HTML без дополнительных атрибутов

Старые фото в `images/` остались в `.jpg`/`.png` (загружены вручную). Это тоже работает.

## Категории (шпаргалка)

См. `_cats_reference.txt` в корне проекта. Кратко:

| id | Название | Подкатегории |
|---|---|---|
| home | Дом | — |
| storage | Хранение | ikea-skadis, gridfinity, custom |
| kitchen | Кухня | — |
| lighting | Свет | — |
| tools | Инструменты | — |
| wardrobe | Гардероб | — |
| figures | Фигурки | star-wars, lotr, marvel, anime, games, other |
| games | Игры | — |
| auto | Авто и техника | car, motorcycle, boat, bicycle |
| parts | Запчасти | — |

## Локальный сервер для просмотра

`fetch` не работает с `file://` — нужнен http-сервер:

```bash
cd C:\Users\Борис\3d-landing
python -m http.server 8765
```

Открыть: http://localhost:8765/

## Зависимости

- Python 3.11+
- `playwright` (`pip install playwright`)
- `playwright install chromium` (≈1.3 ГБ)
- `add_manual.py` не требует ничего сверх стандартной библиотеки

## ⚠️ Не открывай и не сохраняй `data/models.json` через PowerShell

`Get-Content` в PowerShell 5.1 читает файлы в системной кодировке (CP-1251 на русской Windows), что **ломает кириллицу при round-trip**. Также `Out-File -Encoding utf8` добавляет BOM, который ломает JSON в браузерах.

**Используй только Python для редактирования JSON:**

```python
import json
data = json.load(open('data/models.json', encoding='utf-8'))  # читать
# ... правки ...
json.dump(data, open('data/models.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)  # писать БЕЗ BOM
```

Или редактируй файл в VS Code / Notepad++ — они сохраняют корректно. Скрипты `add_model.py` и `add_manual.py` уже используют правильный подход.

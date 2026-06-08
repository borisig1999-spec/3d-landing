"""
add_model.py — добавляет 3D-модель в каталог.

Использование:
  python add_model.py <url> [--cat home] [--sub star-wars] [--material PLA] [--featured]
  python add_model.py <url> --add           # сразу дописать в data/models.json
  python add_model.py <url> --dry-run       # только показать, ничего не сохранять

Что делает:
  1. Открывает URL в headless Chromium (проходит Cloudflare как реальный браузер).
  2. Слушает XHR — пытается найти JSON-ответ внутреннего API сайта.
  3. Берёт og:title и og:image из meta-тегов (fallback).
  4. Скачивает фото в images/ — реальный формат определяется по magic bytes
     (MakerWorld отдаёт WebP, скрипт сохраняет с .webp — это в 2-3 раза легче JPEG
     и все современные браузеры его показывают).
  5. Печатает JSON-сниппет, готовый к вставке в data/models.json.
  6. С опцией --add дописать в models.json автоматически.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


# ---------- Проверка дублей по URL ----------
def extract_model_id(url):
    """Извлекает числовой ID модели из URL (MakerWorld / Thingiverse / Printables).
    Примеры:
      .../models/2016647-kraftique-...  → '2016647'
      .../thing:12345                    → '12345'
      .../model/12345-...                → '12345'
    """
    if not url:
        return None
    m = re.search(r'(?:/models?/|thing:)(\d+)', url)
    return m.group(1) if m else None


def find_duplicate_url(new_url, catalog):
    """Ищет в каталоге модель с тем же URL или тем же числовым ID.
    Возвращает dict существующей модели или None."""
    if not new_url:
        return None
    new_id = extract_model_id(new_url)
    for m in catalog.get('models', []):
        existing = m.get('url')
        if not existing:
            continue
        if existing == new_url:
            return m
        if new_id:
            existing_id = extract_model_id(existing)
            if existing_id and existing_id == new_id:
                return m
    return None


def load_catalog(data_file):
    """Читает каталог; возвращает {categories, subcategories, models} или None."""
    if not data_file.exists():
        return {'categories': [], 'subcategories': {}, 'models': []}
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f'WARN: не удалось прочитать {data_file}: {e}', file=sys.stderr)
        return None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ОШИБКА: playwright не установлен. Запусти: python -m pip install playwright", file=sys.stderr)
    sys.exit(1)


# ---------- Транслитерация кириллицы → латиница ----------
def translit(text: str) -> str:
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    out = []
    for ch in text.lower():
        if ch in table:
            out.append(table[ch])
        else:
            out.append(ch)
    return ''.join(out)


def slugify(text: str, max_len: int = 50) -> str:
    s = translit(text)
    s = unicodedata.normalize('NFKD', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    if len(s) > max_len:
        s = s[:max_len].rsplit('-', 1)[0]
    return s or 'model'


# Суффиксы, которые сайты любят добавлять к og:title
TITLE_SUFFIXES = [
    r'\s*[-—|]\s*(Free\s+)?3[Dd]?\s*Print\s*Model.*$',
    r'\s*[-—|]\s*MakerWorld.*$',
    r'\s*[-—|]\s*Thingiverse.*$',
    r'\s*[-—|]\s*Printables.*$',
    r'\s*[-—|]\s*Thangs.*$',
    r'\s*[-—|]\s*Download\s+Free\s+3[Dd].*$',
    r'\s*\|\s*3[Dd]?\s*Model.*$',
]


def clean_title(raw: str) -> str:
    if not raw:
        return raw
    s = raw
    for pat in TITLE_SUFFIXES:
        s2 = re.sub(pat, '', s, flags=re.I)
        if s2 != s and len(s2) >= 3:
            s = s2
    return s.strip().rstrip('-—|:.,')


def file_ext_from_url(url: str, content_type: str = '') -> str:
    path = urlparse(url).path.lower()
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'):
        if path.endswith(ext):
            return '.jpg' if ext == '.jpeg' else ext
    if 'png' in content_type:
        return '.png'
    if 'webp' in content_type:
        return '.webp'
    if 'jpeg' in content_type or 'jpg' in content_type:
        return '.jpg'
    return '.jpg'


def detect_ext_from_bytes(data: bytes) -> str:
    """Определяет реальный формат по магическим байтам."""
    if len(data) < 12:
        return '.jpg'
    if data[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return '.png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    return '.jpg'


def safe_get(d, *keys, default=None):
    """Достаёт значение из вложенного dict по цепочке ключей."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d


# ---------- Извлечение данных с разных сайтов ----------
def extract_makerworld(api_json: dict) -> dict:
    """Парсит JSON MakerWorld — структура меняется, поэтому ищем неустойчиво."""
    result = {}

    candidates = [
        api_json.get('data', {}),
        api_json.get('design', {}),
        api_json.get('result', {}),
        api_json,
    ]
    for c in candidates:
        if not isinstance(c, dict):
            continue
        if not result.get('name'):
            result['name'] = c.get('title') or c.get('name') or c.get('design_title')
        if not result.get('weight'):
            w = c.get('weight') or c.get('print_weight') or c.get('model_weight')
            if isinstance(w, (int, float)):
                result['weight'] = round(w, 1)
        if not result.get('printTime'):
            t = (c.get('printing_time') or c.get('print_time') or
                 c.get('printTime') or c.get('printingTime'))
            if isinstance(t, (int, float)):
                if t > 500:
                    t = round(t / 60, 1)
                result['printTime'] = t
        if not result.get('image'):
            img = c.get('cover') or c.get('cover_image') or c.get('cover_image_url') or c.get('image')
            if isinstance(img, str):
                result['image'] = img
            elif isinstance(img, dict):
                result['image'] = img.get('url') or img.get('original')
        if not result.get('id'):
            did = c.get('id') or c.get('design_id') or c.get('designId')
            if isinstance(did, (int, str)):
                result['id'] = str(did)
        if all(result.get(k) for k in ('name', 'image')):
            break
    return result


def extract_thingiverse(api_json: dict) -> dict:
    """Thingiverse — public REST API, структура стабильна."""
    return {
        'name': api_json.get('name'),
        'weight': api_json.get('details', {}).get('mass'),
        'printTime': None,  # у Thingiverse обычно нет
        'image': api_json.get('default_image', {}).get('sizes', [None, None, None, None])[-1] or
                 api_json.get('thumbnail'),
        'id': str(api_json.get('id', '')),
    }


def extract_printables(api_json: dict) -> dict:
    """Printables — структура менялась, ищем по эвристикам."""
    result = {}
    candidates = [
        api_json.get('model', api_json),
        api_json.get('data', api_json),
        api_json,
    ]
    for c in candidates:
        if not isinstance(c, dict):
            continue
        result['name'] = result.get('name') or c.get('name') or c.get('title')
        if isinstance(c.get('weight_g'), (int, float)):
            result['weight'] = round(c['weight_g'], 1)
        if isinstance(c.get('printTime'), (int, float)) or isinstance(c.get('print_time'), (int, float)):
            result['printTime'] = round(c.get('printTime') or c.get('print_time'), 1)
        img = c.get('image') or c.get('cover') or c.get('preview')
        if isinstance(img, str):
            result['image'] = img
        elif isinstance(img, dict):
            result['image'] = img.get('url')
        if result.get('name') and result.get('image'):
            break
    return result


# ---------- Главный парсер ----------
def fetch_page(url: str, project_root: Path) -> dict:
    """Открывает URL, ждёт загрузки, возвращает dict с данными модели."""
    captured_responses = []
    result = {
        'url': url,
        'name': None,
        'image': None,
        'weight': None,
        'printTime': None,
        'api_json': None,
        'site': None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ru-RU',
            viewport={'width': 1280, 'height': 800},
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get('content-type', '')
                if 'json' not in ct:
                    return
                url_l = resp.url
                # Ловим все JSON — потом решим, что из них полезно
                # (иначе пропустим нестандартные API-эндпоинты)
                body = resp.json()
                # Отсекаем заведомо шумные (трекинг, аналитика)
                if any(x in url_l.lower() for x in ['analytics', 'tracking', 'pixel', 'gtag', 'ga.js']):
                    return
                captured_responses.append({'url': url_l, 'json': body})
            except Exception:
                pass

        page.on('response', on_response)

        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            # Дать JS подгрузить данные
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                pass
        except Exception as e:
            print(f'WARN: goto error: {e}', file=sys.stderr)

        # 1. og:title
        try:
            v = page.locator('meta[property="og:title"]').first.get_attribute('content')
            if v:
                result['name'] = clean_title(v.strip())
        except Exception:
            pass

        # 2. og:image
        try:
            v = page.locator('meta[property="og:image"]').first.get_attribute('content')
            if v:
                result['image'] = v.strip()
        except Exception:
            pass

        # 3. og:description
        try:
            v = page.locator('meta[property="og:description"]').first.get_attribute('content')
            if v:
                result['description'] = v.strip()
        except Exception:
            pass

        # 4. h1 fallback (тоже чистим)
        if not result['name']:
            try:
                v = page.locator('h1').first.inner_text(timeout=2000)
                if v:
                    result['name'] = clean_title(v.strip())
            except Exception:
                pass

        # 4.5. Скрейпинг времени печати и веса со страницы (fallback)
        if not result.get('printTime') or not result.get('weight'):
            try:
                body_text = page.inner_text('body', timeout=3000)
                if not result.get('printTime'):
                    times = re.findall(r'(\d+)\s*(?:min|minute|ч|мин|h)', body_text, re.I)
                    if times:
                        minutes = [int(t) for t in times if 1 < int(t) < 10000]
                        if minutes:
                            result['printTime'] = min(minutes)
                if not result.get('weight'):
                    weights = re.findall(r'(\d+\.?\d*)\s*(?:g|gram|грамм|г)\b', body_text, re.I)
                    if weights:
                        grams = [float(w) for w in weights if 0.1 < float(w) < 50000]
                        if grams:
                            result['weight'] = round(min(grams), 1)
            except Exception:
                pass

        result['site'] = 'makerworld' if 'makerworld' in url else (
            'thingiverse' if 'thingiverse' in url else (
            'printables' if 'printables' in url else 'unknown'))

        # 5. Достаём данные из перехваченных API
        for resp in captured_responses:
            u = resp['url']
            data = resp['json']
            try:
                if result['site'] == 'makerworld':
                    extracted = extract_makerworld(data)
                elif result['site'] == 'thingiverse':
                    extracted = extract_thingiverse(data)
                elif result['site'] == 'printables':
                    extracted = extract_printables(data)
                else:
                    continue
                for k, v in extracted.items():
                    if v and not result.get(k):
                        result[k] = v
                if result.get('name') and result.get('image'):
                    result['api_json'] = data
                    break
            except Exception as e:
                print(f'WARN: extract error: {e}', file=sys.stderr)

        # Если не нашли og:image, попробуем первую крупную картинку на странице
        if not result.get('image'):
            try:
                imgs = page.locator('img').all()
                for img_el in imgs:
                    src = img_el.get_attribute('src') or ''
                    if not src or src.startswith('data:'):
                        continue
                    if any(x in src.lower() for x in ['cover', 'preview', 'main', 'hero', 'design']):
                        result['image'] = src
                        break
                if not result.get('image'):
                    for img_el in imgs:
                        src = img_el.get_attribute('src') or ''
                        if not src or src.startswith('data:'):
                            continue
                        if 'makerworld.com' in src and any(x in src.lower() for x in ['.jpg', '.png', '.webp']):
                            result['image'] = src
                            break
            except Exception:
                pass

        # Последний шанс — ищем в JSON ответах cover image
        if not result.get('image'):
            for resp in captured_responses:
                try:
                    data = resp['json']
                    candidates = [data.get('data', {}), data.get('design', {}), data]
                    for c in candidates:
                        if not isinstance(c, dict):
                            continue
                        for key in ['cover', 'cover_image', 'cover_image_url', 'image', 'image_url', 'preview']:
                            img = c.get(key)
                            if isinstance(img, str) and img.startswith('http'):
                                result['image'] = img
                                break
                            elif isinstance(img, dict):
                                url = img.get('url') or img.get('original')
                                if url and isinstance(url, str) and url.startswith('http'):
                                    result['image'] = url
                                    break
                        if result.get('image'):
                            break
                    if result.get('image'):
                        break
                except Exception:
                    pass

        browser.close()

    return result


# ---------- Скачивание картинки ----------
def download_image(url: str, dest: Path) -> bool:
    """Скачивает картинку через простой GET. Возвращает (True, path) при успехе."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://makerworld.com/',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            ct = resp.headers.get('Content-Type', '')
        # Сначала определяем формат по содержимому — иначе .jpg-фейк
        ext = detect_ext_from_bytes(data)
        # Если не смогли — fallback на URL/CT
        if ext == '.jpg' and ct and 'image' in ct:
            ext = file_ext_from_url(url, ct)
        dest = dest.with_suffix(ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, dest
    except Exception as e:
        print(f'WARN: image download failed: {e}', file=sys.stderr)
        return False, None


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(description='Добавить 3D-модель в каталог')
    ap.add_argument('url', help='URL модели на MakerWorld / Thingiverse / Printables')
    ap.add_argument('--name', default=None, help='Переопределить название (перевести/адаптировать)')
    ap.add_argument('--cat', default=None, help='Категория (id из models.json)')
    ap.add_argument('--sub', default=None, help='Подкатегория (id из models.json)')
    ap.add_argument('--material', default='PLA', help='Материал (PLA / PETG / ABS / TPU / PA6)')
    ap.add_argument('--featured', action='store_true', help='Показывать на главной')
    ap.add_argument('--tags', default='', help='Теги через запятую')
    ap.add_argument('--add', action='store_true', help='Сразу дописать в data/models.json')
    ap.add_argument('--dry-run', action='store_true', help='Только показать, ничего не сохранять')
    ap.add_argument('--root', default=None, help='Корень проекта (по умолчанию — родитель scripts/)')
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    images_dir = root / 'images'
    data_file = root / 'data' / 'models.json'

    # Проверка дубля по URL до запуска браузера
    catalog = load_catalog(data_file)
    if catalog is not None:
        dup = find_duplicate_url(args.url, catalog)
        if dup:
            print(f'ОШИБКА: эта модель уже в каталоге.', file=sys.stderr)
            print(f'  ID:       {dup["id"]}', file=sys.stderr)
            print(f'  Название: {dup["name"]}', file=sys.stderr)
            print(f'  URL:      {dup.get("url", "")}', file=sys.stderr)
            print(f'  Категория: {dup["category"]}', file=sys.stderr)
            sys.exit(5)

    print(f'Открываю: {args.url}', file=sys.stderr)
    data = fetch_page(args.url, root)

    if not data.get('name'):
        print('ОШИБКА: не удалось извлечь название', file=sys.stderr)
        sys.exit(2)

    # Если передано --name, перебиваем og:title на пользовательский
    if args.name:
        data['name'] = args.name.strip()
    if not data.get('image'):
        print('ОШИБКА: не удалось найти фото', file=sys.stderr)
        sys.exit(2)

    print(f'Название: {data["name"]}', file=sys.stderr)
    if data.get('weight'):
        print(f'Вес: {data["weight"]} г', file=sys.stderr)
    if data.get('printTime'):
        pt = data['printTime']
        if pt > 60:
            print(f'Время печати: {round(pt/60, 1)} ч', file=sys.stderr)
        else:
            print(f'Время печати: {pt} мин', file=sys.stderr)
    print(f'Фото URL: {data["image"]}', file=sys.stderr)

    # Slug → имя файла
    slug = slugify(data['name'])
    # Уникализация: если файл уже есть, добавим суффикс
    img_path = images_dir / f'{slug}{file_ext_from_url(data["image"])}'
    if img_path.exists() and not args.dry_run:
        i = 2
        while True:
            candidate = images_dir / f'{slug}-{i}{file_ext_from_url(data["image"])}'
            if not candidate.exists():
                img_path = candidate
                break
            i += 1

    if args.dry_run:
        print(f'[DRY-RUN] Не сохраняю фото и не пишу в JSON', file=sys.stderr)
        rel_path = f'images/{img_path.name}'
    else:
        ok, saved = download_image(data['image'], img_path)
        if not ok:
            print('ОШИБКА: не удалось скачать фото', file=sys.stderr)
            sys.exit(3)
        rel_path = f'images/{saved.name}'
        print(f'Сохранено: {saved}', file=sys.stderr)

    # Готовим JSON
    model_id = re.sub(r'[^a-z0-9-]', '', slug) or 'model'
    entry = {
        'id': model_id,
        'name': data['name'],
        'category': args.cat or 'TODO',
        'subcategory': args.sub,
        'material': args.material,
        'weight': data.get('weight'),
        'printTime': data.get('printTime'),
        'image': rel_path,
        'url': args.url,
        'tags': [t.strip() for t in args.tags.split(',') if t.strip()],
        'featured': args.featured,
    }

    if args.add and not args.dry_run:
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
            catalog['models'].append(entry)
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(catalog, f, ensure_ascii=False, indent=2)
            print(f'Добавлено в {data_file}', file=sys.stderr)
        except Exception as e:
            print(f'ОШИБКА записи в models.json: {e}', file=sys.stderr)
            print('JSON-сниппет ниже — добавь вручную', file=sys.stderr)
    else:
        print('--- ВСТАВЬ ЭТО В data/models.json (в массив "models") ---', file=sys.stderr)

    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

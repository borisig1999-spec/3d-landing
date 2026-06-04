"""
add_manual.py — добавляет модель, когда фото уже есть в images/.

Использование:
  python scripts/add_manual.py --image "имя_файла.jpg" --name "Кружка" --cat home
  python scripts/add_manual.py --image "pot.jpg" --name "Горшок" --cat home --sub null --material PLA --tags "растения" --featured --url "https://..."

Что делает:
  1. Проверяет, что фото существует в images/.
  2. Проверяет, что категория есть в models.json (подсказывает id).
  3. Генерирует slug, id.
  4. Дописывает запись в data/models.json.
  5. Печатает JSON, чтобы ты видел что добавилось.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


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
    """Ищет в каталоге модель с тем же URL или тем же числовым ID."""
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


# ---------- Slug + ID ----------
def translit(text: str) -> str:
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    return ''.join(table.get(c, c) for c in text.lower())


def slugify(text: str, max_len: int = 50) -> str:
    s = translit(text)
    s = unicodedata.normalize('NFKD', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    if len(s) > max_len:
        s = s[:max_len].rsplit('-', 1)[0]
    return s or 'model'


def model_id(slug: str) -> str:
    return re.sub(r'[^a-z0-9-]', '', slug) or 'model'


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(description='Добавить модель вручную (фото уже в images/)')
    ap.add_argument('--image', required=True, help='Имя файла в images/ (например "pot.jpg")')
    ap.add_argument('--name', required=True, help='Название модели')
    ap.add_argument('--cat', required=True, help='ID категории (см. models.json)')
    ap.add_argument('--sub', default=None, help='ID подкатегории (если есть)')
    ap.add_argument('--material', default='PLA', help='Материал (PLA / PETG / ABS / TPU / PA6)')
    ap.add_argument('--weight', type=float, default=None, help='Вес в граммах (если знаешь)')
    ap.add_argument('--print-time', type=float, default=None, help='Время печати в часах (если знаешь)')
    ap.add_argument('--tags', default='', help='Теги через запятую')
    ap.add_argument('--url', default=None, help='URL на MakerWorld / Thingiverse (если есть)')
    ap.add_argument('--featured', action='store_true', help='Показывать на главной')
    ap.add_argument('--root', default=None, help='Корень проекта')
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    images_dir = root / 'images'
    data_file = root / 'data' / 'models.json'

    # 1. Проверяем фото
    img_path = images_dir / args.image
    if not img_path.exists():
        print(f'ОШИБКА: файл не найден: {img_path}', file=sys.stderr)
        print(f'В папке images/ есть:', file=sys.stderr)
        for f in sorted(images_dir.iterdir()):
            if f.is_file():
                print(f'  - {f.name}', file=sys.stderr)
        sys.exit(1)

    # 2. Загружаем каталог, проверяем категорию
    with open(data_file, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # 2a. Проверка дубля по URL (если --url указан)
    if args.url:
        dup = find_duplicate_url(args.url, catalog)
        if dup:
            print(f'ОШИБКА: эта модель уже в каталоге.', file=sys.stderr)
            print(f'  ID:       {dup["id"]}', file=sys.stderr)
            print(f'  Название: {dup["name"]}', file=sys.stderr)
            print(f'  URL:      {dup.get("url", "")}', file=sys.stderr)
            sys.exit(5)

    valid_cats = [c['id'] for c in catalog['categories']]
    if args.cat not in valid_cats:
        print(f'ОШИБКА: категория "{args.cat}" не найдена.', file=sys.stderr)
        print(f'Доступные: {", ".join(valid_cats)}', file=sys.stderr)
        sys.exit(2)

    # 3. Проверяем подкатегорию, если указана
    if args.sub and args.sub != 'null':
        valid_subs = [s['id'] for s in catalog.get('subcategories', {}).get(args.cat, [])]
        if args.sub not in valid_subs:
            print(f'ОШИБКА: подкатегория "{args.sub}" не найдена для "{args.cat}".', file=sys.stderr)
            print(f'Доступные: {", ".join(valid_subs) or "(нет подкатегорий)"}', file=sys.stderr)
            sys.exit(3)

    # 4. Проверяем дубль по image
    for m in catalog['models']:
        if m.get('image') == f'images/{args.image}':
            print(f'ОШИБКА: фото уже используется в модели "{m["name"]}" (id: {m["id"]})', file=sys.stderr)
            sys.exit(4)

    # 5. Генерируем id (с защитой от дублей)
    base_slug = slugify(args.name)
    new_id = model_id(base_slug)
    existing_ids = {m['id'] for m in catalog['models']}
    if new_id in existing_ids:
        i = 2
        while f'{new_id}-{i}' in existing_ids:
            i += 1
        new_id = f'{new_id}-{i}'
        print(f'INFO: id занят, использую "{new_id}"', file=sys.stderr)

    # 6. Собираем запись
    entry = {
        'id': new_id,
        'name': args.name,
        'category': args.cat,
        'subcategory': args.sub if args.sub and args.sub != 'null' else None,
        'material': args.material,
        'weight': args.weight,
        'printTime': args.print_time,
        'image': f'images/{args.image}',
        'url': args.url,
        'tags': [t.strip() for t in args.tags.split(',') if t.strip()],
        'featured': args.featured,
    }

    # 7. Дописываем
    catalog['models'].append(entry)
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print('Добавлено:', file=sys.stderr)
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

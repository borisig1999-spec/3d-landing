import json

with open('data/models.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for m in data['models']:
    pt = m.get('printTime')
    if pt is not None and pt < 24 and pt != int(pt):
        # Decimal values < 24 are hours from old API, convert to minutes
        m['printTime'] = round(pt * 60, 1)
        print(f"  {m['id']}: {pt}h -> {m['printTime']}min")

with open('data/models.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Done!")

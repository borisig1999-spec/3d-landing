import json

with open('data/models.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for m in data['models']:
    if m['id'] == 'kompaktnaya-podstavka-dlya-smartfona':
        m['weight'] = 38
        m['printTime'] = 38
        print('Updated:', m['name'], '-> weight=38g, printTime=38min')
        break

with open('data/models.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Saved')

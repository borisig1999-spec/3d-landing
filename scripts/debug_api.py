import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

captured = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    def on_resp(resp):
        try:
            ct = resp.headers.get('content-type','')
            if 'json' in ct:
                u = resp.url
                d = resp.json()
                s = json.dumps(d, ensure_ascii=False)
                if len(s) > 100:
                    captured.append({'url': u, 'size': len(s), 'data': d})
        except: pass
    page.on('response', on_resp)
    page.goto('https://makerworld.com/ru/models/1685835-lightest-gridfinity-base-ever-customizable', wait_until='domcontentloaded', timeout=30000)
    try: page.wait_for_load_state('networkidle', timeout=15000)
    except: pass
    browser.close()

for c in captured:
    sz = c['size']
    u = c['url'][:120]
    print(f'{sz:>8} {u}')
    d = c['data']
    if isinstance(d, dict):
        for k in list(d.keys())[:3]:
            v = d[k]
            if isinstance(v, dict):
                print(f'          {k}: {list(v.keys())[:8]}')

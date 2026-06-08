import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "models.json"

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

missing = [m for m in data["models"] if not m.get("printTime") and m.get("url") and "makerworld" in m.get("url", "")]
print(f"Missing printTime: {len(missing)} models")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    updated = 0
    for i, m in enumerate(missing):
        url = m.get("url")
        print(f"[{i+1}/{len(missing)}] {m['id']}...", end=" ", flush=True)

        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            # Try to click "All" tab or first printer tab to reveal profiles
            try:
                page.click('text="All"', timeout=3000)
                time.sleep(1)
            except Exception:
                pass

            body = page.inner_text("body", timeout=5000)

            # Find "XX min" near "plate" or "Designer"
            times = re.findall(r"(\d+)\s*min", body, re.I)
            times = [int(t) for t in times if 1 < int(t) < 10000]

            if times:
                m["printTime"] = min(times)
                print(f"printTime={m['printTime']}min")
                updated += 1
            else:
                print("no time")

        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            page.close()

        time.sleep(0.5)

    browser.close()

with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\nDone! Updated {updated}/{len(missing)}")

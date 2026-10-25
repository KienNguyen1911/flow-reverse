import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Monitoring Gemini response...")
                for i in range(20):
                    time.sleep(2)
                    res = p.evaluate("""() => {
                        const stop = !!document.querySelector('button[aria-label*="Ngừng"], button[aria-label*="Stop"]');
                        const mrs = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                        return {
                            stop,
                            mrsCount: mrs.length,
                            latest: mrs.length > 0 ? mrs[mrs.length - 1] : ''
                        };
                    }""")
                    print(f"[{i*2}s] Stop button visible: {res['stop']}, Response length: {len(res['latest'])}")
                    if not res['stop'] and len(res['latest']) > 100:
                        print("=== FINISHED GENERATING! ===")
                        print(res['latest'])
                        Path("out/two_video_prompts_perfect.txt").write_text(res['latest'], encoding="utf-8")
                        break
                break

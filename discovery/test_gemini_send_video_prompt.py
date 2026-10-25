import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Gemini URL:", p.url)
                
                editor = p.query_selector('div.ql-editor')
                editor.click()
                p.keyboard.type("@try-on-prompter", delay=30)
                p.wait_for_timeout(600)
                p.keyboard.press("Enter")
                p.wait_for_timeout(600)
                p.keyboard.type(" create video prompt", delay=20)
                p.wait_for_timeout(800)

                before_count = p.evaluate("document.querySelectorAll('model-response').length")

                send_btn = p.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
                if send_btn and not send_btn.is_disabled():
                    send_btn.click()
                else:
                    p.keyboard.press("Enter")

                print("Sent prompt! Waiting for streaming...")
                t0 = time.time()
                while time.time() - t0 < 60:
                    time.sleep(3)
                    res = p.evaluate("""(before) => {
                        const mrs = document.querySelectorAll('model-response');
                        const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
                        if (mrs.length <= before) return { ready: false, isBusy };
                        const last = mrs[mrs.length - 1];
                        const text = (last.innerText || '').trim();
                        return { ready: !isBusy && text.length > 50, text: text, isBusy: isBusy };
                    }""", before_count)
                    print(f"[{time.time()-t0:.1f}s] Ready: {res['ready']}, Busy: {res['isBusy']}, Len: {len(res.get('text', ''))}")
                    if res.get('ready'):
                        print("=== GEMINI VIDEO PROMPTS GENERATED ===")
                        print(res['text'])
                        Path("out/two_video_prompts.txt").write_text(res['text'], encoding="utf-8")
                        break
                break

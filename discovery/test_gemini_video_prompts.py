from pathlib import Path
import time
from playwright.sync_api import sync_playwright

first_frame = Path("out/first_frame_generated.png").resolve()

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    gemini_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                gemini_page = p
                break

    print("Gemini URL:", gemini_page.url)

    # 1. Upload first frame image
    file_inputs = gemini_page.query_selector_all("input[type=file]")
    if not file_inputs:
        add_btn = gemini_page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm']")
        if add_btn:
            add_btn.click()
            gemini_page.wait_for_timeout(1000)
            file_inputs = gemini_page.query_selector_all("input[type=file]")

    inp = file_inputs[0]
    inp.set_input_files([str(first_frame)])
    print("Uploaded first_frame.png! Waiting 4s...")
    gemini_page.wait_for_timeout(4000)

    # 2. Focus editor and type @try-on-prompt + Enter + create video prompt
    editor = gemini_page.query_selector('div.ql-editor')
    editor.click()
    gemini_page.keyboard.press("Control+A")
    gemini_page.keyboard.press("Backspace")
    gemini_page.wait_for_timeout(300)

    gemini_page.keyboard.type("@try-on-prompt", delay=30)
    gemini_page.wait_for_timeout(500)
    gemini_page.keyboard.press("Enter")
    gemini_page.wait_for_timeout(500)
    gemini_page.keyboard.type(" create video prompt", delay=20)
    gemini_page.wait_for_timeout(500)

    before_count = gemini_page.evaluate("document.querySelectorAll('model-response').length")

    send_btn = gemini_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        send_btn.click()
    else:
        gemini_page.keyboard.press("Enter")

    print("Sent video prompt request! Monitoring streaming...")
    t0 = time.time()
    while time.time() - t0 < 60:
        time.sleep(3)
        res = gemini_page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
            if (mrs.length <= before) return { ready: false, isBusy };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            return { ready: !isBusy && clean.length > 50, text: text, cleanLen: clean.length, isBusy: isBusy };
        }""", before_count)
        print(f"[{time.time()-t0:.1f}s] Ready: {res['ready']}, Busy: {res['isBusy']}, CleanLen: {res.get('cleanLen', 0)}")
        if res.get('ready'):
            print("=== GEMINI 2 VIDEO PROMPTS ===")
            print(res['text'])
            Path("out/video_prompts_raw.txt").write_text(res['text'], encoding="utf-8")
            break

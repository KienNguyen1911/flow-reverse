import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    gemini_page = None
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            gemini_page = p
            break

    # Focus editor
    editor = gemini_page.query_selector("div.ql-editor, rich-textarea")
    editor.click()
    gemini_page.keyboard.press("Control+A")
    gemini_page.keyboard.press("Backspace")
    gemini_page.wait_for_timeout(300)

    # Type @try-on
    print("Typing '@try-on'...")
    gemini_page.keyboard.type("@try-on", delay=40)
    gemini_page.wait_for_timeout(1000)

    # Click try-on-prompter
    gemini_page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('*')).filter(e => 
            e.childNodes.length === 1 && 
            e.childNodes[0].nodeType === Node.TEXT_NODE && 
            e.innerText.trim() === 'try-on-prompter'
        );
        if (els.length > 0) els[0].click();
    }""")
    gemini_page.wait_for_timeout(600)

    # Type exact command
    print("Typing ' create video prompt'...")
    gemini_page.keyboard.type(" create video prompt", delay=20)
    gemini_page.wait_for_timeout(800)

    gemini_page.screenshot(path="out/gemini_vp_exact_cmd.png")

    before_count = gemini_page.evaluate("document.querySelectorAll('model-response').length")
    print("Before count:", before_count)

    # Send
    send_btn = gemini_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        send_btn.click()
    else:
        gemini_page.keyboard.press("Enter")

    print("Sent! Waiting for streaming response...")
    t0 = time.time()
    last_text = ""
    stable_count = 0
    full_text = ""

    while time.time() - t0 < 90:
        time.sleep(2)
        res = gemini_page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            if (mrs.length <= before) return { ready: false, isBusy: true, text: '' };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], mat-progress-spinner, pending-response');
            return { ready: !isBusy && clean.length > 50, isBusy, text };
        }""", before_count)

        cur_text = res.get("text", "")
        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, Length: {len(cur_text)}")

        if res.get("ready"):
            if len(cur_text) == len(last_text) and not res["isBusy"]:
                stable_count += 1
                if stable_count >= 2:
                    print("Video prompts generated!")
                    full_text = cur_text
                    break
            else:
                stable_count = 0
            last_text = cur_text

    if not full_text:
        full_text = last_text

    Path("out/gemini_video_prompts_exact.txt").write_text(full_text, encoding="utf-8")
    print("=== RAW RESPONSE ===")
    print(full_text[:500])

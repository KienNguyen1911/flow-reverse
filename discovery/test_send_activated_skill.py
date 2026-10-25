import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    target_page = None
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            target_page = p
            break

    # We already have <p><strong>@try-on-prompter</strong> </p> in editor!
    # Now type the command:
    print("Typing prompt...")
    target_page.keyboard.type("tạo prompt ảnh người mẫu mặc thử trang phục trên", delay=20)
    target_page.wait_for_timeout(1000)

    target_page.screenshot(path="out/gemini_skill_typed_ready.png")

    before_count = target_page.evaluate("document.querySelectorAll('model-response').length")
    print("Responses before:", before_count)

    # Click Send
    send_btn = target_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        print("Clicking Send button...")
        send_btn.click()
    else:
        print("Pressing Enter to send...")
        target_page.keyboard.press("Enter")

    print("Sent! Waiting for streaming response...")
    t0 = time.time()
    last_text = ""
    stable_count = 0
    full_response = ""

    while time.time() - t0 < 90:
        time.sleep(2)
        res = target_page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
            if (mrs.length <= before) return { ready: false, isBusy, text: '' };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            return { ready: !isBusy && clean.length > 40, text: text, cleanLen: clean.length, isBusy: isBusy };
        }""", before_count)

        cur_text = res.get("text", "")
        print(f"[{time.time()-t0:.1f}s] Ready: {res['ready']}, Busy: {res['isBusy']}, Length: {len(cur_text)}")

        if res.get("ready"):
            if len(cur_text) == len(last_text) and not res["isBusy"]:
                stable_count += 1
                if stable_count >= 2:
                    print("Gemini response is finished!")
                    full_response = cur_text
                    break
            else:
                stable_count = 0
            last_text = cur_text

    target_page.screenshot(path="out/gemini_active_skill_result.png")
    if not full_response:
        full_response = last_text

    Path("out/gemini_active_skill_result.txt").write_text(full_response, encoding="utf-8")
    print("=== GEMINI FULL RESPONSE ===")
    print(full_response)

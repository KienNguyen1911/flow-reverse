from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                ed = p.query_selector('div.ql-editor')
                ed.click()
                p.keyboard.press("Control+A")
                p.keyboard.press("Backspace")
                p.wait_for_timeout(300)

                # Type @try-on-prompt + Enter + prompt text
                p.keyboard.type("@try-on-prompt", delay=30)
                p.wait_for_timeout(600)
                p.keyboard.press("Enter")
                p.wait_for_timeout(500)
                p.keyboard.type(" hãy tạo 2 video prompt 8s nối tiếp nhau từ ảnh này cho Google Flow", delay=15)
                p.wait_for_timeout(500)

                # Send
                p.keyboard.press("Enter")
                print("Sent prompt! Waiting 15s...")
                p.wait_for_timeout(15000)
                text = p.evaluate("""() => {
                    const mrs = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                    return mrs.length > 0 ? mrs[mrs.length - 1] : '';
                }""")
                print("=== RESPONSE ===")
                print(text)
                break

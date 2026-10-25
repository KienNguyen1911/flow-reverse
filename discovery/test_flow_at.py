from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                textarea = p.query_selector('textarea, div[contenteditable="true"]')
                if textarea:
                    textarea.click()
                    p.keyboard.press("Control+A")
                    p.keyboard.press("Backspace")
                    p.keyboard.type("@", delay=100)
                    p.wait_for_timeout(1000)
                    p.screenshot(path='out/flow_at_popup.png')
                    popup = p.evaluate("""() => {
                        const items = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], .ingredient-item, [class*="chip"], [class*="tag"]'))
                            .map(e => e.innerText.trim()).filter(Boolean);
                        return items;
                    }""")
                    print("At popup items:", popup)
                break

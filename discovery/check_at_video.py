from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                pm = p.query_selector('div.ProseMirror')
                pm.click()
                p.keyboard.press("Control+A")
                p.keyboard.press("Backspace")
                p.wait_for_timeout(300)
                p.keyboard.type("@", delay=50)
                p.wait_for_timeout(1000)
                
                # Check popup items
                items = p.evaluate("""() => {
                    const list = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], .ingredient-item, [class*="chip"]'))
                        .map(e => e.innerText.trim()).filter(Boolean);
                    return list;
                }""")
                print("At popup in video mode:", items)
                break

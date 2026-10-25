from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Checking model switcher on Flow...")
                btn = p.query_selector('//button[contains(., "Nano Banana")] | //button[contains(., "Banana")]')
                if btn:
                    print("Found model button:", btn.inner_text())
                    btn.click()
                    p.wait_for_timeout(1000)
                    options = p.evaluate("""() => {
                        const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], mat-menu-item, button, [class*="item"]'))
                            .map(e => e.innerText.trim()).filter(Boolean);
                        return items.slice(0, 25);
                    }""")
                    print("Model switcher options:", options)
                else:
                    print("Model button not found!")
                break

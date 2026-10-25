from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            editor = p.query_selector("div.ql-editor, rich-textarea")
            editor.click()
            p.keyboard.press("Control+A")
            p.keyboard.press("Backspace")
            p.wait_for_timeout(300)
            
            p.keyboard.type("@", delay=100)
            p.wait_for_timeout(1000)
            p.screenshot(path="out/gemini_at_menu.png")
            
            # Check all items in overlay or listbox
            items = p.evaluate("""() => {
                const els = document.querySelectorAll('.cdk-overlay-pane, [role="listbox"], [role="menu"], [role="option"], gem-skill-picker-item, .mat-mdc-menu-item');
                return Array.from(els).map(e => e.innerText.trim()).filter(Boolean);
            }""")
            print("Gemini @ menu items:")
            for item in items:
                print(repr(item))
            break

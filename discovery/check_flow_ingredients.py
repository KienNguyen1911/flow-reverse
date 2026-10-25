from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            pm = p.query_selector('div.ProseMirror')
            pm.click()
            p.keyboard.press("Control+A")
            p.keyboard.press("Backspace")
            p.wait_for_timeout(300)
            p.keyboard.type("@", delay=50)
            p.wait_for_timeout(1000)
            p.screenshot(path='out/flow_at_menu.png')
            
            # Find all options inside the autocomplete popup
            popup_items = p.evaluate("""() => {
                const results = [];
                // Check all overlay containers
                const nodes = document.querySelectorAll('.cdk-overlay-pane, [role="listbox"], [role="menu"]');
                nodes.forEach(n => {
                    n.querySelectorAll('*').forEach(child => {
                        const t = (child.innerText || '').trim();
                        if (t && t.length < 50 && !results.includes(t)) {
                            results.push(t);
                        }
                    });
                });
                return results;
            }""")
            print("Ingredients in popup:", popup_items[:20])
            break

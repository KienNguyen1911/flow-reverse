from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                pm = p.query_selector('div.ProseMirror')
                pm.click()
                p.keyboard.type("A cinematic shot of a young woman walking in a bakery store, natural light.", delay=10)
                p.wait_for_timeout(1000)
                
                # Check button disabled status
                btn_state = p.evaluate("""() => {
                    const btn = document.querySelector('button.generate-icon-button');
                    return {
                        disabled: btn ? (btn.disabled || btn.classList.contains('mat-mdc-button-disabled')) : null,
                        ariaDisabled: btn ? btn.getAttribute('aria-disabled') : null
                    };
                }""")
                print("After typing prompt, generate button state:", btn_state)
                break

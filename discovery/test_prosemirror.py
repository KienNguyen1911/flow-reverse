from playwright.sync_api import sync_playwright

prompt_text = "A photorealistic lifestyle portrait of @main-model.jpg wearing the outfit from @1.jpg in a bakery store, high details, natural lighting."

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Found flow!")
                pm = p.query_selector('div.ProseMirror[contenteditable="true"]')
                if pm:
                    print("Found ProseMirror composer!")
                    pm.click()
                    p.keyboard.press("Control+A")
                    p.keyboard.press("Backspace")
                    p.wait_for_timeout(300)

                    # Type prompt into ProseMirror
                    pm.fill(prompt_text)
                    p.wait_for_timeout(500)
                    p.screenshot(path='out/flow_pm_filled.png')
                    print("Filled ProseMirror! Content:", pm.inner_text())

                    # Check generate button state
                    btn_state = p.evaluate("""() => {
                        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Bắt đầu tạo') || (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo'));
                        return {
                            found: !!btn,
                            text: btn ? btn.innerText.trim() : null,
                            disabled: btn ? (btn.disabled || btn.getAttribute('aria-disabled') === 'true') : null
                        };
                    }""")
                    print("Generate button:", btn_state)
                break

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_current.png')
                print("Flow Title:", p.title())
                # Check composer elements
                info = p.evaluate("""() => {
                    const textarea = document.querySelector('textarea, div[contenteditable="true"], [role="textbox"]');
                    const allButtons = Array.from(document.querySelectorAll('button, [role="button"]'))
                        .map(b => (b.getAttribute('aria-label') || b.innerText).trim())
                        .filter(Boolean);
                    return {
                        hasTextarea: !!textarea,
                        textareaPlaceholder: textarea ? (textarea.placeholder || textarea.getAttribute('aria-label') || '') : '',
                        buttons: allButtons.slice(0, 30)
                    };
                }""")
                print("Flow composer info:", info)
                break

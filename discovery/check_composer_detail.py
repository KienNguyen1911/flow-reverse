from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_composer_detail.png')
                res = p.evaluate("""() => {
                    const composer = document.querySelector('[class*="composer"], [class*="prompt-box"], form') || document.body;
                    const btns = Array.from(composer.querySelectorAll('button')).map(b => ({
                        aria: b.getAttribute('aria-label') || '',
                        text: b.innerText.trim(),
                        className: b.className
                    }));
                    return btns;
                }""")
                print("Composer buttons:", res)
                break

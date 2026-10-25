from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                btns = p.evaluate("""() => {
                    const container = document.querySelector('input-area-v2, .input-area-container, input-container');
                    const btns = container ? Array.from(container.querySelectorAll('button')) : Array.from(document.querySelectorAll('button'));
                    return btns.map(b => ({
                        aria: b.getAttribute('aria-label') || '',
                        text: b.innerText.trim(),
                        tag: b.tagName,
                        jslog: b.getAttribute('jslog') || ''
                    }));
                }""")
                print("All buttons in input area:", btns)
                break

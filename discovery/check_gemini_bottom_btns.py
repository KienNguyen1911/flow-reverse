from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Gemini URL:", p.url)
                btns = p.evaluate("""() => {
                    const allBtns = Array.from(document.querySelectorAll('button')).map(b => ({
                        aria: b.getAttribute('aria-label') || '',
                        text: b.innerText.trim(),
                        className: b.className
                    })).filter(b => b.aria || b.text);
                    return allBtns.slice(-15);
                }""")
                print("Buttons near bottom:", btns)
                break

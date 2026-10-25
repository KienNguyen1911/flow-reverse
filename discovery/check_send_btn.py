from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                btn = p.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const sendBtns = btns.map(b => ({
                        aria: b.getAttribute('aria-label') || '',
                        text: b.innerText.trim(),
                        disabled: b.disabled || b.getAttribute('aria-disabled') === 'true',
                        className: b.className
                    })).filter(b => b.aria.toLowerCase().includes('gửi') || b.aria.toLowerCase().includes('send') || b.text.toLowerCase().includes('gửi'));
                    return sendBtns;
                }""")
                print("Send buttons in Gemini:", btn)
                break

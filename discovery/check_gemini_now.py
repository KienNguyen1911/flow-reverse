from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                p.screenshot(path='out/gemini_now_state.png')
                res = p.evaluate("""() => {
                    const text = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                    const stop = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"]');
                    return { stop, textCount: text.length, text: text.slice(-1) };
                }""")
                print("Gemini result:", res)
                break

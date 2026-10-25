from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                res = p.evaluate("""() => {
                    const mrs = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                    const stop = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"]');
                    return { stop, count: mrs.length, latest: mrs.length > 0 ? mrs[mrs.length - 1].slice(0, 150) : '' };
                }""")
                print("Gemini live status:", res)
                break

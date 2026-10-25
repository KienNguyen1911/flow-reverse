from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                res = p.evaluate("""() => {
                    const errorMsg = document.querySelector('[role="alert"], .error-message, [class*="error"]')?.innerText;
                    const toast = document.querySelector('mat-snack-bar-container')?.innerText;
                    const stop = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"]');
                    const retryBtn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').toLowerCase().includes('thử lại') || (b.getAttribute('aria-label') || '').toLowerCase().includes('retry'));
                    return {
                        errorMsg,
                        toast,
                        stop,
                        hasRetry: !!retryBtn,
                        allButtons: Array.from(document.querySelectorAll('button')).map(b => (b.getAttribute('aria-label') || b.innerText).trim()).filter(Boolean).slice(-10)
                    };
                }""")
                print("Gemini response debug:", res)
                break

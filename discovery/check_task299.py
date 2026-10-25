from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                p.screenshot(path='out/gemini_task299.png')
                res = p.evaluate("""() => {
                    const editor = document.querySelector('div.ql-editor')?.innerText || '';
                    const lastResp = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText.slice(0, 150));
                    const stop = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"]');
                    return { editor, stop, lastResp };
                }""")
                print(res)
                break

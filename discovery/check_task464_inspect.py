from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                p.screenshot(path='out/gemini_task464_inspect.png')
                res = p.evaluate("""() => {
                    const uq = Array.from(document.querySelectorAll('user-query')).map(u => u.innerText);
                    const mr = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                    const ed = document.querySelector('div.ql-editor')?.innerText;
                    return { ed, uq, mr };
                }""")
                print("Gemini DOM:", res)
                break

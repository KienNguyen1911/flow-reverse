from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                p.screenshot(path='out/gemini_task369_state.png')
                info = p.evaluate("""() => {
                    return {
                        url: location.href,
                        editorHtml: document.querySelector('div.ql-editor')?.innerHTML,
                        editorText: document.querySelector('div.ql-editor')?.innerText,
                        userQueries: Array.from(document.querySelectorAll('user-query')).map(u => u.innerText),
                        responses: Array.from(document.querySelectorAll('model-response')).map(m => m.innerText)
                    };
                }""")
                print("Gemini state:", info)
                break

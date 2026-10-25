from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                mr_html = p.evaluate("""() => {
                    const mr = document.querySelector('model-response');
                    return mr ? mr.innerHTML : 'No model-response';
                }""")
                print("=== MODEL-RESPONSE INNER HTML ===")
                print(mr_html)
                break

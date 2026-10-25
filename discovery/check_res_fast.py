from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                res = p.evaluate("""() => {
                    const mrs = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                    return { count: mrs.length, latest: mrs.length > 0 ? mrs[mrs.length - 1] : '' };
                }""")
                print("Model responses count:", res['count'])
                if res['count'] > 0:
                    print("=== LATEST RESPONSE ===")
                    print(res['latest'])
                break

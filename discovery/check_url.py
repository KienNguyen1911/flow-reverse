from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Page URL:", p.url)
                body = p.evaluate("() => document.body.innerText")
                print("Body text tail:")
                print(body[-600:])
                break

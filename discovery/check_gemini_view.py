from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                p.screenshot(path='out/gemini_current_view.png')
                print("Gemini URL:", p.url)
                print("Gemini Title:", p.title())
                break

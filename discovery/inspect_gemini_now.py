from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            p.screenshot(path="out/gemini_live_now.png")
            last_text = p.evaluate("""() => {
                const mrs = document.querySelectorAll('model-response');
                return mrs.length > 0 ? mrs[mrs.length - 1].innerText : 'NO MODEL RESPONSE';
            }""")
            print("Current last model response length:", len(last_text))
            print("Preview:", repr(last_text[:200]))
            break

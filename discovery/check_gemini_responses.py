from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            p.screenshot(path='out/gemini_inspect_responses.png')
            res = p.evaluate("""() => {
                const mrs = Array.from(document.querySelectorAll('model-response')).map((m, idx) => ({
                    idx,
                    len: m.innerText.length,
                    preview: m.innerText.slice(0, 100)
                }));
                const busy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], mat-progress-spinner');
                return { mrs, busy };
            }""")
            print("Gemini responses:", res)

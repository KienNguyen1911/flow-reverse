from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            p.screenshot(path='out/gemini_current_debug.png')
            btns = p.evaluate("""() => {
                return Array.from(document.querySelectorAll('button, input, [role="button"]')).map(e => ({
                    tag: e.tagName,
                    type: e.type || '',
                    aria: e.getAttribute('aria-label') || '',
                    text: (e.innerText || '').slice(0, 30),
                    cls: e.className
                })).filter(x => x.aria || x.type === 'file' || x.text);
            }""")
            print("Gemini elements found:", len(btns))
            for b in btns:
                if any(k in (b['aria'] + b['text'] + b['type']).lower() for k in ['tải', 'upload', 'thêm', 'add', 'file', 'menu', 'file']):
                    print(b)
            break

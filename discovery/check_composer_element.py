from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                els = p.evaluate("""() => {
                    const editables = Array.from(document.querySelectorAll('[contenteditable="true"], textarea, input[type="text"]'))
                        .map(e => ({
                            tag: e.tagName,
                            className: e.className,
                            contenteditable: e.getAttribute('contenteditable'),
                            placeholder: e.getAttribute('placeholder') || e.getAttribute('data-placeholder'),
                            visible: e.offsetParent !== null
                        }));
                    return editables;
                }""")
                print("Editable elements in Flow:", els)
                break

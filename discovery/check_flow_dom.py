from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                inputs = p.evaluate("""() => {
                    const allInputs = Array.from(document.querySelectorAll('input')).map(i => ({
                        type: i.type,
                        accept: i.accept,
                        id: i.id,
                        className: i.className
                    }));
                    return allInputs;
                }""")
                print("All inputs on Flow page:", inputs)
                break

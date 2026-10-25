from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                info = p.evaluate("""() => {
                    const pm = document.querySelector('div.ProseMirror');
                    const allButtons = Array.from(document.querySelectorAll('button')).map(b => (b.getAttribute('aria-label') || b.innerText).trim()).filter(Boolean);
                    const allText = document.body.innerText;
                    return {
                        pmText: pm ? pm.innerText : '',
                        buttons: allButtons.slice(-15),
                        textTail: allText.slice(-600)
                    };
                }""")
                print("Composer & Page text:", info)
                break

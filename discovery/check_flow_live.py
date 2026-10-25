from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_live_state.png')
                res = p.evaluate("""() => {
                    const progress = Array.from(document.querySelectorAll('[class*="progress"], [class*="spin"], [class*="load"]')).length;
                    const toast = document.querySelector('[role="alert"], [class*="toast"], [class*="snack"]')?.innerText || '';
                    const textarea = document.querySelector('textarea')?.value || '';
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => (b.getAttribute('aria-label') || b.innerText).trim()).filter(Boolean);
                    return { progress, toast, textareaPreview: textarea.slice(0, 100), buttons: buttons.slice(-10) };
                }""")
                print("Flow state:", res)
                break

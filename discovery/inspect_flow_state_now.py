from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            info = p.evaluate("""() => {
                const title = document.title;
                const url = window.location.href;
                const pm = document.querySelector('div.ProseMirror')?.innerText || '';
                const alerts = Array.from(document.querySelectorAll('[role="alert"], [class*="alert"], .mat-mdc-snack-bar-label')).map(e => e.innerText);
                const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean);
                return { title, url, pm, alerts, buttons: buttons.slice(0, 10) };
            }""")
            print("Flow page info:", info)
            break

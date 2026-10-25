from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Clicking generate button on Flow...")
                clicked = p.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('arrow_forward') || b.innerText.includes('Bắt đầu tạo') || (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo'));
                    if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                print("Clicked:", clicked)
                p.wait_for_timeout(6000)
                p.screenshot(path='out/flow_generating_now.png')
                print("Saved out/flow_generating_now.png!")
                break

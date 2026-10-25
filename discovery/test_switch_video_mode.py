from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Switching to Video mode...")
                clicked = p.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Video') || (b.getAttribute('aria-label')||'').includes('Video'));
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                print("Clicked Video:", clicked)
                p.wait_for_timeout(1500)
                p.screenshot(path='out/flow_video_mode.png')
                
                # Check composer in video mode
                state = p.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean);
                    return buttons.slice(-10);
                }""")
                print("Buttons in video mode:", state)
                break

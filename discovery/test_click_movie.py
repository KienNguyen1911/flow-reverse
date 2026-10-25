from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Clicking 'movie Cảnh'...")
                btn = p.query_selector('//button[contains(., "Cảnh")]')
                if btn:
                    btn.click()
                    p.wait_for_timeout(1000)
                    p.screenshot(path='out/flow_after_movie_click.png')
                    print("Clicked! Saved out/flow_after_movie_click.png")
                    
                    # Check composer state
                    state = p.evaluate("""() => {
                        const pm = document.querySelector('div.ProseMirror')?.innerText;
                        const btns = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean);
                        return { pm, btns: btns.slice(-10) };
                    }""")
                    print("Composer state after movie click:", state)
                break

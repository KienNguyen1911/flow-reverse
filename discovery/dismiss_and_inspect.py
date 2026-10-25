from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            print("Found flow page, checking overlays...")
            overlays = p.evaluate("""() => {
                const els = document.querySelectorAll('.cdk-overlay-pane, [role="dialog"], [role="menu"]');
                return Array.from(els).map(e => e.innerText.slice(0, 100));
            }""")
            print("Overlays found:", overlays)
            p.keyboard.press("Escape")
            p.wait_for_timeout(500)
            p.screenshot(path="out/flow_clean_state.png")
            print("Saved out/flow_clean_state.png")

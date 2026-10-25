from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_current_video_composer.png')
                # Press Escape to close overlay
                p.keyboard.press("Escape")
                p.wait_for_timeout(500)
                p.screenshot(path='out/flow_composer_clean.png')
                print("Closed overlay, saved out/flow_composer_clean.png")
                break

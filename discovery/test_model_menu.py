from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                # Find button inside composer that contains Nano Banana
                btn = p.query_selector('//button[contains(., "Nano Banana")]')
                if btn:
                    btn.click()
                    p.wait_for_timeout(1000)
                    p.screenshot(path='out/flow_model_menu.png')
                    menu = p.evaluate("""() => {
                        const overlays = Array.from(document.querySelectorAll('.cdk-overlay-pane, [role="menu"], mat-dialog-container'));
                        const lastOverlay = overlays.length > 0 ? overlays[overlays.length - 1] : null;
                        const btns = lastOverlay ? Array.from(lastOverlay.querySelectorAll('button, [role="menuitem"], div[role="option"]')).map(b => b.innerText.trim()).filter(Boolean) : [];
                        return { overlayCount: overlays.length, buttons: btns };
                    }""")
                    print("Model menu items:", menu)
                break

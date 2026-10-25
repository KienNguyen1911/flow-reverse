from playwright.sync_api import sync_playwright

prompt_v1 = "A young woman in a mint-blue cardigan and cream dress standing near a bakery cart, she gently turns her head and smiles naturally, smooth slow handheld camera pan, soft ambient light, natural fabric movement, 8 seconds."

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Testing clean video prompt on Flow...")
                
                # Close any toast or error dialog
                p.evaluate("""() => {
                    const undoBtn = document.querySelector('button[aria-label*="undo"], button[aria-label*="hoàn tác"]');
                    if (undoBtn) undoBtn.click();
                }""")
                p.wait_for_timeout(500)

                # Focus composer
                pm = p.query_selector('div.ProseMirror[contenteditable="true"]')
                pm.click()
                p.keyboard.press("Control+A")
                p.keyboard.press("Backspace")
                p.wait_for_timeout(300)

                # Type prompt
                p.keyboard.type(prompt_v1, delay=10)
                p.wait_for_timeout(800)

                # Click generate arrow button
                clicked = p.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => 
                        b.innerText.includes('arrow_forward') || 
                        b.innerText.includes('Bắt đầu tạo') || 
                        (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo')
                    );
                    if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                print("Clicked generate:", clicked)
                p.wait_for_timeout(5000)
                p.screenshot(path='out/flow_clean_video_test.png')
                
                # Check status
                status = p.evaluate("""() => {
                    const alert = document.querySelector('[role="alert"], [class*="alert"]')?.innerText || '';
                    const hasProgress = document.querySelectorAll('mat-progress-spinner, mat-progress-bar, [class*="generating"]').length > 0;
                    const text = document.body.innerText.slice(-300);
                    return { alert, hasProgress, text };
                }""")
                print("Flow render status:", status)
                break

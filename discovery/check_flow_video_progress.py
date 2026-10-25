from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            p.screenshot(path='out/flow_video1_live_progress.png')
            status = p.evaluate("""() => {
                const spinners = document.querySelectorAll('mat-progress-spinner, mat-progress-bar, [class*="generating"], [class*="progress"]');
                const videos = Array.from(document.querySelectorAll('video')).map(v => v.src);
                const toast = document.querySelector('[role="alert"], [class*="alert"], .mat-mdc-snack-bar-label')?.innerText || '';
                return { spinners: spinners.length, videos: videos.length, toast };
            }""")
            print("Flow Video 1 live status:", status)

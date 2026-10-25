from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_after_stage4_timeout.png')
                res = p.evaluate("""() => {
                    const videos = Array.from(document.querySelectorAll('video')).map(v => ({
                        src: v.src,
                        currentSrc: v.currentSrc,
                        duration: v.duration
                    }));
                    const entries = performance.getEntriesByType('resource')
                        .map(e => e.name)
                        .filter(u => u.includes('.mp4') || u.includes('/video/'));
                    const toast = document.querySelector('[role="alert"], [class*="snack"], [class*="toast"]')?.innerText;
                    const cards = Array.from(document.querySelectorAll('[class*="card"], [class*="asset"]'))
                        .map(c => c.innerText.trim()).filter(Boolean);
                    return {
                        videos,
                        mp4Entries: entries.slice(-10),
                        toast,
                        cards: cards.slice(0, 15)
                    };
                }""")
                print("Flow state:", res)
                break

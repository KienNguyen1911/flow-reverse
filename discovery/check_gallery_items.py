from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            cards = p.evaluate("""() => {
                const items = [];
                document.querySelectorAll('[class*="asset"], [class*="media"], [class*="item"], .mat-mdc-card').forEach(el => {
                    const img = el.querySelector('img');
                    const video = el.querySelector('video');
                    const txt = el.innerText.trim();
                    if ((img || video) && txt) {
                        items.push({
                            tag: video ? 'VIDEO' : 'IMG',
                            src: (video ? video.src : (img ? img.src : '')).slice(0, 80),
                            txt: txt.slice(0, 80)
                        });
                    }
                });
                return items;
            }""")
            print("Found gallery items:", len(cards))
            for c in cards[:10]:
                print(c)
            break

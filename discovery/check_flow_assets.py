from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                assets = p.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('[class*="asset"], [class*="card"], [class*="item"]'))
                        .map(c => c.innerText.trim()).filter(Boolean);
                    const images = Array.from(document.querySelectorAll('img'))
                        .map(img => img.alt || img.src || '').filter(Boolean);
                    return { cards: cards.slice(0, 15), images: images.slice(0, 10) };
                }""")
                print("Flow assets:", assets)
                break

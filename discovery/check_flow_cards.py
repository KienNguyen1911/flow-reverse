from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                p.screenshot(path='out/flow_media_cards.png')
                card_actions = p.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('[class*="card"], [class*="asset"], [class*="thumbnail"]'));
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
                        aria: b.getAttribute('aria-label') || '',
                        text: b.innerText.trim()
                    })).filter(b => b.aria.toLowerCase().includes('video') || b.aria.toLowerCase().includes('chuyển động') || b.aria.toLowerCase().includes('animate') || b.aria.toLowerCase().includes('cảnh') || b.text.toLowerCase().includes('cảnh'));
                    return { cardsCount: cards.length, buttons };
                }""")
                print("Card actions:", card_actions)
                break

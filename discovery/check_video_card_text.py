from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            card_info = p.evaluate("""() => {
                const textNodes = Array.from(document.querySelectorAll('.card, [class*="card"], [class*="tile"], [class*="item"]'))
                    .map(c => c.innerText.trim())
                    .filter(t => t.includes('%') || t.includes('Tạo') || t.includes('Render') || t.includes('8s') || t.includes('giây'));
                return textNodes.slice(0, 5);
            }""")
            print("Video progress text:", card_info)
            break

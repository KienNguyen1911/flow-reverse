from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            nav_items = p.evaluate("""() => {
                const items = [];
                document.querySelectorAll('a, button, div[role="button"]').forEach(el => {
                    const txt = (el.innerText || '').trim();
                    const href = el.getAttribute('href') || '';
                    if (txt && (txt.includes('Nabi') || txt.includes('Try-On') || txt.includes('cuộc trò chuyện mới') || txt.includes('Thiết Kế') || txt.includes('Sổ ghi chú'))) {
                        items.push({ txt, href });
                    }
                });
                return items;
            }""")
            print("Found navigation items:")
            for item in nav_items:
                print(item)

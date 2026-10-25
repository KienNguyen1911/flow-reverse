from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    # Find the card with b0959305 (Video 2)
    print("Hovering and inspecting card for Video 2...")
    card_info = flow_page.evaluate("""() => {
        const img = document.querySelector('img[src*="b0959305"]');
        if (!img) return { found: false };
        const card = img.closest('.mat-mdc-card, [class*="card"], [class*="item"]') || img.parentElement;
        return {
            found: true,
            cardTag: card.tagName,
            cardClass: card.className,
            innerHtml: card.innerHTML.slice(0, 300)
        };
    }""")
    print("Card info:", card_info)

    # Hover over the card
    card_el = flow_page.query_selector('img[src*="b0959305"]')
    if card_el:
        card_el.hover()
        flow_page.wait_for_timeout(1000)
        flow_page.screenshot(path="out/flow_v2_hovered.png")
        
        # Check if hover brought up play button or video tag
        hover_state = flow_page.evaluate("""() => {
            const v = document.querySelector('video');
            const btns = Array.from(document.querySelectorAll('button, [role="button"]')).map(b => b.innerText.trim()).filter(Boolean);
            return { hasVideo: !!v, videoSrc: v ? v.src : '', btns: btns.slice(0, 15) };
        }""")
        print("Hover state:", hover_state)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    print("Clicking on the second video card...")
    # Find the card with b0959305
    card_clicked = flow_page.evaluate("""() => {
        const img = document.querySelector('img[src*="b0959305"]');
        if (img) {
            const card = img.closest('.mat-mdc-card, [class*="card"], [class*="item"]');
            if (card) {
                card.click();
                return true;
            }
            img.click();
            return true;
        }
        return false;
    }""")
    print("Card clicked:", card_clicked)
    flow_page.wait_for_timeout(2000)
    flow_page.screenshot(path="out/flow_card_clicked.png")

    # Look for video element
    video_src = flow_page.evaluate("""() => {
        const v = document.querySelector('video');
        return v ? v.src : '';
    }""")
    print("Video element src:", video_src[:100])

    if video_src:
        # Download video via browser fetch to carry session cookies!
        print("Fetching video bytes via browser page.evaluate...")
        b64 = flow_page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""", video_src)
        
        import base64
        header, encoded = b64.split(',', 1)
        data = base64.b64decode(encoded)
        with open("out/affiliate_runs/video_2.mp4", "wb") as f:
            f.write(data)
        print(f"Downloaded Video 2 to out/affiliate_runs/video_2.mp4 ({len(data)} bytes)!")

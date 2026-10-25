import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                flow_page = p
                break

    print("Waiting for Flow image generation to complete...")
    t0 = time.time()
    seen_urls = set()
    first_frame_url = None

    while time.time() - t0 < 60:
        time.sleep(3)
        res = flow_page.evaluate("""() => {
            const spinners = document.querySelectorAll('mat-progress-spinner, [class*="progress"], [class*="generating"]');
            const imgs = Array.from(document.querySelectorAll('img'))
                .map(i => i.src)
                .filter(s => s && (s.includes('flow-content.google') || s.includes('flow.google.com/asb') || s.includes('lh3.googleusercontent.com')));
            return {
                isBusy: spinners.length > 0,
                imgs: Array.from(new Set(imgs))
            };
        }""")
        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, Total images: {len(res['imgs'])}")
        
        # Check for newly generated image
        if len(res['imgs']) > 3 and not res['isBusy']:
            # The newest generated image is typically in flow.google.com/asb or flow-content.google
            candidates = [u for u in res['imgs'] if 'flow.google.com/asb' in u or 'flow-content.google' in u]
            if candidates:
                first_frame_url = candidates[-1]
                print(f"Found First Frame image URL: {first_frame_url[:80]}...")
                flow_page.screenshot(path='out/flow_image_finished.png')
                break

    if first_frame_url:
        print("Downloading first frame image...")
        img_bytes = flow_page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const buf = await resp.arrayBuffer();
            return Array.from(new Uint8Array(buf));
        }""", first_frame_url)
        dest = Path("out/first_frame_perfect.png")
        dest.write_bytes(bytes(img_bytes))
        print(f"SAVED: {dest} ({len(img_bytes)} bytes)!")

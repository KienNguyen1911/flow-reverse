import urllib.request
from pathlib import Path

url = "https://flow.google.com/asb/ANqvLOYeA5VYyJWvuzMUPWrKB0gyAAenu5bEHvdtgdbb7fDoYsvjiwjxGM_6lvvfl5LpJ9MCTZlMlJmwDvQeWip2kg8LYqqVR8oznnOxSFg0naRPWFJJiNiUoU6efdcW8PSwVq_7jVt4UHvgJSHIgWTUoIhs9apaBliafrlThDxKPQ=s1600-rw"
dest = Path("out/first_frame_generated.png")
dest.parent.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                img_bytes = p.evaluate("""async (url) => {
                    const resp = await fetch(url);
                    const buf = await resp.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                }""", url)
                dest.write_bytes(bytes(img_bytes))
                print(f"Downloaded generated image to {dest}! Size: {len(img_bytes)} bytes")
                break

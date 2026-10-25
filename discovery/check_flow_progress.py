import time
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                info = p.evaluate("""() => {
                    const spinners = document.querySelectorAll('mat-progress-spinner, mat-progress-bar, [class*="progress"], [class*="generating"]');
                    const images = Array.from(document.querySelectorAll('img')).map(i => ({ src: i.src, alt: i.alt })).filter(i => i.src.startsWith('http') || i.src.startsWith('blob'));
                    return {
                        spinnersCount: spinners.length,
                        imagesCount: images.length,
                        latestImages: images.slice(-5)
                    };
                }""")
                print("Flow render info:", info)
                break

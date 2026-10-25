from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            info = p.evaluate("""() => {
                const textNodes = Array.from(document.querySelectorAll('.response-content, message-content, [class*="response"]')).map(e => e.innerText);
                const stopBtn = document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], input-area-v2 button');
                return {
                    count: textNodes.length,
                    lastPreview: textNodes[textNodes.length - 1]?.slice(0, 300),
                    stopBtn: stopBtn?.getAttribute('aria-label') || ''
                };
            }""")
            print("Gemini streaming state:", info)

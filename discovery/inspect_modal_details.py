from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            info = p.evaluate("""() => {
                const modal = document.querySelector('[role="dialog"], .cdk-overlay-pane, .video-player-container, [class*="detail"]');
                const downloadBtn = Array.from(document.querySelectorAll('a, button')).filter(e => {
                    const t = (e.innerText || '') + (e.getAttribute('aria-label') || '');
                    return t.toLowerCase().includes('tải xuống') || t.toLowerCase().includes('download');
                }).map(e => ({ text: e.innerText.trim(), href: e.href || '', aria: e.getAttribute('aria-label') || '' }));
                
                const allVideos = Array.from(document.querySelectorAll('video')).map(v => v.outerHTML);
                return { modal: modal ? modal.className : 'NONE', downloadBtn, allVideos };
            }""")
            print("Modal / Download info:", info)
            break

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            p.screenshot(path='out/flow_video2_current_view.png')
            videos = p.evaluate("""() => {
                return Array.from(document.querySelectorAll('video')).map(v => ({
                    src: v.src,
                    duration: v.duration,
                    paused: v.paused,
                    readyState: v.readyState
                }));
            }""")
            print("Videos currently on Flow page:", len(videos))
            for v in videos:
                print(v)
            break

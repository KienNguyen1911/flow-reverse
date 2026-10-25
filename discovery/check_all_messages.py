from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            p.screenshot(path='out/gemini_page_full_view.png')
            all_msgs = p.evaluate("""() => {
                const msgs = Array.from(document.querySelectorAll('message-content')).map(e => e.innerText);
                return { count: msgs.length, last: msgs[msgs.length - 1] };
            }""")
            print("Message content count:", all_msgs['count'])
            if all_msgs['last']:
                print("Last message (first 500 chars):")
                print(all_msgs['last'][:500])
                with open("out/step3_last_message.txt", "w", encoding="utf-8") as f:
                    f.write(all_msgs['last'])

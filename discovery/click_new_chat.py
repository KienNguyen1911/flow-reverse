from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Clicking 'Cuộc trò chuyện mới'...")
                clicked = p.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('a, button, div[role="button"]'))
                        .find(b => b.innerText.includes('Cuộc trò chuyện mới'));
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                print("Clicked new chat:", clicked)
                p.wait_for_timeout(3000)
                p.screenshot(path='out/gemini_fresh_new_chat.png')
                print("Saved out/gemini_fresh_new_chat.png!")
                break

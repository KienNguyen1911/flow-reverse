from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                # Find link 'Tạo Prompt Video Lookbook 16s'
                item = p.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a, button, div[role="button"]'));
                    const target = links.find(l => l.innerText.includes('Tạo Prompt Video Lookbook 16s'));
                    if (target) {
                        target.click();
                        return true;
                    }
                    return false;
                }""")
                print("Clicked chat:", item)
                p.wait_for_timeout(3000)
                body = p.evaluate("() => document.body.innerText")
                print("Body text tail:")
                print(body[-1500:])
                break

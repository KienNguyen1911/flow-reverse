from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    pm = flow_page.query_selector('div.ProseMirror')
    pm.click(force=True)
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    # 1. Type @
    flow_page.keyboard.type("@", delay=50)
    flow_page.wait_for_timeout(1000)
    flow_page.screenshot(path="out/flow_at_popup_now.png")

    # Inspect the popup options
    popup_data = flow_page.evaluate("""() => {
        const items = Array.from(document.querySelectorAll('.cdk-overlay-pane *')).filter(el => {
            return el.childNodes.length === 1 && el.childNodes[0].nodeType === Node.TEXT_NODE && el.innerText.trim();
        }).map(el => ({ text: el.innerText.trim(), tag: el.tagName }));
        return items;
    }""")
    print("Popup items found:", len(popup_data))
    for item in popup_data[:15]:
        print(" ", item)

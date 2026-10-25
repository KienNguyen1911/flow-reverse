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

    # Type @main
    flow_page.keyboard.type("@main", delay=80)
    flow_page.wait_for_timeout(1000)
    flow_page.screenshot(path="out/flow_at_main.png")

    # Check popup items when @main is typed
    items = flow_page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('.cdk-overlay-pane *').forEach(el => {
            if (el.childNodes.length === 1 && el.childNodes[0].nodeType === Node.TEXT_NODE && el.innerText.trim()) {
                out.push({ text: el.innerText.trim(), tag: el.tagName });
            }
        });
        return out;
    }""")
    print("Items when @main typed:", items)

    # Also check if any element has class containing 'item' or 'option'
    elements = flow_page.evaluate("""() => {
        const els = document.querySelectorAll('.cdk-overlay-pane [role="option"], .cdk-overlay-pane [role="menuitem"], .cdk-overlay-pane .item');
        return Array.from(els).map(e => ({ text: e.innerText.trim(), tag: e.tagName, cls: e.className }));
    }""")
    print("Structured items:", elements)

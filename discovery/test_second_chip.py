from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    # We already have main-model.jpg chip!
    # Now type @1
    print("Typing '@1'...")
    flow_page.keyboard.type("@1", delay=80)
    flow_page.wait_for_timeout(1000)

    # Click button.asset-item
    print("Clicking button.asset-item for 1.jpg...")
    flow_page.click("button.asset-item", timeout=3000)
    flow_page.wait_for_timeout(1000)

    # Check ProseMirror HTML
    pm_html = flow_page.evaluate("""() => {
        const pm = document.querySelector('div.ProseMirror');
        const chips = Array.from(pm.querySelectorAll('.mention-chip')).map(c => c.innerText);
        return { chips, html: pm.innerHTML, text: pm.innerText };
    }""")
    print("PM after adding second chip:", pm_html)

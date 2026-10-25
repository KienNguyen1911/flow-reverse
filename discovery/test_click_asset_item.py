from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    # We currently have the popup open with 'asset-item asset-item-active'!
    # Let's click the active button or press Enter!
    print("Clicking button.asset-item...")
    flow_page.click("button.asset-item", timeout=3000)
    flow_page.wait_for_timeout(1000)
    flow_page.screenshot(path="out/flow_after_asset_click.png")

    # Check ProseMirror HTML
    pm_html = flow_page.evaluate("""() => {
        const pm = document.querySelector('div.ProseMirror');
        return { html: pm.innerHTML, text: pm.innerText };
    }""")
    print("PM after click:", pm_html)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                flow_page = p
                break

    if not flow_page:
        print("Flow page not found!")
        exit(1)

    print("Flow URL:", flow_page.url)
    flow_page.screenshot(path='out/flow_step0.png')

    # Look for button "Trình đơn thêm nội dung nghe nhìn" or upload buttons
    add_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"], button[aria-label*="thêm"], button[aria-label*="Thêm"]')
    if add_btn:
        print("Found add button:", add_btn.get_attribute('aria-label'))
        add_btn.click()
        flow_page.wait_for_timeout(1000)
        flow_page.screenshot(path='out/flow_add_clicked.png')
        
        # Check for menu items or file inputs
        items = flow_page.evaluate("""() => {
            const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], mat-menu-item, button'))
                .map(e => e.innerText.trim()).filter(Boolean);
            const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
                accept: i.accept,
                multiple: i.multiple
            }));
            return { menuItems: menuItems.slice(0, 20), fileInputs };
        }""")
        print("Menu items & file inputs:", items)
    else:
        print("Add button not found!")

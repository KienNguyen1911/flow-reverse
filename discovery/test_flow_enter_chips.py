from playwright.sync_api import sync_playwright

prompt_text = " A photorealistic, candid lifestyle fashion portrait of the model wearing the complete outfit from the reference image, posing in the bakery store, high-end details, natural lighting."

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

    print("Found flow page!")
    pm = flow_page.query_selector('div.ProseMirror[contenteditable="true"]')
    if not pm:
        print("ProseMirror not found!")
        exit(1)

    # Click and clear
    pm.click()
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    # 1. Type @main-model and press Enter
    print("Typing '@main-model'...")
    flow_page.keyboard.type("@main-model", delay=50)
    flow_page.wait_for_timeout(800)
    print("Pressing Enter to select main-model.jpg chip...")
    flow_page.keyboard.press("Enter")
    flow_page.wait_for_timeout(500)

    # 2. Type space + @1.jpg and press Enter
    print("Typing ' @1.jpg'...")
    flow_page.keyboard.type(" @1.jpg", delay=50)
    flow_page.wait_for_timeout(800)
    print("Pressing Enter to select 1.jpg chip...")
    flow_page.keyboard.press("Enter")
    flow_page.wait_for_timeout(500)

    # 3. Type rest of prompt
    print("Typing rest of prompt text...")
    flow_page.keyboard.type(prompt_text, delay=10)
    flow_page.wait_for_timeout(800)

    # Take screenshot of the composer to verify both chips!
    flow_page.screenshot(path='out/flow_chips_verified.png')
    print("Saved out/flow_chips_verified.png!")

    # Check composer HTML to see the chips
    composer_html = flow_page.evaluate("""() => {
        const pm = document.querySelector('div.ProseMirror');
        const chips = Array.from(pm.querySelectorAll('*')).map(e => e.className || e.tagName);
        return { text: pm.innerText, chips: chips };
    }""")
    print("Composer content:", composer_html)

    # 4. Click the generate arrow button
    print("Clicking generate button...")
    clicked = flow_page.evaluate("""() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            b.innerText.includes('arrow_forward') || 
            b.innerText.includes('Bắt đầu tạo') || 
            (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo')
        );
        if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
            btn.click();
            return true;
        }
        return false;
    }""")
    print("Generate clicked:", clicked)
    flow_page.wait_for_timeout(5000)
    flow_page.screenshot(path='out/flow_generating_chips.png')
    print("Saved out/flow_generating_chips.png!")

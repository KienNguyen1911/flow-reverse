from playwright.sync_api import sync_playwright

clean_video_prompt = (
    "A cinematic realistic 8-second fashion video starting seamlessly from the reference image. "
    "The subject naturally takes two gentle steps forward along the sunny sidewalk, smiles warmly towards the camera, "
    "soft natural breeze fluttering the dress hem and cardigan, authentic 24fps cadence, real-time natural speed, "
    "subtle handheld micro-movements, warm golden sunlight, realistic fabric motion."
)

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    # Dismiss any alerts / click undo or delete on failed card
    flow_page.evaluate("""() => {
        const undoBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('undo') || b.innerText.includes('delete_forever'));
        undoBtns.forEach(b => b.click());
    }""")
    flow_page.wait_for_timeout(1000)

    # Focus ProseMirror
    pm = flow_page.query_selector('div.ProseMirror')
    pm.click(force=True)
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    # Type @first_frame to select starting frame chip
    print("Typing '@first_frame'...")
    flow_page.keyboard.type("@first_frame", delay=50)
    flow_page.wait_for_timeout(800)

    # Select chip
    flow_page.click("button.asset-item", timeout=3000)
    flow_page.wait_for_timeout(500)

    # Type clean video prompt
    print("Typing clean video prompt...")
    flow_page.keyboard.type(" " + clean_video_prompt, delay=5)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path="out/flow_clean_vp1_ready.png")
    print("Saved out/flow_clean_vp1_ready.png")

    # Click Generate
    flow_page.click("button.generate-icon-button", force=True)
    print("Clicked Generate!")
    flow_page.wait_for_timeout(3000)

    flow_page.screenshot(path="out/flow_clean_vp1_started.png")
    print("Saved out/flow_clean_vp1_started.png")

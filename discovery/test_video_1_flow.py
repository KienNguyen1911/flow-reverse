from pathlib import Path
from playwright.sync_api import sync_playwright

first_frame = Path("out/first_frame_perfect.png").resolve()
video_prompt_1 = "A cinematic realistic 8-second video of the woman turning towards the camera with a gentle warm smile, soft ambient store lighting, realistic fabric and hair movement, smooth 1x real-time speed."

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                flow_page = p
                break

    print("Found flow page!")
    
    # 1. Upload first_frame_perfect.png to Flow media
    print("Uploading first_frame_perfect.png to Flow...")
    add_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
    if add_btn:
        add_btn.click(force=True)
        flow_page.wait_for_timeout(600)
        upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
        if upload_btn:
            with flow_page.expect_file_chooser(timeout=5000) as fc:
                upload_btn.click(force=True)
            file_chooser = fc.value
            file_chooser.set_files([str(first_frame)])
            print("Files set! Waiting 5s for upload...")
            flow_page.wait_for_timeout(5000)

    # Close any overlay
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 2. In ProseMirror: type @first_frame + Enter
    pm = flow_page.query_selector('div.ProseMirror')
    pm.click()
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    print("Typing '@first_frame'...")
    flow_page.keyboard.type("@first_frame", delay=50)
    flow_page.wait_for_timeout(800)
    print("Pressing Enter to select chip...")
    flow_page.keyboard.press("Enter")
    flow_page.wait_for_timeout(500)

    # 3. Type video prompt
    print("Typing video prompt 1...")
    flow_page.keyboard.type(" " + video_prompt_1, delay=10)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path='out/flow_video1_ready.png')
    print("Saved out/flow_video1_ready.png!")

    # 4. Click generate
    print("Clicking generate...")
    clicked = flow_page.evaluate("""() => {
        const btn = document.querySelector('button.generate-icon-button') || Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('arrow_forward'));
        if (btn && !btn.disabled && !btn.classList.contains('mat-mdc-button-disabled')) {
            btn.click();
            return true;
        }
        return false;
    }""")
    print("Generate clicked:", clicked)
    flow_page.wait_for_timeout(4000)
    flow_page.screenshot(path='out/flow_video1_started.png')
    print("Saved out/flow_video1_started.png!")

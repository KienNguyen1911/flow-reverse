import sys
import time
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

first_frame = Path("out/first_frame_perfect.png").resolve()
vp1_text = Path("out/video_prompt_1_clean.txt").read_text(encoding="utf-8")

# Prepare single-paragraph prompt for Flow composer
# Remove markdown bullet points so it flows smoothly in the prompt box
clean_vp1 = " ".join([l.strip() for l in vp1_text.splitlines() if l.strip()])

print("First frame exists:", first_frame.exists(), "size:", first_frame.stat().st_size)
print("Video prompt 1 length:", len(clean_vp1))

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    if not flow_page:
        print("Flow page not found!")
        sys.exit(1)

    print("Found Flow page:", flow_page.url)
    flow_page.bring_to_front()
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 1. Switch to Video mode (8s)
    print("Switching to Video mode...")
    model_btn = flow_page.query_selector('button.model-selector-button, [aria-label*="chọn mô hình"], [class*="model-select"]')
    if model_btn:
        model_btn.click(force=True)
        flow_page.wait_for_timeout(800)
        # Click "Video"
        video_opt = flow_page.query_selector('//button[contains(., "Video")] | //div[contains(., "Video") and @role="menuitem"]')
        if video_opt:
            video_opt.click(force=True)
            flow_page.wait_for_timeout(800)

    # 2. Upload first_frame_perfect.png to Flow media
    print("Uploading first_frame_perfect.png to Flow media...")
    add_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
    if add_btn:
        add_btn.click(force=True)
        flow_page.wait_for_timeout(800)
        upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
        if upload_btn:
            try:
                with flow_page.expect_file_chooser(timeout=4000) as fc:
                    upload_btn.click(force=True)
                fc.value.set_files([str(first_frame)])
                print("Uploaded first_frame_perfect.png to Flow! Waiting 5s...")
                flow_page.wait_for_timeout(5000)
            except Exception as e:
                print("Upload dialog:", e)
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 3. Focus ProseMirror and type @first_frame
    pm = flow_page.query_selector('div.ProseMirror')
    pm.click(force=True)
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    print("Typing '@first_frame'...")
    flow_page.keyboard.type("@first_frame", delay=60)
    flow_page.wait_for_timeout(1000)

    # Click asset item in popup
    print("Clicking button.asset-item in popup...")
    clicked_chip = flow_page.evaluate("""() => {
        const item = document.querySelector('button.asset-item, .cdk-overlay-pane [role="option"]');
        if (item) {
            item.click();
            return true;
        }
        return false;
    }""")
    print("Chip clicked:", clicked_chip)
    flow_page.wait_for_timeout(600)

    # 4. Type Video Prompt 1
    print("Typing Video Prompt 1 into composer...")
    flow_page.keyboard.type(" " + clean_vp1, delay=2)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path="out/flow_video1_ready.png")
    print("Saved out/flow_video1_ready.png!")

    # Check generate button status
    btn_status = flow_page.evaluate("""() => {
        const btn = document.querySelector('button.generate-icon-button') || 
                    Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('arrow_forward'));
        return {
            disabled: btn ? (btn.disabled || btn.classList.contains('mat-mdc-button-disabled')) : null,
            ariaDisabled: btn ? btn.getAttribute('aria-disabled') : null
        };
    }""")
    print("Generate button status before click:", btn_status)

    # Initial videos before generation
    init_videos = flow_page.evaluate("""() => {
        return Array.from(document.querySelectorAll('video')).map(v => v.src).filter(Boolean);
    }""")
    print(f"Flow videos before generate: {len(init_videos)}")

    # 5. Click Generate
    flow_page.click("button.generate-icon-button", force=True)
    print("Generate button clicked!")
    flow_page.wait_for_timeout(3000)

    flow_page.screenshot(path="out/flow_video1_generating.png")
    print("Saved out/flow_video1_generating.png!")

    # 6. Poll for video completion (videos take ~2-4 minutes)
    print("Waiting for Video 1 rendering to finish...")
    t0 = time.time()
    video_url = ""
    while time.time() - t0 < 300:
        time.sleep(5)
        res = flow_page.evaluate("""(inits) => {
            const cur = Array.from(document.querySelectorAll('video')).map(v => v.src).filter(Boolean);
            const diff = cur.filter(s => !inits.includes(s));
            const isBusy = !!document.querySelector('mat-progress-spinner, mat-progress-bar, [class*="generating"]');
            const alert = document.querySelector('[role="alert"], [class*="alert"]')?.innerText || '';
            return {
                isBusy,
                curCount: cur.length,
                newCount: diff.length,
                newSrc: diff[0] || '',
                alert
            };
        }""", init_videos)

        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, New videos: {res['newCount']}, Alert: {res['alert']}")

        if res['newCount'] > 0 and not res['isBusy']:
            video_url = res['newSrc']
            print("Video 1 generated successfully!", video_url[:80])
            break

    flow_page.screenshot(path="out/flow_video1_finished.png")

    out_dir = Path("out/affiliate_runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    video_1_path = out_dir / "video_1.mp4"

    if video_url:
        print("Downloading video 1 from URL...")
        resp = requests.get(video_url, timeout=60)
        video_1_path.write_bytes(resp.content)
        print(f"Saved {video_1_path} ({len(resp.content)} bytes)!")
    else:
        print("Checking if video is available via DOM or blob...")
        # Check if there is any new video in the media cards
        v_src = flow_page.evaluate("""() => {
            const v = document.querySelector('video');
            return v ? v.src : '';
        }""")
        if v_src and 'blob:' not in v_src:
            resp = requests.get(v_src, timeout=60)
            video_1_path.write_bytes(resp.content)
            print(f"Saved {video_1_path} from querySelector ({len(resp.content)} bytes)!")

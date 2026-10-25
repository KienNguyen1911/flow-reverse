import sys
import time
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

last_frame = Path("out/affiliate_runs/last_frame_video_1.png").resolve()

clean_vp2 = (
    "A continuous candid street fashion video, 16:9 aspect ratio, real-time natural speed (1x speed), "
    "authentic 24fps cadence, seamless continuation from the previous shot. "
    "Starting from the exact ending pose, she gently lets her right hand drop down, then does a fluid, "
    "graceful 3/4 turn toward the storefront display windows to showcase the full silhouette of the dress "
    "and cardigan from the side. She glances playfully over her shoulder back toward the camera with a "
    "confident, radiant laugh, then turns forward again. Natural fabric movement and flutter during turning, "
    "authentic warm sidewalk lighting, subtle handheld micro-movements, realistic fabric motion."
)

print("Last frame exists:", last_frame.exists(), "size:", last_frame.stat().st_size)
print("Video prompt 2 length:", len(clean_vp2))

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

    # 1. Upload last_frame_video_1.png to Flow media
    print("Uploading last_frame_video_1.png to Flow media...")
    add_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
    if add_btn:
        add_btn.click(force=True)
        flow_page.wait_for_timeout(800)
        upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
        if upload_btn:
            try:
                with flow_page.expect_file_chooser(timeout=4000) as fc:
                    upload_btn.click(force=True)
                fc.value.set_files([str(last_frame)])
                print("Uploaded last_frame_video_1.png to Flow! Waiting 5s...")
                flow_page.wait_for_timeout(5000)
            except Exception as e:
                print("Upload dialog:", e)
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 2. Focus ProseMirror and type @last_frame
    pm = flow_page.query_selector('div.ProseMirror')
    pm.click(force=True)
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    print("Typing '@last_frame'...")
    flow_page.keyboard.type("@last_frame", delay=60)
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

    # 3. Type Video Prompt 2
    print("Typing Video Prompt 2 into composer...")
    flow_page.keyboard.type(" " + clean_vp2, delay=2)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path="out/flow_video2_ready.png")
    print("Saved out/flow_video2_ready.png!")

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

    # 4. Click Generate
    flow_page.click("button.generate-icon-button", force=True)
    print("Generate button clicked!")
    flow_page.wait_for_timeout(3000)

    flow_page.screenshot(path="out/flow_video2_generating.png")
    print("Saved out/flow_video2_generating.png!")

    # 5. Poll for video completion
    print("Waiting for Video 2 rendering to finish...")
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
            print("Video 2 generated successfully!", video_url[:80])
            break

    flow_page.screenshot(path="out/flow_video2_finished.png")

    out_dir = Path("out/affiliate_runs")
    video_2_path = out_dir / "video_2.mp4"

    if video_url:
        print("Downloading video 2 from URL...")
        resp = requests.get(video_url, timeout=60)
        video_2_path.write_bytes(resp.content)
        print(f"Saved {video_2_path} ({len(resp.content)} bytes)!")
    else:
        print("Fallback querySelector for video 2...")
        v_src = flow_page.evaluate("""() => {
            const vs = Array.from(document.querySelectorAll('video')).map(v => v.src).filter(s => s && !s.includes('blob:'));
            return vs.length > 0 ? vs[0] : '';
        }""")
        if v_src:
            resp = requests.get(v_src, timeout=60)
            video_2_path.write_bytes(resp.content)
            print(f"Saved {video_2_path} ({len(resp.content)} bytes)!")

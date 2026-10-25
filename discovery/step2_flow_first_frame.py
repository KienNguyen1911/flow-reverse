import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")
prompt_file = Path("out/first_frame_prompt.txt")
prompt_text = prompt_file.read_text(encoding="utf-8")

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
    flow_page.wait_for_timeout(1000)

    # Dismiss any active overlay/dialog
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 1. Switch model to Image Mode (Nano Banana 2.1) if needed
    print("Checking current model mode...")
    current_mode = flow_page.evaluate("""() => {
        const btn = document.querySelector('button.model-selector-button, [aria-label*="chọn mô hình"], [class*="model-select"]');
        return btn ? btn.innerText.trim() : '';
    }""")
    print("Current model button text:", repr(current_mode))

    if "Video" in current_mode or "videocam" in current_mode:
        print("Switching back to Image mode...")
        model_btn = flow_page.query_selector('button.model-selector-button, [aria-label*="chọn mô hình"], [class*="model-select"]')
        if model_btn:
            model_btn.click(force=True)
            flow_page.wait_for_timeout(800)
            img_mode = flow_page.query_selector('//button[contains(., "Hình ảnh") or contains(., "Banana")]')
            if img_mode:
                img_mode.click(force=True)
                flow_page.wait_for_timeout(800)

    # 2. Upload model & garment images to project if not already present
    print("Ensuring images are uploaded to Flow...")
    add_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
    if add_btn:
        add_btn.click(force=True)
        flow_page.wait_for_timeout(800)
        upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
        if upload_btn:
            try:
                with flow_page.expect_file_chooser(timeout=4000) as fc:
                    upload_btn.click(force=True)
                fc.value.set_files([str(model_img), str(garment_img)])
                print("Uploaded both files to Flow, waiting 5s...")
                flow_page.wait_for_timeout(5000)
            except Exception as e:
                print("File chooser not triggered or cancelled:", e)
    flow_page.keyboard.press("Escape")
    flow_page.wait_for_timeout(500)

    # 3. Focus ProseMirror and type chips with Enter
    pm = flow_page.query_selector('div.ProseMirror')
    pm.click(force=True)
    flow_page.keyboard.press("Control+A")
    flow_page.keyboard.press("Backspace")
    flow_page.wait_for_timeout(300)

    print("Typing '@main-model'...")
    flow_page.keyboard.type("@main-model", delay=50)
    flow_page.wait_for_timeout(800)
    print("Pressing Enter to select @main-model...")
    flow_page.keyboard.press("Enter")
    flow_page.wait_for_timeout(600)

    print("Typing ' @1.jpg'...")
    flow_page.keyboard.type(" @1.jpg", delay=50)
    flow_page.wait_for_timeout(800)
    print("Pressing Enter to select @1.jpg...")
    flow_page.keyboard.press("Enter")
    flow_page.wait_for_timeout(600)

    # Verify chips in ProseMirror
    chips_status = flow_page.evaluate("""() => {
        const pm = document.querySelector('div.ProseMirror');
        const chips = Array.from(pm.querySelectorAll('mention-chip, [class*="chip"]')).map(c => c.innerText.trim());
        return { count: chips.length, chips: chips, html: pm.innerHTML };
    }""")
    print("Chips status after Enter:", chips_status['chips'])
    print("HTML preview:", chips_status['html'][:200])

    # 4. Type the prompt
    print("Typing prompt into ProseMirror...")
    flow_page.keyboard.type(" " + prompt_text, delay=5)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path="out/flow_stage2_ready.png")
    print("Saved out/flow_stage2_ready.png")

    # Record initial images before generation
    initial_imgs = flow_page.evaluate("""() => {
        return Array.from(document.querySelectorAll('img')).map(img => img.src).filter(s => s && s.includes('flow-content'));
    }""")
    print(f"Flow images before generation: {len(initial_imgs)}")

    # 5. Click Generate
    print("Clicking Generate button...")
    gen_clicked = flow_page.evaluate("""() => {
        const btn = document.querySelector('button.generate-icon-button') || 
                    Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('arrow_forward'));
        if (btn && !btn.disabled && !btn.classList.contains('mat-mdc-button-disabled')) {
            btn.click();
            return true;
        }
        return false;
    }""")
    print("Generate clicked:", gen_clicked)
    flow_page.wait_for_timeout(3000)

    flow_page.screenshot(path="out/flow_stage2_generating.png")

    # 6. Monitor generation until new image appears
    print("Waiting for image generation to finish...")
    t0 = time.time()
    new_image_src = ""
    while time.time() - t0 < 120:
        time.sleep(3)
        res = flow_page.evaluate("""(initSrcs) => {
            const curImgs = Array.from(document.querySelectorAll('img')).map(img => img.src).filter(s => s && s.includes('flow-content'));
            const newImgs = curImgs.filter(s => !initSrcs.includes(s));
            const isBusy = !!document.querySelector('mat-progress-spinner, mat-progress-bar, [class*="generating"]');
            return {
                isBusy: isBusy,
                curCount: curImgs.length,
                newCount: newImgs.length,
                newSrc: newImgs.length > 0 ? newImgs[0] : ''
            };
        }""", initial_imgs)

        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, New count: {res['newCount']}")

        if res["newCount"] > 0 and not res["isBusy"]:
            new_image_src = res["newSrc"]
            print("New generated image found!", new_image_src[:80])
            break

    flow_page.screenshot(path="out/flow_stage2_finished.png")

    if new_image_src:
        # Download the new image
        import requests
        print("Downloading generated image...")
        resp = requests.get(new_image_src, timeout=30)
        first_frame_path = Path("out/first_frame_perfect.png")
        first_frame_path.write_bytes(resp.content)
        print(f"Saved {first_frame_path} ({len(resp.content)} bytes)!")
    else:
        print("Generation did not produce new image within timeout or image already existed.")

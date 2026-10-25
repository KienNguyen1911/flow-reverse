import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

first_frame = Path("out/first_frame_perfect.png").resolve()

print(f"First Frame file: {first_frame} (exists: {first_frame.exists()}, size: {first_frame.stat().st_size})")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    gemini_page = None
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            gemini_page = p
            break

    if not gemini_page:
        print("Gemini page not found!")
        sys.exit(1)

    print("Found Gemini page:", gemini_page.url)
    gemini_page.bring_to_front()
    gemini_page.wait_for_timeout(1000)

    # 1. Open upload menu
    print("Opening upload menu...")
    add_btn = gemini_page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button, button[aria-label*='Nội dung tải lên']")
    if add_btn:
        add_btn.click()
        gemini_page.wait_for_timeout(800)

    # Locate input[type=file]
    file_inputs = gemini_page.query_selector_all("input[type=file]")
    if not file_inputs:
        print("ERROR: input[type=file] not found!")
        sys.exit(1)

    print("Uploading first_frame_perfect.png...")
    file_inputs[0].set_input_files([str(first_frame)])
    
    # Wait for upload preview chip
    print("Waiting for upload preview...")
    t0 = time.time()
    while time.time() - t0 < 30:
        time.sleep(1)
        st = gemini_page.evaluate("""() => {
            const previews = document.querySelectorAll('uploader-file-preview, .file-preview-chip, gem-media-attachment');
            const spinners = document.querySelectorAll('uploader-file-preview mat-progress-spinner, .file-preview-chip mat-progress-spinner');
            return { count: previews.length, spinners: spinners.length };
        }""")
        if st['count'] > 0 and st['spinners'] == 0:
            print("First frame uploaded ready!")
            break

    # Dismiss any leftover menu overlay
    gemini_page.keyboard.press("Escape")
    gemini_page.wait_for_timeout(500)

    # 2. Focus editor and activate @try-on-prompter
    editor = gemini_page.query_selector("div.ql-editor, rich-textarea")
    editor.click()
    gemini_page.keyboard.press("Control+A")
    gemini_page.keyboard.press("Backspace")
    gemini_page.wait_for_timeout(300)

    print("Typing '@try-on'...")
    gemini_page.keyboard.type("@try-on", delay=40)
    gemini_page.wait_for_timeout(1000)

    # Click try-on-prompter in dropdown
    print("Selecting try-on-prompter from dropdown...")
    clicked_skill = gemini_page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('*')).filter(e => 
            e.childNodes.length === 1 && 
            e.childNodes[0].nodeType === Node.TEXT_NODE && 
            e.innerText.trim() === 'try-on-prompter'
        );
        if (els.length > 0) {
            els[0].click();
            return true;
        }
        return false;
    }""")
    print("Skill tag activated:", clicked_skill)
    gemini_page.wait_for_timeout(600)

    # Type command for 2 video prompts (8s each)
    command = "tạo 2 video prompt 8s mỗi video tiếp nối nhau cho google flow video generation từ ảnh trên"
    print(f"Typing command: '{command}'...")
    gemini_page.keyboard.type(command, delay=15)
    gemini_page.wait_for_timeout(1000)

    gemini_page.screenshot(path="out/step3_gemini_prompt_ready.png")

    before_count = gemini_page.evaluate("document.querySelectorAll('model-response').length")
    print(f"Responses before: {before_count}")

    # Send
    send_btn = gemini_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        print("Clicking send button...")
        send_btn.click()
    else:
        print("Pressing Enter to send...")
        gemini_page.keyboard.press("Enter")

    print("Prompt sent! Waiting for streaming response...")
    t0 = time.time()
    last_text = ""
    stable_count = 0
    full_response = ""

    while time.time() - t0 < 120:
        time.sleep(2)
        res = gemini_page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
            if (mrs.length <= before) return { ready: false, isBusy, text: '' };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            return { ready: !isBusy && clean.length > 50, text: text, cleanLen: clean.length, isBusy: isBusy };
        }""", before_count)

        cur_text = res.get("text", "")
        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, Length: {len(cur_text)}")

        if res.get("ready"):
            if len(cur_text) == len(last_text) and not res["isBusy"]:
                stable_count += 1
                if stable_count >= 2:
                    print("Gemini response is finished!")
                    full_response = cur_text
                    break
            else:
                stable_count = 0
            last_text = cur_text

    gemini_page.screenshot(path="out/step3_gemini_result.png")
    if not full_response:
        full_response = last_text

    Path("out/step3_gemini_raw.txt").write_text(full_response, encoding="utf-8")
    print("Full response saved to out/step3_gemini_raw.txt!")

    # Parse the two video prompts
    from src.Bridge.gemini_bridge import parse_gemini_video_prompts
    vp1, vp2 = parse_gemini_video_prompts(full_response)
    print("\n=== PARSED VIDEO PROMPT 1 ===")
    print(vp1)
    print("\n=== PARSED VIDEO PROMPT 2 ===")
    print(vp2)

    Path("out/video_prompt_1.txt").write_text(vp1, encoding="utf-8")
    Path("out/video_prompt_2.txt").write_text(vp2, encoding="utf-8")

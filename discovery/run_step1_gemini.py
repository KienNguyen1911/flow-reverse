import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

print(f"Model image: {model_img} (exists={model_img.exists()}, size={model_img.stat().st_size if model_img.exists() else 0})")
print(f"Garment image: {garment_img} (exists={garment_img.exists()}, size={garment_img.stat().st_size if garment_img.exists() else 0})")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    target_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                target_page = p
                break
        if target_page:
            break

    if not target_page:
        print("Gemini page not found, opening new page...")
        ctx = browser.contexts[0]
        target_page = ctx.new_page()

    # Navigate to Nabi Studio
    print("Navigating to Nabi Studio: https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553")
    target_page.goto("https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553", wait_until="domcontentloaded", timeout=45000)
    target_page.wait_for_timeout(3000)

    # 1. Reset / Start clean chat in Nabi Studio
    print("Resetting to clean chat...")
    target_page.evaluate("""() => {
        const newChatBtn = document.querySelector('a[href*="/app/"], a[aria-label*="Cuộc trò chuyện mới"], button[aria-label*="Cuộc trò chuyện mới"]');
        if (newChatBtn) newChatBtn.click();
    }""")
    target_page.wait_for_timeout(2000)

    # Open upload menu
    print("Opening upload menu...")
    add_btn = target_page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button")
    if add_btn:
        add_btn.click()
        target_page.wait_for_timeout(1000)

    # Locate input[type=file]
    file_input = target_page.query_selector("input[type=file]")
    if not file_input:
        print("ERROR: input[type=file] not found!")
        sys.exit(1)

    print("Uploading 2 images: main-model.jpg & 1.jpg...")
    file_input.set_input_files([str(model_img), str(garment_img)])
    
    # Wait for uploads to complete
    print("Waiting for file preview chips...")
    t0 = time.time()
    while time.time() - t0 < 30:
        time.sleep(1)
        st = target_page.evaluate("""() => {
            const previews = document.querySelectorAll('uploader-file-preview, .file-preview-chip, gem-media-attachment');
            const spinners = document.querySelectorAll('uploader-file-preview mat-progress-spinner, .file-preview-chip mat-progress-spinner, [xapfileselectordropzone] mat-progress-spinner');
            return { count: previews.length, spinners: spinners.length };
        }""")
        print(f"Previews: {st['count']}, Spinners: {st['spinners']}")
        if st['count'] >= 2 and st['spinners'] == 0:
            print("Both images uploaded and ready!")
            break

    target_page.screenshot(path="out/step1_gemini_uploaded.png")

    # Focus editor
    editor = target_page.query_selector("div.ql-editor[contenteditable='true'], div.ql-editor, rich-textarea")
    editor.click()
    target_page.keyboard.press("Control+A")
    target_page.keyboard.press("Backspace")
    target_page.wait_for_timeout(300)

    print("Typing '@try-on-prompter'...")
    target_page.keyboard.type("@try-on-prompter", delay=30)
    target_page.wait_for_timeout(800)
    print("Pressing Enter to activate skill tag...")
    target_page.keyboard.press("Enter")
    target_page.wait_for_timeout(600)
    
    print("Typing prompt...")
    target_page.keyboard.type(" Tạo prompt ảnh kết hợp người mẫu và mẫu mặc thử trên", delay=15)
    target_page.wait_for_timeout(1000)

    target_page.screenshot(path="out/step1_gemini_prompt_ready.png")

    before_count = target_page.evaluate("document.querySelectorAll('model-response').length")
    print(f"Responses before send: {before_count}")

    # Send
    send_btn = target_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        print("Clicking Send button...")
        send_btn.click()
    else:
        print("Pressing Enter to send...")
        target_page.keyboard.press("Enter")

    print("Prompt sent! Waiting for streaming response...")
    t0 = time.time()
    last_text = ""
    stable_count = 0
    full_response = ""

    while time.time() - t0 < 90:
        time.sleep(2)
        res = target_page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
            if (mrs.length <= before) return { ready: false, isBusy, text: '' };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            return { ready: !isBusy && clean.length > 40, text: text, cleanLen: clean.length, isBusy: isBusy };
        }""", before_count)
        
        cur_text = res.get("text", "")
        print(f"[{time.time()-t0:.1f}s] Ready: {res['ready']}, Busy: {res['isBusy']}, Length: {len(cur_text)}")
        
        if res.get("ready"):
            if len(cur_text) == len(last_text) and not res["isBusy"]:
                stable_count += 1
                if stable_count >= 2:
                    print("Gemini response is finished and stable!")
                    full_response = cur_text
                    break
            else:
                stable_count = 0
            last_text = cur_text

    target_page.screenshot(path="out/step1_gemini_finished.png")
    
    if not full_response:
        full_response = last_text

    print("=== RAW RESPONSE ===")
    print(full_response[:500])
    
    Path("out/gemini_step1_raw.txt").write_text(full_response, encoding="utf-8")
    
    # Parse image prompt
    from src.Bridge.gemini_bridge import parse_gemini_image_prompt
    clean_image_prompt = parse_gemini_image_prompt(full_response)
    print("\n=== PARSED CLEAN IMAGE PROMPT ===")
    print(clean_image_prompt)
    
    Path("out/step1_image_prompt.txt").write_text(clean_image_prompt, encoding="utf-8")
    print("\nSaved out/step1_image_prompt.txt successfully!")

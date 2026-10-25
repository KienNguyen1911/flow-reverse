from pathlib import Path
import time
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

print(f"Model image: {model_img} (exists: {model_img.exists()})")
print(f"Garment image: {garment_img} (exists: {garment_img.exists()})")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                page = p
                break

    if not page:
        print("Gemini page not found!")
        exit(1)

    print("Gemini page URL:", page.url)

    # 1. Click "Cuộc trò chuyện mới" to reset to a clean state
    new_chat_btn = page.query_selector('//a[contains(., "Cuộc trò chuyện mới")] | //button[contains(., "Cuộc trò chuyện mới")]')
    if new_chat_btn:
        print("Clicking 'Cuộc trò chuyện mới'...")
        new_chat_btn.click()
        page.wait_for_timeout(2000)

    # Or navigate directly to the notebook to ensure fresh conversation in notebook
    page.goto('https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553', wait_until='domcontentloaded')
    page.wait_for_timeout(3000)

    # 2. Upload the two correct images
    print("Finding upload menu / file input...")
    # Open upload menu
    add_btn = page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button")
    if add_btn:
        add_btn.click()
        page.wait_for_timeout(1000)

    file_input = page.query_selector("input[type=file]")
    if not file_input:
        print("ERROR: input[type=file] not found!")
        exit(1)

    print("Uploading 2 correct images: main-model.jpg and 1.jpg...")
    file_input.set_input_files([str(model_img), str(garment_img)])
    page.wait_for_timeout(4000)
    page.screenshot(path='out/gemini_2_images_uploaded.png')
    print("Screenshot saved to out/gemini_2_images_uploaded.png!")

    # 3. Enter @try-on-prompter + Enter, then ' create image prompt'
    editor = page.query_selector('div.ql-editor')
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(300)

    print("Typing '@try-on-prompter'...")
    page.keyboard.type("@try-on-prompter", delay=30)
    page.wait_for_timeout(600)
    print("Pressing Enter to activate skill...")
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    print("Typing ' create image prompt'...")
    page.keyboard.type(" create image prompt", delay=20)
    page.wait_for_timeout(800)
    page.screenshot(path='out/gemini_editor_ready.png')

    before_count = page.evaluate("document.querySelectorAll('model-response').length")

    # 4. Click Send
    send_btn = page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
    if send_btn and not send_btn.is_disabled():
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    print("Prompt sent! Waiting for Gemini response streaming...")
    t0 = time.time()
    last_text = ""
    while time.time() - t0 < 90:
        time.sleep(3)
        res = page.evaluate("""(before) => {
            const mrs = document.querySelectorAll('model-response');
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
            if (mrs.length <= before) return { ready: false, isBusy };
            const last = mrs[mrs.length - 1];
            const text = (last.innerText || '').trim();
            const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
            return { ready: !isBusy && clean.length > 50, text: text, cleanLen: clean.length, isBusy: isBusy };
        }""", before_count)
        print(f"[{time.time()-t0:.1f}s] Ready: {res['ready']}, Busy: {res['isBusy']}, CleanLen: {res.get('cleanLen', 0)}")
        if res.get('ready'):
            print("=== GEMINI IMAGE PROMPT COMPLETED! ===")
            print(res['text'])
            Path("out/image_prompt_result.txt").write_text(res['text'], encoding="utf-8")
            break

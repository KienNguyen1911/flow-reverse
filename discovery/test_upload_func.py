from pathlib import Path
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    page = [p for ctx in browser.contexts for p in ctx.pages if 'gemini.google.com' in p.url][0]
    
    # Wait for input area
    page.wait_for_selector("input-area-v2, div.ql-editor", timeout=15000)
    
    def get_input():
        for inp in page.query_selector_all('input[type=file]'):
            acc = (inp.get_attribute('accept') or '').lower()
            if 'image' in acc:
                return inp
        return None

    inp = get_input()
    print('Initial input:', inp is not None)
    if not inp:
        sel = "simplified-input-menu button, button[aria-label*='tải lên' i], button:has(mat-icon[fonticon='plus'])"
        btn = page.query_selector(sel)
        if btn:
            expanded = btn.get_attribute('aria-expanded')
            print("Button expanded:", expanded)
            if expanded != 'true':
                page.click(sel)
                time.sleep(1.0)
        inp = get_input()
        print('After click input:', inp is not None)
    
    img1 = Path('out/uploads/1792955358411_main-model.jpg').resolve()
    img2 = Path('out/uploads/1792955345724_1.jpg').resolve()
    if inp:
        inp.set_input_files([str(img1), str(img2)])
        print('Uploaded files successfully!')
        time.sleep(2.0)
        chips = page.query_selector_all("uploader-file-preview, .file-preview-chip")
        print("Attachment chips count:", len(chips))

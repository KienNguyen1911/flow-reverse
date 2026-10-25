from pathlib import Path
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Found flow!")
                # First click the main add media button
                add_btn = p.query_selector('button[aria-label*="nghe nhìn"]')
                if add_btn:
                    add_btn.click(force=True)
                    p.wait_for_timeout(600)
                
                # Now find the Upload button in the opened overlay
                upload_btn = p.query_selector('//button[contains(., "Tải lên")]')
                print("Upload button found:", upload_btn is not None)
                if upload_btn:
                    with p.expect_file_chooser(timeout=8000) as fc:
                        upload_btn.click(force=True)
                    file_chooser = fc.value
                    print("SUCCESS! File chooser caught!")
                    file_chooser.set_files([str(model_img), str(garment_img)])
                    print("Files passed to file chooser!")
                    p.wait_for_timeout(6000)
                    p.screenshot(path='out/flow_uploaded_success.png')
                    print("Saved out/flow_uploaded_success.png!")
                break

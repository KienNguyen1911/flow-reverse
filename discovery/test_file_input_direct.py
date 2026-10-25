from pathlib import Path
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            print("Found Gemini page!")
            file_inputs = p.query_selector_all("input[type=file]")
            print(f"Found {len(file_inputs)} file inputs.")
            if file_inputs:
                file_inputs[0].set_input_files([str(model_img), str(garment_img)])
                print("Uploaded files! Waiting 5s...")
                p.wait_for_timeout(5000)
                p.screenshot(path="out/gemini_files_set.png")
                print("Saved out/gemini_files_set.png")
            break

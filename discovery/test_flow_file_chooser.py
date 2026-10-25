from pathlib import Path
from playwright.sync_api import sync_playwright

model_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
garment_img = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Found flow page!")
                # Click the Upload button directly via JS or file chooser
                with p.expect_file_chooser(timeout=10000) as fc_info:
                    p.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('button'));
                        for (const b of btns) {
                            if (b.innerText.includes('Tải lên') || b.innerText.includes('upload')) {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                file_chooser = fc_info.value
                print("Setting files to file chooser:", model_img.name, garment_img.name)
                file_chooser.set_files([str(model_img), str(garment_img)])
                print("Files set! Waiting 5s...")
                p.wait_for_timeout(5000)
                p.screenshot(path='out/flow_uploaded.png')
                print("Screenshot saved to out/flow_uploaded.png!")
                break

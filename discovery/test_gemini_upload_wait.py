import time
from pathlib import Path
from playwright.sync_api import sync_playwright

first_frame = Path("out/first_frame_perfect.png").resolve()

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                print("Gemini URL:", p.url)
                
                # Check upload menu
                add_btn = p.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button")
                if add_btn:
                    add_btn.click()
                    p.wait_for_timeout(500)
                
                inp = p.query_selector("input[type=file]")
                inp.set_input_files([str(first_frame)])
                print("Files passed to input[type=file]!")

                # Check preview chip status every 1s
                for i in range(10):
                    time.sleep(1)
                    chips = p.evaluate("""() => {
                        const previews = Array.from(document.querySelectorAll('uploader-file-preview, .file-preview-chip, gem-media-attachment'));
                        const spinners = Array.from(document.querySelectorAll('uploader-file-preview mat-progress-spinner, .file-preview-chip mat-progress-spinner'));
                        const imgs = previews.map(pr => pr.querySelector('img')?.src || '');
                        return { count: previews.length, spinners: spinners.length, imgs };
                    }""")
                    print(f"[{i}s] Chip status:", chips)
                    if chips['count'] > 0 and chips['spinners'] == 0:
                        print("File preview chip is READY!")
                        break
                
                p.screenshot(path='out/gemini_chip_uploaded_inspect.png')
                break

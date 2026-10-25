import time
from pathlib import Path
from playwright.sync_api import sync_playwright

prompt_text = Path("out/first_frame_prompt.txt").read_text(encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    flow_page = None
    for p in browser.contexts[0].pages:
        if 'flow.google.com' in p.url:
            flow_page = p
            break

    # We already have both chips in PM!
    print("Typing prompt text...")
    flow_page.keyboard.type(prompt_text, delay=2)
    flow_page.wait_for_timeout(1000)

    flow_page.screenshot(path="out/flow_stage2_perfect_composer.png")
    print("Saved out/flow_stage2_perfect_composer.png!")

    # Check generate button status
    btn_status = flow_page.evaluate("""() => {
        const btn = document.querySelector('button.generate-icon-button');
        return {
            disabled: btn ? (btn.disabled || btn.classList.contains('mat-mdc-button-disabled')) : null,
            ariaDisabled: btn ? btn.getAttribute('aria-disabled') : null
        };
    }""")
    print("Generate button status before click:", btn_status)

    # Initial image count
    init_imgs = flow_page.evaluate("""() => {
        return Array.from(document.querySelectorAll('img')).map(i => i.src).filter(s => s && s.includes('flow-content'));
    }""")
    print(f"Flow images before generate: {len(init_imgs)}")

    # Click generate
    flow_page.click("button.generate-icon-button", force=True)
    print("Generate button clicked!")
    flow_page.wait_for_timeout(3000)

    # Poll for completion
    t0 = time.time()
    new_src = ""
    while time.time() - t0 < 150:
        time.sleep(3)
        res = flow_page.evaluate("""(inits) => {
            const cur = Array.from(document.querySelectorAll('img')).map(i => i.src).filter(s => s && s.includes('flow-content'));
            const diff = cur.filter(s => !inits.includes(s));
            const isBusy = !!document.querySelector('mat-progress-spinner, mat-progress-bar, [class*="generating"]');
            return { isBusy, newCount: diff.length, newSrc: diff[0] || '' };
        }""", init_imgs)

        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, New images: {res['newCount']}")

        if res['newCount'] > 0 and not res['isBusy']:
            new_src = res['newSrc']
            print("Generation complete! New image:", new_src[:80])
            break

    flow_page.screenshot(path="out/flow_stage2_result.png")

    if new_src:
        import requests
        resp = requests.get(new_src, timeout=30)
        out_p = Path("out/first_frame_perfect.png")
        out_p.write_bytes(resp.content)
        print(f"Downloaded First Frame to {out_p} ({len(resp.content)} bytes)!")

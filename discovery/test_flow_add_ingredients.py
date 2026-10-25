from playwright.sync_api import sync_playwright

prompt_body = """A photorealistic, candid lifestyle fashion portrait of the exact young Korean woman from @main-model.jpg, perfectly trying on and wearing the complete outfit and posing in the exact scene from @1.jpg, vertical 3:4 aspect ratio. Visible skin micro-pores, authentic fabric weave texture, natural store ambient lighting."""

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'flow.google.com' in p.url:
                print("Found flow!")
                
                # Check if overlay is showing
                p.evaluate("""() => {
                    const btnModel = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('main-model.jpg'));
                    if (btnModel) btnModel.click();
                    const btnGarment = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('1.jpg'));
                    if (btnGarment) btnGarment.click();
                    const btnAdd = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Thêm vào câu lệnh'));
                    if (btnAdd) btnAdd.click();
                }""")
                p.wait_for_timeout(1000)

                # Focus textarea, clear, and type prompt
                textarea = p.query_selector('textarea')
                if textarea:
                    textarea.click(force=True)
                    # Don't delete the chips, just append prompt
                    p.keyboard.press("End")
                    p.keyboard.type(" " + prompt_body, delay=10)
                    p.wait_for_timeout(1000)

                    # Click Bắt đầu tạo
                    p.evaluate("""() => {
                        const genBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Bắt đầu tạo') || (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo'));
                        if (genBtn) genBtn.click();
                    }""")
                    print("Clicked Bắt đầu tạo!")
                    p.wait_for_timeout(4000)
                    p.screenshot(path='out/flow_after_generate_click.png')
                    print("Saved out/flow_after_generate_click.png!")
                break

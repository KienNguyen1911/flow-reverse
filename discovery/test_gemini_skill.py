from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    gemini_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                gemini_page = p
                break

    if not gemini_page:
        print("No gemini page")
        exit(1)

    print("Gemini URL:", gemini_page.url)

    # Focus editor
    editor = gemini_page.query_selector('div.ql-editor')
    if editor:
        editor.click()
        gemini_page.keyboard.press("Control+A")
        gemini_page.keyboard.press("Backspace")
        gemini_page.wait_for_timeout(300)

        # Type @try-on-prompt
        gemini_page.keyboard.type("@try-on-prompt", delay=30)
        gemini_page.wait_for_timeout(500)
        # Press Enter to select the skill from the dropdown
        gemini_page.keyboard.press("Enter")
        gemini_page.wait_for_timeout(500)

        # Now type the rest of the prompt: create image prompt
        gemini_page.keyboard.type(" create image prompt", delay=20)
        gemini_page.wait_for_timeout(500)

        gemini_page.screenshot(path='out/gemini_skill_typed.png')

        # Check what the editor HTML looks like
        editor_info = gemini_page.evaluate("""() => {
            const ed = document.querySelector('div.ql-editor');
            return {
                html: ed ? ed.innerHTML : '',
                text: ed ? ed.innerText : '',
                chips: Array.from(document.querySelectorAll('.mention, .chip, [class*="mention"]')).map(c => c.innerText)
            };
        }""")
        print("Editor info:", editor_info)

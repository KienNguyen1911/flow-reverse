from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            editor = p.query_selector("div.ql-editor, rich-textarea")
            editor.click()
            p.keyboard.press("Control+A")
            p.keyboard.press("Backspace")
            p.wait_for_timeout(300)
            
            print("Typing '@try-on'...")
            p.keyboard.type("@try-on", delay=50)
            p.wait_for_timeout(1000)
            p.screenshot(path="out/gemini_at_tryon_typed.png")
            
            # Look for the option with text 'try-on-prompter'
            clicked = p.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('*')).filter(e => 
                    e.childNodes.length === 1 && 
                    e.childNodes[0].nodeType === Node.TEXT_NODE && 
                    e.innerText.trim() === 'try-on-prompter'
                );
                if (els.length > 0) {
                    els[0].click();
                    return true;
                }
                return false;
            }""")
            print("Clicked try-on-prompter in dropdown:", clicked)
            p.wait_for_timeout(1000)
            p.screenshot(path="out/gemini_skill_clicked.png")
            
            # Check editor contents
            editor_html = p.evaluate("""() => {
                const ed = document.querySelector('div.ql-editor');
                return ed ? ed.innerHTML : 'no editor';
            }""")
            print("Editor HTML after click:", editor_html)
            break

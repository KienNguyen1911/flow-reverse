from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                info = p.evaluate("""() => {
                    const editor = document.querySelector('div.ql-editor');
                    const uq = Array.from(document.querySelectorAll('user-query')).map(u => u.innerText);
                    const fileChips = Array.from(document.querySelectorAll('uploader-file-preview, .file-preview-chip')).length;
                    return {
                        editorHtml: editor ? editor.innerHTML : '',
                        editorText: editor ? editor.innerText : '',
                        userQueries: uq,
                        fileChips
                    };
                }""")
                print("Editor & query state:", info)
                break

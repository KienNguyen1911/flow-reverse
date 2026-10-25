from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            nodes = p.evaluate("""() => {
                const queries = Array.from(document.querySelectorAll('user-query')).map(u => u.innerText);
                const responses = Array.from(document.querySelectorAll('model-response')).map(m => m.innerText);
                const pending = document.querySelectorAll('pending-response, mat-progress-spinner, thinking-dots-animation').length;
                return { queries, responses_count: responses.length, pending };
            }""")
            print("Conversation status:", nodes)

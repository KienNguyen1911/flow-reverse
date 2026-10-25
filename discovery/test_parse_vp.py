from src.Bridge.gemini_bridge import parse_gemini_video_prompts
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                text = p.evaluate("""() => {
                    const mrs = document.querySelectorAll('model-response');
                    return mrs.length > 0 ? mrs[mrs.length - 1].innerText : '';
                }""")
                p1, p2 = parse_gemini_video_prompts(text)
                print("=== PARSED VIDEO PROMPT 1 (first 200 chars) ===")
                print(p1[:200])
                print("=== PARSED VIDEO PROMPT 2 (first 200 chars) ===")
                print(p2[:200])
                break

from src.Bridge.gemini_bridge import parse_gemini_image_prompt

with open("out/gemini_response_sample.txt", "w", encoding="utf-8") as f:
    pass

import sys
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
                clean = parse_gemini_image_prompt(text)
                print("=== PARSED CLEAN IMAGE PROMPT ===")
                print(clean[:300])
                print("... Length:", len(clean))
                break

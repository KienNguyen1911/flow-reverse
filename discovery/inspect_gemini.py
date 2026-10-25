import json
import sys
from pathlib import Path
sys.path.insert(0, ".")
from playwright.sync_api import sync_playwright


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'gemini.google.com' in p.url:
                page = p
                break
        if page:
            break
    if not page:
        print('Gemini page not found!')
        exit(1)

    att = page.evaluate('() => document.querySelectorAll("uploader-file-preview, .file-preview-chip").length')
    print('Gemini current attachments in composer:', att)
    ed = page.evaluate('() => document.querySelector("div.ql-editor") ? document.querySelector("div.ql-editor").innerText : ""')
    print('Gemini current text in composer:', ed)























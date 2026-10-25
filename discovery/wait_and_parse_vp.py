import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:4023')
    target_page = None
    for p in browser.contexts[0].pages:
        if 'gemini.google.com' in p.url:
            target_page = p
            break

    print("Monitoring response #2 completion...")
    t0 = time.time()
    last_text = ""
    stable_count = 0
    full_text = ""

    while time.time() - t0 < 90:
        time.sleep(2)
        res = target_page.evaluate("""() => {
            const mrs = document.querySelectorAll('model-response');
            if (mrs.length < 2) return { ready: false, isBusy: true, text: '' };
            const second = mrs[1];
            const text = (second.innerText || '').trim();
            const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], mat-progress-spinner, pending-response');
            return { ready: !isBusy && text.length > 50, isBusy, text };
        }""")

        cur_text = res.get("text", "")
        print(f"[{time.time()-t0:.1f}s] Busy: {res['isBusy']}, Length: {len(cur_text)}")

        if res.get("ready"):
            if len(cur_text) == len(last_text) and not res["isBusy"]:
                stable_count += 1
                if stable_count >= 2:
                    print("Response #2 completed and stable!")
                    full_text = cur_text
                    break
            else:
                stable_count = 0
            last_text = cur_text

    if not full_text:
        full_text = last_text

    print("=== RAW RESPONSE #2 ===")
    print(full_text[:600])

    Path("out/step3_video_prompts_raw.txt").write_text(full_text, encoding="utf-8")
    
    # Parse with custom logic or regex
    # Pattern: Video 1 / Clip 1 ... Video 2 / Clip 2
    import re
    p1 = ""
    p2 = ""
    m1 = re.search(r"(?:video\s*(?:prompt\s*)?1\b|clip\s*1\b|đoạn\s*1\b)[^\n:]*[:\-–]?(.*?)(?=(?:video\s*(?:prompt\s*)?2\b|clip\s*2\b|đoạn\s*2\b|$))", full_text, re.DOTALL | re.IGNORECASE)
    m2 = re.search(r"(?:video\s*(?:prompt\s*)?2\b|clip\s*2\b|đoạn\s*2\b)[^\n:]*[:\-–]?(.*?)(?=(?:💡|lưu\s*ý|hướng\s*dẫn|note:|$))", full_text, re.DOTALL | re.IGNORECASE)
    
    if m1 and m2:
        p1 = m1.group(1).strip()
        p2 = m2.group(1).strip()
    else:
        # Fallback to codeblocks or paragraphs
        cbs = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", full_text, re.DOTALL)
        if len(cbs) >= 2:
            p1 = cbs[0].strip()
            p2 = cbs[1].strip()
        else:
            p1 = full_text[:len(full_text)//2].strip()
            p2 = full_text[len(full_text)//2:].strip()

    # Clean markdown formatting from chunks
    def clean_chunk(s: str) -> str:
        s = re.sub(r"```[a-zA-Z0-9_\-]*\n?", "", s)
        s = re.sub(r"^markdown\s*", "", s, flags=re.IGNORECASE)
        lines = [l.strip() for l in s.splitlines() if l.strip() and not l.strip().startswith("#")]
        return " ".join(lines).strip().strip('"').strip("'")

    p1 = clean_chunk(p1)
    p2 = clean_chunk(p2)

    print("\n=== CLEAN VIDEO PROMPT 1 ===")
    print(p1)
    print("\n=== CLEAN VIDEO PROMPT 2 ===")
    print(p2)

    Path("out/video_prompt_1.txt").write_text(p1, encoding="utf-8")
    Path("out/video_prompt_2.txt").write_text(p2, encoding="utf-8")

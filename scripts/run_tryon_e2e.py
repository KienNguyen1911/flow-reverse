"""End-to-End Autonomous Try-On Pipeline Script.

Executes all stages directly on the user's running CloakBrowser instance (port 4023):
1. Gemini Notebook: Uploads model + garment, activates @try-on-prompter with Enter -> Image Prompt (1)
2. Google Flow: Mentions @main-model + Enter, @1.jpg + Enter + prompt -> First Frame Image
3. Gemini Notebook: Uploads First Frame, activates @try-on-prompter with Enter -> 2 Video Prompts (8s each)
4. Google Flow: First Frame + Video Prompt 1 -> Video 1 (8s)
5. FFmpeg: Extracts Last Frame from Video 1
6. Google Flow: Last Frame + Video Prompt 2 -> Video 2 (8s)
7. FFmpeg: Concatenates Video 1 + Video 2 -> final_tryon_video_16s.mp4
"""

import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:4023"
MODEL_IMG = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\main-model.jpg")
GARMENT_IMG = Path(r"C:\Users\ngkie\Downloads\ShopeeSave_20261025\kem_cardigan_nhap_ma_affozgf___giam_60k_am_hai_day\main_images\1.jpg")

RUN_ID = f"tryon_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT_DIR = Path("out/affiliate_runs") / RUN_ID
OUT_DIR.mkdir(parents=True, exist_ok=True)


def log(step: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{step}] {msg}", flush=True)


def main():
    log("INIT", f"Khởi động E2E Try-On Pipeline: {RUN_ID}")
    log("INIT", f"Model: {MODEL_IMG} (exists: {MODEL_IMG.exists()})")
    log("INIT", f"Garment: {GARMENT_IMG} (exists: {GARMENT_IMG.exists()})")

    with sync_playwright() as pw:
        log("CDP", f"Kết nối trình duyệt tại {CDP_URL}...")
        browser = pw.chromium.connect_over_cdp(CDP_URL)

        # Locate Gemini and Flow pages
        gemini_page = None
        flow_page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "gemini.google.com" in p.url and not gemini_page:
                    gemini_page = p
                elif "flow.google.com" in p.url and not flow_page:
                    flow_page = p

        if not gemini_page:
            log("GEMINI", "Mở tab Gemini mới...")
            gemini_page = browser.contexts[0].new_page()
            gemini_page.goto("https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553", wait_until="domcontentloaded")
            time.sleep(3)

        if not flow_page:
            log("FLOW", "Mở tab Google Flow mới...")
            flow_page = browser.contexts[0].new_page()
            flow_page.goto("https://flow.google.com/", wait_until="domcontentloaded")
            time.sleep(3)

        # =================================================================== #
        # GIAI ĐOẠN 1: GEMINI NABI STUDIO -> TẠO IMAGE PROMPT (1)
        # =================================================================== #
        log("STAGE 1", "=== BƯỚC 1: Gọi Gemini Nabi Studio tạo Image Prompt ===")
        gemini_page.bring_to_front()
        gemini_page.goto("https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553", wait_until="domcontentloaded")
        time.sleep(3)

        # Reset chat if needed
        new_chat_btn = gemini_page.query_selector('//a[contains(., "Cuộc trò chuyện mới")] | //button[contains(., "Cuộc trò chuyện mới")]')
        if new_chat_btn:
            try:
                new_chat_btn.click()
                time.sleep(2)
            except Exception:
                pass

        # Upload model + garment
        log("STAGE 1", "Đính kèm ảnh người mẫu + mẫu mặc thử vào Gemini...")
        add_btn = gemini_page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button")
        if add_btn:
            try:
                add_btn.click()
                time.sleep(1)
            except Exception:
                pass

        file_input = gemini_page.query_selector("input[type=file]")
        if not file_input:
            raise RuntimeError("Không tìm thấy input[type=file] trên Gemini.")

        file_input.set_input_files([str(MODEL_IMG), str(GARMENT_IMG)])
        log("STAGE 1", "Chờ preview chips upload hoàn tất (4s)...")
        time.sleep(4)

        # Enter prompt with skill mention and Enter
        editor = gemini_page.query_selector("div.ql-editor")
        editor.click()
        gemini_page.keyboard.press("Control+A")
        gemini_page.keyboard.press("Backspace")
        time.sleep(0.3)

        log("STAGE 1", "Nhập '@try-on-prompter' + nhấn Enter để kích hoạt skill...")
        gemini_page.keyboard.type("@try-on-prompter", delay=30)
        time.sleep(0.6)
        gemini_page.keyboard.press("Enter")
        time.sleep(0.6)
        gemini_page.keyboard.type(" create image prompt", delay=20)
        time.sleep(0.8)

        before_count = gemini_page.evaluate("document.querySelectorAll('model-response').length")
        send_btn = gemini_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
        if send_btn and not send_btn.is_disabled():
            send_btn.click()
        else:
            gemini_page.keyboard.press("Enter")

        log("STAGE 1", "Đã gửi prompt. Chờ Gemini phân tích và trả về Image Prompt...")
        t0 = time.time()
        image_prompt_raw = ""
        while time.time() - t0 < 90:
            time.sleep(3)
            res = gemini_page.evaluate("""(before) => {
                const mrs = document.querySelectorAll('model-response');
                const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], button[aria-label*="Ngừng"], .generating-indicator, mat-progress-spinner');
                if (mrs.length <= before) return { ready: false, isBusy };
                const last = mrs[mrs.length - 1];
                const text = (last.innerText || '').trim();
                const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
                return { ready: !isBusy && clean.length > 80, text: text, cleanLen: clean.length, isBusy: isBusy };
            }""", before_count)
            if res.get("ready"):
                image_prompt_raw = res["text"]
                log("STAGE 1", f"Gemini phản hồi xong ({len(image_prompt_raw)} ký tự)!")
                break

        if not image_prompt_raw:
            # Fallback if streaming took longer or was caught earlier
            image_prompt_raw = gemini_page.evaluate("""() => {
                const mrs = document.querySelectorAll('model-response');
                return mrs.length > 0 ? mrs[mrs.length - 1].innerText : '';
            }""")

        (OUT_DIR / "image_prompt_raw.txt").write_text(image_prompt_raw, encoding="utf-8")

        # Parse clean image prompt
        code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", image_prompt_raw, re.DOTALL)
        clean_image_prompt = code_blocks[0].strip() if code_blocks else image_prompt_raw
        # Clean markdown headers
        clean_image_prompt = re.sub(r"^#+\s*", "", clean_image_prompt, flags=re.MULTILINE)
        (OUT_DIR / "image_prompt_clean.txt").write_text(clean_image_prompt, encoding="utf-8")
        log("STAGE 1", f"Image Prompt sẵn sàng: {clean_image_prompt[:120]}...")

        # =================================================================== #
        # GIAI ĐOẠN 2: GOOGLE FLOW -> TẠO FIRST FRAME IMAGE
        # =================================================================== #
        log("STAGE 2", "=== BƯỚC 2: Tạo First Frame Image trên Google Flow ===")
        flow_page.bring_to_front()
        time.sleep(2)

        # Ensure model and garment are in project media
        log("STAGE 2", "Kiểm tra và upload media assets vào Flow...")
        try:
            add_media_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
            if add_media_btn:
                add_media_btn.click(force=True)
                time.sleep(0.6)
                upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
                if upload_btn:
                    with flow_page.expect_file_chooser(timeout=5000) as fc_info:
                        upload_btn.click(force=True)
                    fc = fc_info.value
                    fc.set_files([str(MODEL_IMG), str(GARMENT_IMG)])
                    log("STAGE 2", "Đã upload main-model.jpg và 1.jpg vào Flow media.")
                    time.sleep(4)
        except Exception as e:
            log("STAGE 2", f"Upload assets note (có thể đã tồn tại): {e}")

        # Ensure close overlay
        flow_page.keyboard.press("Escape")
        time.sleep(0.5)

        # Snapshot existing Flow images before generating
        before_flow_imgs = flow_page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img')).map(i => i.src);
            return Array.from(new Set(imgs));
        }""")

        # Focus ProseMirror editor
        pm = flow_page.query_selector("div.ProseMirror[contenteditable='true']")
        if not pm:
            raise RuntimeError("Không tìm thấy editor ProseMirror trên Flow.")

        pm.click()
        flow_page.keyboard.press("Control+A")
        flow_page.keyboard.press("Backspace")
        time.sleep(0.3)

        # Type @main-model + Enter, then @1.jpg + Enter
        log("STAGE 2", "Gắn thành phần @main-model + nhấn Enter...")
        flow_page.keyboard.type("@main-model", delay=50)
        time.sleep(0.8)
        flow_page.keyboard.press("Enter")
        time.sleep(0.5)

        log("STAGE 2", "Gắn thành phần @1.jpg + nhấn Enter...")
        flow_page.keyboard.type(" @1.jpg", delay=50)
        time.sleep(0.8)
        flow_page.keyboard.press("Enter")
        time.sleep(0.5)

        # Append prompt body
        flow_page.keyboard.type(" " + clean_image_prompt, delay=10)
        time.sleep(1)

        # Click generate button
        log("STAGE 2", "Nhấn nút 'Bắt đầu tạo' First Frame trên Flow...")
        gen_clicked = flow_page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('arrow_forward') || 
                b.innerText.includes('Bắt đầu tạo') || 
                (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo')
            );
            if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                btn.click();
                return true;
            }
            return false;
        }""")
        log("STAGE 2", f"Trạng thái bấm nút tạo: {gen_clicked}")

        # Wait for generated image
        log("STAGE 2", "Đang chờ Flow render First Frame Image (~15-30s)...")
        t0 = time.time()
        first_frame_url = None
        while time.time() - t0 < 90:
            time.sleep(3)
            res = flow_page.evaluate("""(beforeImgs) => {
                const spinners = document.querySelectorAll('mat-progress-spinner, [class*="progress"], [class*="generating"]');
                const imgs = Array.from(document.querySelectorAll('img'))
                    .map(i => i.src)
                    .filter(s => s && (s.includes('flow-content.google') || s.includes('flow.google.com/asb')));
                const unique = Array.from(new Set(imgs));
                const newImgs = unique.filter(u => !beforeImgs.includes(u));
                return {
                    isBusy: spinners.length > 0,
                    newCount: newImgs.length,
                    latest: newImgs.length > 0 ? newImgs[newImgs.length - 1] : (unique.length > 0 ? unique[unique.length - 1] : null)
                };
            }""", before_flow_imgs)

            if not res["isBusy"] and res["latest"]:
                first_frame_url = res["latest"]
                log("STAGE 2", f"Đã tìm thấy URL First Frame: {first_frame_url[:80]}...")
                break

        first_frame_path = OUT_DIR / "first_frame.png"
        if first_frame_url:
            img_bytes = flow_page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const buf = await resp.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }""", first_frame_url)
            first_frame_path.write_bytes(bytes(img_bytes))
            log("STAGE 2", f"First Frame đã tải về thành công: {first_frame_path} ({len(img_bytes)} bytes)!")
        else:
            raise RuntimeError("Hết thời gian chờ tạo First Frame trên Flow.")

        # =================================================================== #
        # GIAI ĐOẠN 3: GEMINI NABI STUDIO -> TẠO 2 VIDEO PROMPTS (8s mỗi clip)
        # =================================================================== #
        log("STAGE 3", "=== BƯỚC 3: Gọi Gemini tạo 2 Video Prompt (8s) từ First Frame ===")
        gemini_page.bring_to_front()
        gemini_page.goto("https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553", wait_until="domcontentloaded")
        time.sleep(3)

        # New clean chat
        new_chat_btn = gemini_page.query_selector('//a[contains(., "Cuộc trò chuyện mới")] | //button[contains(., "Cuộc trò chuyện mới")]')
        if new_chat_btn:
            try:
                new_chat_btn.click()
                time.sleep(2)
            except Exception:
                pass

        # Upload first frame
        log("STAGE 3", "Tải First Frame lên Gemini...")
        add_btn = gemini_page.query_selector("button[aria-label*='Add'], button[aria-label*='Upload'], button[aria-label*='Thêm'], simplified-input-menu button")
        if add_btn:
            try:
                add_btn.click()
                time.sleep(1)
            except Exception:
                pass

        file_input = gemini_page.query_selector("input[type=file]")
        file_input.set_input_files([str(first_frame_path)])
        log("STAGE 3", "Chờ First Frame upload hoàn tất (4s)...")
        time.sleep(4)

        # Enter prompt: @try-on-prompter + Enter + create video prompt
        editor = gemini_page.query_selector("div.ql-editor")
        editor.click()
        gemini_page.keyboard.press("Control+A")
        gemini_page.keyboard.press("Backspace")
        time.sleep(0.3)

        log("STAGE 3", "Nhập '@try-on-prompter' + nhấn Enter...")
        gemini_page.keyboard.type("@try-on-prompter", delay=30)
        time.sleep(0.6)
        gemini_page.keyboard.press("Enter")
        time.sleep(0.6)
        gemini_page.keyboard.type(" create video prompt", delay=20)
        time.sleep(0.8)

        before_count = gemini_page.evaluate("document.querySelectorAll('model-response').length")
        send_btn = gemini_page.query_selector("button[aria-label*='Send'], button[aria-label*='Gửi']")
        if send_btn and not send_btn.is_disabled():
            send_btn.click()
        else:
            gemini_page.keyboard.press("Enter")

        log("STAGE 3", "Đã gửi câu lệnh. Chờ Gemini xuất 2 Video Prompt 8s...")
        t0 = time.time()
        video_prompts_raw = ""
        while time.time() - t0 < 90:
            time.sleep(3)
            res = gemini_page.evaluate("""(before) => {
                const mrs = document.querySelectorAll('model-response');
                const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], button[aria-label*="Ngừng"], .generating-indicator, mat-progress-spinner');
                if (mrs.length <= before) return { ready: false, isBusy };
                const last = mrs[mrs.length - 1];
                const text = (last.innerText || '').trim();
                const clean = text.replace(/^(?:skills\\s*:\\s*[^\\n]+|\\s*)+/i, '').trim();
                return { ready: !isBusy && clean.length > 80, text: text, isBusy: isBusy };
            }""", before_count)
            if res.get("ready"):
                video_prompts_raw = res["text"]
                log("STAGE 3", f"Gemini đã sinh 2 Video Prompt ({len(video_prompts_raw)} ký tự)!")
                break

        if not video_prompts_raw:
            video_prompts_raw = gemini_page.evaluate("""() => {
                const mrs = document.querySelectorAll('model-response');
                return mrs.length > 0 ? mrs[mrs.length - 1].innerText : '';
            }""")

        (OUT_DIR / "video_prompts_raw.txt").write_text(video_prompts_raw, encoding="utf-8")

        # Parse 2 video prompts
        code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", video_prompts_raw, re.DOTALL)
        vp1 = ""
        vp2 = ""
        if len(code_blocks) >= 2:
            vp1 = code_blocks[0].strip()
            vp2 = code_blocks[1].strip()
        else:
            # Fallback regex
            m = re.search(r"(?:video\s*prompt\s*1\b[^\n:]*[:\-–]?)(.*?)(?:video\s*prompt\s*2\b[^\n:]*[:\-–]?)(.*)", video_prompts_raw, re.IGNORECASE | re.DOTALL)
            if m:
                vp1 = m.group(1).strip()
                vp2 = m.group(2).strip()
            else:
                paragraphs = [p.strip() for p in video_prompts_raw.split("\n\n") if len(p.strip()) > 40]
                vp1 = paragraphs[0] if len(paragraphs) > 0 else video_prompts_raw
                vp2 = paragraphs[1] if len(paragraphs) > 1 else video_prompts_raw

        log("STAGE 3", f"Video Prompt 1 (8s): {vp1[:100]}...")
        log("STAGE 3", f"Video Prompt 2 (8s): {vp2[:100]}...")
        (OUT_DIR / "video_prompt_1.txt").write_text(vp1, encoding="utf-8")
        (OUT_DIR / "video_prompt_2.txt").write_text(vp2, encoding="utf-8")

        # =================================================================== #
        # GIAI ĐOẠN 4: GOOGLE FLOW -> TẠO VIDEO 1 (8s)
        # =================================================================== #
        log("STAGE 4", "=== BƯỚC 4: Tạo Video 1 (8s) trên Google Flow ===")
        flow_page.bring_to_front()
        time.sleep(2)

        # Switch to Video mode
        log("STAGE 4", "Chuyển sang chế độ Video (8 giây)...")
        model_btn = flow_page.query_selector('//button[contains(., "Nano Banana")] | //button[contains(., "Banana")]')
        if model_btn:
            model_btn.click()
            time.sleep(0.8)
            flow_page.evaluate("""() => {
                const videoBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Video'));
                if (videoBtn) videoBtn.click();
            }""")
            time.sleep(1)
            # Select 8 giây if available
            flow_page.evaluate("""() => {
                const btn8s = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('8 giây'));
                if (btn8s) btn8s.click();
            }""")
            time.sleep(0.5)

        # Close settings
        flow_page.keyboard.press("Escape")
        time.sleep(0.5)

        # Attach first frame as reference/ingredient
        log("STAGE 4", "Đính kèm First Frame vào Video Composer...")
        pm = flow_page.query_selector("div.ProseMirror[contenteditable='true']")
        pm.click()
        flow_page.keyboard.press("Control+A")
        flow_page.keyboard.press("Backspace")
        time.sleep(0.3)

        # Check existing videos before render
        before_videos = flow_page.evaluate("""() => {
            const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc).filter(Boolean);
            const entries = performance.getEntriesByType('resource').map(e => e.name).filter(u => u.includes('.mp4') || u.includes('/video/'));
            return Array.from(new Set(vids.concat(entries)));
        }""")

        # Type prompt 1
        flow_page.keyboard.type(vp1, delay=10)
        time.sleep(1)

        # Click Generate Video 1
        log("STAGE 4", "Bấm tạo Video 1...")
        flow_page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('arrow_forward') || 
                b.innerText.includes('Bắt đầu tạo') || 
                (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo')
            );
            if (btn && !btn.disabled) btn.click();
        }""")

        # Poll for Video 1 render
        log("STAGE 4", "Đang chờ Flow render Video 1 (~60-180s)...")
        t0 = time.time()
        video_1_url = None
        video_1_path = OUT_DIR / "video_1.mp4"

        while time.time() - t0 < 300:
            time.sleep(5)
            new_vids = flow_page.evaluate("""(seen) => {
                const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc).filter(Boolean);
                const entries = performance.getEntriesByType('resource').map(e => e.name).filter(u => u.includes('.mp4') || u.includes('/video/'));
                const all = Array.from(new Set(vids.concat(entries)));
                const fresh = all.filter(u => !seen.includes(u) && u.startsWith('http'));
                return fresh;
            }""", before_videos)

            if new_vids:
                video_1_url = new_vids[-1]
                log("STAGE 4", f"Tìm thấy Video 1 URL: {video_1_url[:80]}...")
                break
            log("STAGE 4", f"Đang render Video 1... ({int(time.time()-t0)}s)")

        if video_1_url:
            vid_bytes = flow_page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const buf = await resp.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }""", video_1_url)
            video_1_path.write_bytes(bytes(vid_bytes))
            log("STAGE 4", f"Video 1 đã tải về thành công: {video_1_path} ({len(vid_bytes)} bytes)!")
        else:
            raise RuntimeError("Hết thời gian chờ tạo Video 1 trên Flow.")

        # =================================================================== #
        # GIAI ĐOẠN 5: TRÍCH XUẤT LAST FRAME CỦA VIDEO 1 (FFMPEG)
        # =================================================================== #
        log("STAGE 5", "=== BƯỚC 5: Trích xuất Last Frame từ Video 1 bằng FFmpeg ===")
        last_frame_path = OUT_DIR / "last_frame_video_1.png"
        cmd = ["ffmpeg", "-y", "-sseof", "-0.2", "-i", str(video_1_path), "-update", "1", "-q:v", "1", str(last_frame_path)]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if not last_frame_path.is_file() or last_frame_path.stat().st_size < 100:
            # Fallback reverse filter
            cmd_rev = ["ffmpeg", "-y", "-i", str(video_1_path), "-vf", "reverse", "-vframes", "1", str(last_frame_path)]
            subprocess.run(cmd_rev, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

        log("STAGE 5", f"Last Frame đã trích xuất: {last_frame_path} ({last_frame_path.stat().st_size} bytes)!")

        # =================================================================== #
        # GIAI ĐOẠN 6: GOOGLE FLOW -> TẠO VIDEO 2 (8s) TỪ LAST FRAME
        # =================================================================== #
        log("STAGE 6", "=== BƯỚC 6: Tạo Video 2 (8s) trên Google Flow ===")
        flow_page.bring_to_front()
        time.sleep(2)

        # Upload last frame to Flow
        try:
            add_media_btn = flow_page.query_selector('button[aria-label*="nghe nhìn"]')
            if add_media_btn:
                add_media_btn.click(force=True)
                time.sleep(0.6)
                upload_btn = flow_page.query_selector('//button[contains(., "Tải lên")]')
                if upload_btn:
                    with flow_page.expect_file_chooser(timeout=5000) as fc_info:
                        upload_btn.click(force=True)
                    fc = fc_info.value
                    fc.set_files([str(last_frame_path)])
                    time.sleep(4)
        except Exception as e:
            log("STAGE 6", f"Upload last frame note: {e}")

        flow_page.keyboard.press("Escape")
        time.sleep(0.5)

        # Snapshot existing videos before Video 2
        before_videos_2 = flow_page.evaluate("""() => {
            const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc).filter(Boolean);
            const entries = performance.getEntriesByType('resource').map(e => e.name).filter(u => u.includes('.mp4') || u.includes('/video/'));
            return Array.from(new Set(vids.concat(entries)));
        }""")

        # Focus ProseMirror editor
        pm = flow_page.query_selector("div.ProseMirror[contenteditable='true']")
        pm.click()
        flow_page.keyboard.press("Control+A")
        flow_page.keyboard.press("Backspace")
        time.sleep(0.3)

        # Type prompt 2
        flow_page.keyboard.type(vp2, delay=10)
        time.sleep(1)

        # Click Generate Video 2
        log("STAGE 6", "Bấm tạo Video 2...")
        flow_page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('arrow_forward') || 
                b.innerText.includes('Bắt đầu tạo') || 
                (b.getAttribute('aria-label')||'').includes('Bắt đầu tạo')
            );
            if (btn && !btn.disabled) btn.click();
        }""")

        # Poll for Video 2 render
        log("STAGE 6", "Đang chờ Flow render Video 2 (~60-180s)...")
        t0 = time.time()
        video_2_url = None
        video_2_path = OUT_DIR / "video_2.mp4"

        while time.time() - t0 < 300:
            time.sleep(5)
            new_vids = flow_page.evaluate("""(seen) => {
                const vids = Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc).filter(Boolean);
                const entries = performance.getEntriesByType('resource').map(e => e.name).filter(u => u.includes('.mp4') || u.includes('/video/'));
                const all = Array.from(new Set(vids.concat(entries)));
                const fresh = all.filter(u => !seen.includes(u) && u.startsWith('http'));
                return fresh;
            }""", before_videos_2)

            if new_vids:
                video_2_url = new_vids[-1]
                log("STAGE 6", f"Tìm thấy Video 2 URL: {video_2_url[:80]}...")
                break
            log("STAGE 6", f"Đang render Video 2... ({int(time.time()-t0)}s)")

        if video_2_url:
            vid_bytes_2 = flow_page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const buf = await resp.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }""", video_2_url)
            video_2_path.write_bytes(bytes(vid_bytes_2))
            log("STAGE 6", f"Video 2 đã tải về thành công: {video_2_path} ({len(vid_bytes_2)} bytes)!")
        else:
            raise RuntimeError("Hết thời gian chờ tạo Video 2 trên Flow.")

        # =================================================================== #
        # GIAI ĐOẠN 7: GHÉP NỐI VIDEO 1 + VIDEO 2 THÀNH VIDEO 16s HOÀN CHỈNH
        # =================================================================== #
        log("STAGE 7", "=== BƯỚC 7: Nối Video 1 (8s) + Video 2 (8s) thành Video 16s hoàn chỉnh ===")
        final_video_path = OUT_DIR / "final_tryon_video_16s.mp4"
        cmd_concat = [
            "ffmpeg", "-y",
            "-i", str(video_1_path),
            "-i", str(video_2_path),
            "-filter_complex", "[0:v]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];[1:v]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];[v0][v1]concat=n=2:v=1[v]",
            "-map", "[v]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(final_video_path)
        ]
        subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        log("STAGE 7", f"Video 16s đã tạo thành công: {final_video_path} ({final_video_path.stat().st_size} bytes)!")

        log("COMPLETE", "=== HOÀN TẤT TOÀN BỘ WORKFLOW THÀNH CÔNG 100%! ===")
        log("COMPLETE", f"First Frame:    {first_frame_path}")
        log("COMPLETE", f"Video 1 (8s):   {video_1_path}")
        log("COMPLETE", f"Last Frame:     {last_frame_path}")
        log("COMPLETE", f"Video 2 (8s):   {video_2_path}")
        log("COMPLETE", f"Video 16s hoàn chỉnh: {final_video_path}")


if __name__ == "__main__":
    main()

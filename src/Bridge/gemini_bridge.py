"""Gemini Notebook Bridge — CDP automation for Nabi Studio (@try-on-prompter).

Automates https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553:
1. Uploads Nabi model image + try-on garment image.
2. Prompts: "@try-on-prompter create image prompt" -> parses Image Prompt (1).
3. Uploads First Frame image.
4. Prompts: "@try-on-prompter create video prompt" -> parses Video Prompt 1 & Video Prompt 2 (8s each).

Pure parsing functions are isolated and thoroughly tested.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import CDPSession, Page, sync_playwright

DEFAULT_CDP_URL = "http://127.0.0.1:4022"
NABI_NOTEBOOK_URL = "https://gemini.google.com/notebook/7fc78691-ccce-46a9-9f51-4e200aa63553"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

LogFn = Callable[[str, str], None]


# --------------------------------------------------------------------------- #
# Pure Response Parsers (Deterministic & Testable)
# --------------------------------------------------------------------------- #


def parse_gemini_image_prompt(raw_text: str) -> str:
    """Extract the clean image generation prompt from Gemini's response.

    Handles:
    - Codeblocks: ```...```
    - Quotations: "..."
    - Prefixes: 'Image Prompt:', 'Prompt (1):', 'Prompt:'
    - Markdown bolding: **Prompt:** ...
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text.strip()

    # 1. Look for fenced codeblock
    code_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_blocks:
        candidate = code_blocks[0].strip()
        if len(candidate) > 20:
            return candidate

    # 2. Look for labelled lines like "Prompt:", "Image Prompt:", "Prompt (1):"
    label_match = re.search(
        r"(?:(?:image\s+)?prompt(?:\s*\([0-9]+\))?|prompt\s*1)\s*[:\-–]\s*([^\n\r]+(?:\n(?!\n|\*|#).*)*)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        candidate = label_match.group(1).strip().strip('"').strip("'").strip("`")
        if len(candidate) > 20:
            return candidate

    # 3. Look for quoted paragraph
    quoted = re.findall(r'"([^"]{30,})"', text, re.DOTALL)
    if quoted:
        return quoted[0].strip()

    # 4. Fallback: filter out conversational intro/outro lines
    lines = text.splitlines()
    filtered = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Skip conversational openings
        if re.match(
            r"^(?:sure|here|certainly|dưới đây|đây là|tôi đã|chào|hello|hi\b|okay|ok\b)",
            s,
            re.IGNORECASE,
        ):
            continue
        # Skip conversational closings
        if re.match(
            r"^(?:hope|let me know|bạn có thể|chúc bạn|hãy cho tôi biết)",
            s,
            re.IGNORECASE,
        ):
            continue
        filtered.append(s)

    candidate = "\n".join(filtered).strip().strip('"').strip("'")
    return candidate or text


def parse_gemini_video_prompts(raw_text: str) -> tuple[str, str]:
    """Extract two video prompts (8s each) from Gemini's response.

    Returns:
        (video_prompt_1, video_prompt_2)
    """
    if not raw_text or not raw_text.strip():
        return "", ""

    text = raw_text.strip()

    # Pattern A: Segmented by headers like "Video 1", "Video 2", "Prompt 1", "Prompt 2"
    pattern = re.compile(
        r"(?:(?:video|clip|prompt|scene|đoạn)\s*(?:prompt\s*)?(?:#|số\s*)?1\b[^\n:]*[:\-–]?)"
        r"(.*?)"
        r"(?:(?:video|clip|prompt|scene|đoạn)\s*(?:prompt\s*)?(?:#|số\s*)?2\b[^\n:]*[:\-–]?)"
        r"(.*)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(text)
    if m:
        p1 = _clean_prompt_chunk(m.group(1))
        p2 = _clean_prompt_chunk(m.group(2))
        if p1 and p2:
            return p1, p2

    # Pattern B: Numbered list items: "1. ..." and "2. ..."
    pattern_num = re.compile(
        r"(?:^|\n)\s*1[\.\)]\s*(.*?)(?=(?:^|\n)\s*2[\.\)]\s*)"
        r"(?:^|\n)\s*2[\.\)]\s*(.*)",
        re.DOTALL,
    )
    m2 = pattern_num.search(text)
    if m2:
        p1 = _clean_prompt_chunk(m2.group(1))
        p2 = _clean_prompt_chunk(m2.group(2))
        if p1 and p2:
            return p1, p2

    # Pattern C: Codeblocks (e.g. 2 codeblocks)
    blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if len(blocks) >= 2:
        return _clean_prompt_chunk(blocks[0]), _clean_prompt_chunk(blocks[1])

    # Pattern D: Fallback - split by double newlines into two halves
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    if len(paragraphs) >= 2:
        return _clean_prompt_chunk(paragraphs[0]), _clean_prompt_chunk(paragraphs[1])

    # Default fallback
    clean = _clean_prompt_chunk(text)
    return clean, clean


def _clean_prompt_chunk(chunk: str) -> str:
    """Helper to remove formatting marks and timestamps from extracted prompt chunk."""
    s = chunk.strip()
    # Strip markdown headers, bold, italics, codeblock tags
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*|\*|`", "", s)
    # Strip leading timestamps like [0-8s], (0-8s), 8 seconds:
    s = re.sub(r"^\s*[\(\[]?[0-8\s\-sS]+[\)\]]?\s*[:\-–]?\s*", "", s)
    # Strip conversational sign-offs at the end without truncating valid prompt paragraphs
    lines = s.splitlines()
    filtered_lines = []
    for line in lines:
        line_s = line.strip()
        if re.match(r"^(?:hope this helps|let me know|chúc bạn|lưu ý\b|note\b|tùy chọn\b|bạn có thể)", line_s, re.IGNORECASE):
            break
        filtered_lines.append(line)
    s = "\n".join(filtered_lines).strip()
    return s.strip('"').strip("'")


# --------------------------------------------------------------------------- #
# GeminiNotebookBridge (Playwright / CDP)
# --------------------------------------------------------------------------- #


class GeminiBridgeError(RuntimeError):
    """Base error for Gemini bridge failures."""


class GeminiNotebookBridge:
    """Drives the Gemini Nabi Studio notebook tab over Playwright CDP."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        notebook_url: str = NABI_NOTEBOOK_URL,
        log: Optional[LogFn] = None,
        timeout_s: float = 60.0,
    ):
        self.cdp_url = cdp_url
        self.notebook_url = notebook_url
        self._log = log or (lambda kind, msg: None)
        self.timeout_s = timeout_s

        self._pw = None
        self.browser = None
        self.page: Optional[Page] = None
        self._cdp: Optional[CDPSession] = None

    def __enter__(self) -> "GeminiNotebookBridge":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> "GeminiNotebookBridge":
        """Connect over CDP to CloakBrowser and locate/open the Gemini tab."""
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        except Exception as e:
            self._stop_pw()
            raise GeminiBridgeError(
                f"Không thể kết nối CDP tại {self.cdp_url}. Trình duyệt đã mở chưa? ({e})"
            ) from e

        # Find existing tab or navigate to notebook
        target_page = None
        for ctx in self.browser.contexts:
            for p in ctx.pages:
                if "gemini.google.com" in p.url:
                    target_page = p
                    break
            if target_page:
                break

        if target_page is None:
            ctx = self.browser.contexts[0] if self.browser.contexts else None
            if not ctx:
                raise GeminiBridgeError("Trình duyệt không có context nào.")
            target_page = ctx.new_page()
            self._log("step", f"Điều hướng tới Gemini notebook: {self.notebook_url}")
            target_page.goto(self.notebook_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4.0)
        else:
            if self.notebook_url not in target_page.url:
                self._log("step", f"Mở notebook: {self.notebook_url}")
                target_page.goto(self.notebook_url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3.0)

        self.page = target_page
        self.page.bring_to_front()
        self._log("info", f"Đã kết nối Gemini tab: {self.page.url}")
        return self

    def close(self) -> None:
        """Disconnect CDP cleanly without closing the browser process."""
        self._stop_pw()

    def _stop_pw(self) -> None:
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def upload_files(self, file_paths: list[Path]) -> None:
        """Upload one or more files to the Gemini prompt input via input[type=file]."""
        for p in file_paths:
            if not p.is_file():
                raise FileNotFoundError(f"Không tìm thấy file để upload: {p}")

        self._log("step", f"Đính kèm {len(file_paths)} ảnh vào Gemini...")
        file_inputs = self.page.query_selector_all("input[type=file]")
        if not file_inputs:
            add_btn = self.page.query_selector(
                "button[aria-label*='Add'], button[aria-label*='Upload'], "
                "button[aria-label*='Thêm'], button[mattooltip*='Upload']"
            )
            if add_btn:
                try:
                    add_btn.click()
                    time.sleep(1.0)
                    file_inputs = self.page.query_selector_all("input[type=file]")
                except Exception:
                    pass

        if not file_inputs:
            raise GeminiBridgeError("Không tìm thấy input[type=file] trên giao diện Gemini.")

        # Find best matching input (prefer image accept)
        file_input = file_inputs[0]
        for inp in file_inputs:
            acc = inp.get_attribute("accept") or ""
            if "image" in acc.lower() or "*" in acc:
                file_input = inp
                break

        file_input.set_input_files([str(p.resolve()) for p in file_paths])
        self._log("info", f"Đã upload {len(file_paths)} file: {[p.name for p in file_paths]}")
        time.sleep(3.0)

    def send_prompt(self, prompt_text: str, wait_timeout_s: float = 60.0) -> str:
        """Type prompt into Gemini editor, send it, and wait for generation to complete."""
        self._log("step", f"Nhập prompt: '{prompt_text}'")

        # Focus editor
        editor_selectors = [
            "div.ql-editor",
            "rich-textarea",
            "div[contenteditable='true']",
            "textarea.text-input-field",
            "textarea",
        ]
        editor = None
        for sel in editor_selectors:
            editor = self.page.query_selector(sel)
            if editor:
                break

        if not editor:
            raise GeminiBridgeError("Không tìm thấy ô nhập prompt trên Gemini.")

        editor.click()
        time.sleep(0.5)

        # Handle @ mention if present
        if prompt_text.startswith("@"):
            parts = prompt_text.split(" ", 1)
            mention_tag = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            self.page.keyboard.type(mention_tag, delay=20)
            time.sleep(0.8)
            # Dismiss or select autocomplete mention popup if visible
            self.page.keyboard.press("Tab")
            time.sleep(0.3)
            self.page.keyboard.type(" " + rest, delay=15)
        else:
            self.page.keyboard.type(prompt_text, delay=15)
        time.sleep(1.0)

        # Count existing message nodes before send to avoid returning old responses
        before_count = self.page.evaluate(
            "document.querySelectorAll('message-content, .model-response-text, .response-container-content').length"
        )

        # Press Enter or click Send button
        send_btn = self.page.query_selector(
            "button[aria-label*='Send'], button[aria-label*='Gửi'], button.send-button"
        )
        if send_btn and not send_btn.is_disabled():
            send_btn.click()
        else:
            self.page.keyboard.press("Enter")

        self._log("info", "Đã gửi câu lệnh. Đang chờ Gemini phản hồi...")

        # Wait for response streaming to finish
        t0 = time.time()
        deadline = t0 + wait_timeout_s
        last_text = ""
        stable_count = 0

        while time.time() < deadline:
            time.sleep(1.5)
            # Fetch latest response text only if a new message has been added
            state = self.page.evaluate(
                """(expectedMin) => {
                    const nodes = document.querySelectorAll('message-content, .model-response-text, .response-container-content');
                    const isBusy = !!document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], .generating-indicator, mat-progress-spinner');
                    if (nodes.length <= expectedMin) {
                        return {ready: false, text: '', count: nodes.length, busy: isBusy};
                    }
                    const text = nodes[nodes.length - 1].innerText || '';
                    return {ready: true, text: text, count: nodes.length, busy: isBusy};
                }""",
                before_count,
            )

            if state and state.get("ready"):
                latest_text = state.get("text", "").strip()
                is_busy = state.get("busy", False)
                if latest_text:
                    if len(latest_text) == len(last_text) and len(latest_text) > 20 and not is_busy:
                        stable_count += 1
                        if stable_count >= 2:  # stable across 2 polls (~3s)
                            self._log("info", f"Gemini phản hồi xong ({len(latest_text)} ký tự).")
                            return latest_text
                    else:
                        stable_count = 0
                    last_text = latest_text

        if last_text:
            return last_text
        raise GeminiBridgeError(f"Hết thời gian chờ Gemini ({wait_timeout_s}s).")

    def generate_image_prompt(
        self,
        model_image: Path,
        garment_image: Path,
        extra_images: Optional[list[Path]] = None,
    ) -> str:
        """Upload Nabi + Garment (and optional extra product images), prompt '@try-on-prompter create image prompt' -> return clean prompt."""
        files = [model_image, garment_image]
        if extra_images:
            for extra in extra_images:
                p = Path(extra).resolve()
                if p.is_file() and p not in files:
                    files.append(p)
        self.upload_files(files)
        raw = self.send_prompt("@try-on-prompter create image prompt")
        clean_prompt = parse_gemini_image_prompt(raw)
        self._log("info", f"Prompt ảnh trích xuất: {clean_prompt[:120]}...")
        return clean_prompt

    def generate_video_prompts(self, first_frame_image: Path) -> tuple[str, str]:
        """Upload First Frame, prompt '@try-on-prompter create video prompt' -> return (prompt_1, prompt_2)."""
        self.upload_files([first_frame_image])
        raw = self.send_prompt("@try-on-prompter create video prompt")
        p1, p2 = parse_gemini_video_prompts(raw)
        self._log("info", f"Video Prompt 1 (8s): {p1[:100]}...")
        self._log("info", f"Video Prompt 2 (8s): {p2[:100]}...")
        return p1, p2

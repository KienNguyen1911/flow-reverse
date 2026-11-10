"""Gemini Notebook response parsers (@try-on-prompter outputs).

Pure, dependency-free text parsing — the CDP automation that drove the Gemini
notebook tab was removed along with the try-on pipeline; only the parsers stayed
because ``tests/test_prompt_skills_contract.py`` uses them to prove that prompts
written by ``prompt-skills/`` survive sanitising.
"""

from __future__ import annotations

import re


# --------------------------------------------------------------------------- #
# Pure Response Parsers (Deterministic & Testable)
# --------------------------------------------------------------------------- #


def parse_gemini_image_prompt(raw_text: str) -> str:
    """Extract the clean image generation prompt from Gemini's response.

    Handles:
    - Codeblocks: ```...```
    - Segmented options: 'Bản 2:', 'Bản 1:', 'Option 2:', 'Option 1:'
    - Labelled lines: 'Image Prompt:', 'Prompt (1):', 'Prompt:'
    - Quotations: "..."
    - Strips markdown annotations and conversational wrap-arounds.
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

    # 2. Look for Vietnamese/English dual prompt versions: Bản 2 (prefer detailed) or Bản 1
    m_ban2 = re.search(
        r"(?:bản\s*2|option\s*2|phiên\s*bản\s*2)[^\n:]*[:\-–]?(.*?)(?=(?:💡|hướng\s*dẫn|lưu\s*ý|note:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_ban2:
        chunk = m_ban2.group(1).strip()
        chunk = re.sub(r"^[^\n]*\n(?:markdown\s*\n)?", "", chunk, flags=re.IGNORECASE).strip()
        if len(chunk) > 30:
            return chunk

    m_ban1 = re.search(
        r"(?:bản\s*1|option\s*1|phiên\s*bản\s*1)[^\n:]*[:\-–]?(.*?)(?=(?:bản\s*2|option\s*2|💡|hướng\s*dẫn|lưu\s*ý|note:|$))",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_ban1:
        chunk = m_ban1.group(1).strip()
        chunk = re.sub(r"^[^\n]*\n(?:markdown\s*\n)?", "", chunk, flags=re.IGNORECASE).strip()
        if len(chunk) > 30:
            return chunk

    # 3. Look for labelled lines like "Prompt:", "Image Prompt:", "Prompt (1):"
    label_match = re.search(
        r"(?:(?:image\s+)?prompt(?:\s*\([0-9]+\))?|prompt\s*1)\s*[:\-–]\s*([^\n\r]+(?:\n(?!\n|\*|#).*)*)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        candidate = label_match.group(1).strip().strip('"').strip("'").strip("`")
        if len(candidate) > 20:
            return candidate

    # 4. Look for quoted paragraph
    quoted = re.findall(r'"([^"]{30,})"', text, re.DOTALL)
    if quoted:
        return quoted[0].strip()

    # 5. Fallback: filter out conversational intro/outro lines and guidance
    lines = text.splitlines()
    filtered = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Stop if reaching guidance or instructions
        if re.match(r"^(?:💡|hướng\s*dẫn|lưu\s*ý\b|note\b|cách\s*dùng\b)", s, re.IGNORECASE):
            break
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
    # Strip conversational sign-offs or guidance at the end
    lines = s.splitlines()
    filtered_lines = []
    for line in lines:
        line_s = line.strip()
        if re.match(
            r"^(?:hope this helps|let me know|chúc bạn|lưu\s*ý\b|note\b|tùy\s*chọn\b|bạn có thể|💡|hướng\s*dẫn)",
            line_s,
            re.IGNORECASE,
        ):
            break
        filtered_lines.append(line)
    s = "\n".join(filtered_lines).strip()
    return s.strip('"').strip("'")

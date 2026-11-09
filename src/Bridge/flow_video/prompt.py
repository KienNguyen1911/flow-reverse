"""Video prompt sanitization (avoids false-positive Flow celebrity/identity policy blocks)."""

from __future__ import annotations

import re


def sanitize_video_prompt(prompt_text: str, aggressive: bool = False) -> str:
    """Sanitize video prompts to avoid false-positive Google Flow celebrity/identity policy blocks.

    In Frames Mode ('Khung hình' / `macaron_cookie_i2v_<n>s`), the starting frame image already
    locks the model's visual identity. Phrases like 'exact young Korean woman from the reference
    image' or 'Strictly lock facial identity' frequently trigger Google's prominent-person safety
    filter.
    """
    clean = " ".join([line.strip() for line in prompt_text.splitlines() if line.strip()])

    # Strip POLICY COMPLIANCE boilerplate if present
    clean = re.sub(r"\[POLICY COMPLIANCE\]:?[^\n]*?(?:living person|public figure)\.?", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\[POLICY COMPLIANCE\]:?[^.!?]*?[.!?]", "", clean, flags=re.IGNORECASE).strip()
    # Strip unnecessary prompt section headers
    clean = re.sub(r"\[(?:Reference Image to Video|Image to Video)[^\]]*\]:?", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\bTimeline:\s*", "", clean, flags=re.IGNORECASE).strip()

    replacements = [
        (r"\b(of\s+)?(the\s+)?exact\s+(young\s+)?(korean\s+|asian\s+)?(woman|girl|model|lady)(\s+from\s+the\s+reference\s+(image|photo))?\b", "of the fashion model"),
        (r"\b(young\s+)?(korean|asian|japanese|chinese)\s+(woman|girl|model|lady)\b", "fashion model"),
        (r"\bfrom\s+the\s+reference\s+(image|photo)(\s+pose)?\b", "in the scene"),
        (r"\b(strictly\s+)?lock(ed)?\s+facial\s+(identity|features|structure)(\s+and\s+hairstyle)?\b", "natural expression"),
        (r"\b(strictly\s+)?maintain(ing)?\s+(exact\s+)?facial\s+(identity|features)\b", "natural expression"),
        (r"\b(celebrity|idol|actress|k-pop|famous\s+person)\b", "model"),
        (r"\bvisible\s+skin\s+micro-pores,?\s*", ""),
        (r"\bauthentic\s+skin\s+texture\s+with\s+natural\s+pores,?\s*", "soft natural lighting, "),
        (r"\bzero\s+plastic\s+skin\s+smoothing,?\s*", ""),
    ]
    for pattern, repl in replacements:
        clean = re.sub(pattern, repl, clean, flags=re.IGNORECASE)

    # Strip Gemini timecode section labels and "Camera & Realism" identity boilerplate.
    # NOTE: `clean` đã bị join thành MỘT dòng ở trên, nên mọi regex `.*$` ở đây sẽ ăn tới hết
    # chuỗi. Chỉ xoá đúng header, không xoá phần nội dung phía sau nó.
    clean = re.sub(r"Camera\s*&\s*Realism\s*:\s*", "", clean, flags=re.IGNORECASE).strip()
    # Xoá nhãn mốc thời gian ở mọi dạng phổ biến, giữ lại phần mô tả sau nhãn.
    timecode_patterns = (
        r"-\s*\d+(?:\.\d+)?s\s*to\s*\d+(?:\.\d+)?s\s*\([^)]*\)\s*:\s*",
        r"\d+(?:\.\d+)?s\s*[-–]\s*\d+(?:\.\d+)?s\s*\([^)]*\)\s*:\s*",
        r"\d+(?:\.\d+)?s\s*[-–]\s*\d+(?:\.\d+)?s\s*:\s*",
        r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?s\s*:\s*",
        r"\[\s*\d+(?:\.\d+)?s?\s*[-–]\s*\d+(?:\.\d+)?s\s*\]\s*:?\s*",
        r"\[\s*\d+(?:\.\d+)?s\s*\]\s*:?\s*",
        r"\(\s*\d+(?:\.\d+)?s\s*[-–]\s*\d+(?:\.\d+)?s\s*\)\s*:\s*",
    )
    for pat in timecode_patterns:
        clean = re.sub(pat, " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s{2,}", " ", clean).strip()

    if aggressive:
        aggressive_replacements = [
            (r"\bglances\s+over\s+(her|his|their)\s+shoulder,?\s*", "rotates smoothly, "),
            (r"\bfacing\s+the\s+camera\b", "in a balanced front silhouette"),
            (r"\blook(s|ing)?\s+(directly\s+|straight\s+)?at\s+the\s+camera\b", "maintaining natural posture"),
            (r"\b(the\s+)?(woman|girl|lady)\b", "the fashion subject"),
            (r"\b(the\s+)?model('s)?\b", lambda m: "the subject's" if m.group(2) else "the subject"),
            (r"\bshe\b", "the subject"),
            (r"\bher\b", "their"),
        ]
        for pattern, repl in aggressive_replacements:
            clean = re.sub(pattern, repl, clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s{2,}", " ", clean).strip()
        if not clean:
            clean = (
                "A smooth, realistic 8-second fashion lookbook video. "
                "The subject moves gracefully with natural posture, gentle fabric flow, "
                "soft studio lighting, subtle handheld camera movement, 24fps."
            )
        else:
            clean += " Focus on garment silhouette, realistic fabric drape, soft studio lighting, 8 seconds."

    return clean

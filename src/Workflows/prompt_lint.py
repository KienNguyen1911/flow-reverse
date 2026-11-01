"""Prompt Lint — kiểm tra prompt trước khi gửi lên Google Flow.

Linter không chặn cứng; nó trả danh sách cảnh báo để UI hiển thị và để test assert.
Quy tắc ở đây phải khớp với quy tắc trong `prompt-skills/*.md` — skill là nguồn sự thật,
linter chỉ máy móc hoá những gì skill đã dặn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

WarnLevel = Literal["error", "warn"]


@dataclass
class PromptWarning:
    code: str
    level: WarnLevel
    message: str
    match: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "level": self.level, "message": self.message, "match": self.match}


@dataclass
class LintResult:
    ok: bool
    word_count: int
    warnings: list[PromptWarning] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "word_count": self.word_count,
            "warnings": [w.to_dict() for w in self.warnings],
        }


# --- Quy tắc video --------------------------------------------------------- //

#: UI/graphic vocabulary — AI video không vẽ được chữ sắc nét, lớp dựng lo phần này.
UI_TERMS = (
    "sidebar", "item column", "progress bar", "split screen", "split-screen",
    "card", "cards", "banner", "collage", "infographic", "subtitle", "caption",
    "label", "text overlay", "on-screen text", "thumbnail", "panel",
)

#: Cụm bị `sanitize_video_prompt(aggressive=True)` viết lại — dùng thì lần retry 2 sẽ phá nghĩa.
AGGRESSIVE_REWRITES = (
    "glances over her shoulder", "looks at the camera", "looking directly at the camera",
    "facing the camera", "the woman", "the girl", "the lady",
)

#: Đại từ sẽ bị đổi thành "the subject" mà không viết hoa lại đầu câu.
PRONOUN_RE = re.compile(r"\b(she|her|hers)\b", re.IGNORECASE)

#: Header mốc thời gian bị sanitizer cắt, để lại câu cụt.
TIMECODE_HEADER_RE = re.compile(
    r"(\bTimeline\s*:|\bCamera\s*&\s*Realism\s*:|\d+(?:\.\d+)?\s*s?\s*[-–]\s*\d+(?:\.\d+)?\s*s\s*:|\[\s*\d+(?:\.\d+)?s)",
    re.IGNORECASE,
)

POLICY_CLAUSE_RE = re.compile(r"\[\s*POLICY\s+COMPLIANCE\s*\]", re.IGNORECASE)

#: Cụm ra lệnh model **vẽ lại giải phẫu** trong prompt ảnh try-on. Xem
#: `prompt-skills/try-on-image-prompter.md` §2.3.1 — chúng đổi vóc dáng so với Ảnh 1,
#: tức là phá Identity Lock, kể cả khi người dùng chỉ muốn "trông cao hơn".
IMAGE_ANATOMY_REWRITES = (
    "elongated legs", "longer legs", "overly long legs", "very long legs",
    "slimmer waist", "tiny upper body", "8 heads tall", "eight heads tall",
    "stretch the entire body", "stretched limbs", "extremely tall",
    "very tall and slim", "make her look taller", "make the model taller",
    "model proportions",
)

#: Góc máy / tiêu cự làm hỏng cảm giác chiều cao. Khác `IMAGE_ANATOMY_REWRITES`:
#: nhóm này *không* đổi cơ thể, chỉ chọn góc nhìn bất lợi.
#: Lưu ý: `35mm` KHÔNG nằm ở đây vì nó còn là tên phong cách ("raw candid 35mm
#: photography"). Chỉ bắt khi đứng cạnh chữ `lens`.
IMAGE_PERSPECTIVE_ERRORS = (
    "worm's-eye view", "worms eye view", "extreme low angle", "extremely low angle",
    "high angle shot", "shot from above", "overhead perspective", "downward camera tilt",
    "24mm", "28mm wide-angle", "wide-angle distortion", "35mm lens", "35mm wide angle",
    "35mm wide-angle", "24mm lens", "28mm lens",
)

#: Tư thế hai chân làm mất đường chân. Khi đùi chồng hoặc hai chân dính thành một khối,
#: mắt không tìm được điểm kết thúc của đường chân ⇒ đọc ra lùn, bất kể góc máy.
#: Đây là lỗi của cụm cũ `front foot slightly across the body line` — xem skill §2.2.1.
IMAGE_LEG_POSE_ERRORS = (
    "crossed legs", "overlapping thighs", "legs touching", "legs together",
    "one leg in front of the other", "legs merging", "feet together",
    "heels together", "feet shoulder-width apart",
    # Cụm cũ của chính skill này — bước chéo qua đường trục làm hai chân giao nhau
    # trong khung 2D. Đã thay bằng "without crossing the body's vertical centreline".
    # Lưu ý: KHÔNG đưa `crossing the body's vertical` vào đây — cụm đúng là
    # "without crossing the body's vertical centreline", sẽ bị bắt nhầm.
    "across the body line", "across the body's vertical centerline",
    "across the body's vertical centreline",
)

#: Khối cố định của skill ảnh try-on (§2.2.2). Thiếu khối này, tỷ lệ hình thể sẽ nhảy
#: giữa các ảnh trong cùng một lookbook vì model tự ứng biến mỗi lần.
#: Nhận mọi biến thể tên đã thấy trên thực tế:
#:   [HEIGHT & PROPORTION OPTIMIZATION]
#:   [POSE & HEIGHT PERCEPTION OPTIMIZATION V4]   (mẫu người dùng, không có dấu &)
#:   [END POSE & HEIGHT PERCEPTION OPTIMIZATION]
HEIGHT_BLOCK_RE = re.compile(
    r"\[\s*(?:END\s+)?(?:POSE\s*&\s*)?"
    r"HEIGHT(?:\s*&\s*(?:PERCEPTION|PROPORTION)|\s+PERCEPTION|\s+PROPORTION)?"
    r"\s+OPTIMIZATION(?:\s+V\d+)?\s*\]",
    re.IGNORECASE,
)

#: Mô tả lại thứ đã có trong ảnh nguồn (làm loãng token chuyển động).
IMAGE_RESTATE_TERMS = (
    "8k", "ultra-photorealistic", "masterpiece", "best quality", "award-winning",
    "slow motion", "slow-motion",
)

VIDEO_MAX_WORDS = 80
VIDEO_MIN_WORDS = 10


def _word_count(text: str) -> int:
    return len(text.split())


def _find_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """Khớp theo ranh giới từ: 'card' không được khớp 'cardigan'."""
    hits: list[str] = []
    for t in terms:
        if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", text, re.IGNORECASE):
            hits.append(t)
    return hits


#: Phủ định đứng ngay trước cụm thì cụm đó là *cấm*, không phải *yêu cầu*.
#: `no wide-angle distortion` trong negative prompt không được báo lỗi như
#: `wide-angle distortion` trong prompt khẳng định.
_NEGATION_RE_TMPL = r"(?:no|not|never|without|avoid|avoiding|avoid distortions like)\s+$"


def _find_affirmed_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """Như `_find_terms` nhưng bỏ qua lần khớp bị phủ định ngay trước đó."""
    hits: list[str] = []
    for t in terms:
        pattern = re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])", re.IGNORECASE)
        for m in pattern.finditer(text):
            before = text[: m.start()]
            if re.search(_NEGATION_RE_TMPL, before, re.IGNORECASE):
                continue
            hits.append(t)
            break
    return hits


def lint_video_prompt(prompt: str) -> LintResult:
    """Kiểm tra một prompt video trước khi gửi Flow."""
    warnings: list[PromptWarning] = []
    text = (prompt or "").strip()
    words = _word_count(text)

    if not text:
        warnings.append(PromptWarning("empty", "error", "Prompt rỗng — sẽ gửi lên Flow một chuỗi trống."))
        return LintResult(ok=False, word_count=0, warnings=warnings)

    if words > VIDEO_MAX_WORDS:
        warnings.append(PromptWarning(
            "too_long", "warn",
            f"Prompt {words} từ, vượt ngân sách {VIDEO_MAX_WORDS} từ của skill video.",
        ))
    elif words < VIDEO_MIN_WORDS:
        warnings.append(PromptWarning(
            "too_short", "warn",
            f"Prompt chỉ {words} từ — có thể thiếu mô tả chuyển động camera/cơ thể.",
        ))

    for term in _find_terms(text, UI_TERMS):
        warnings.append(PromptWarning(
            "ui_vocabulary", "error",
            f"Prompt chứa từ vựng UI '{term}'. Lớp dựng (HyperFrames/editor) lo phần này, "
            "không phải AI video.",
            match=term,
        ))

    for term in _find_terms(text, AGGRESSIVE_REWRITES):
        warnings.append(PromptWarning(
            "aggressive_rewrite", "warn",
            f"Cụm '{term}' sẽ bị sanitize(aggressive=True) viết lại ở lần thử thứ 2.",
            match=term,
        ))

    m = PRONOUN_RE.search(text)
    if m:
        warnings.append(PromptWarning(
            "pronoun", "warn",
            "Prompt dùng she/her — bộ lọc aggressive đổi thành 'the subject' và làm cụt ngữ pháp. "
            "Gọi chủ thể là 'the model'.",
            match=m.group(0),
        ))

    m = TIMECODE_HEADER_RE.search(text)
    if m:
        warnings.append(PromptWarning(
            "timecode_header", "warn",
            f"Prompt chứa nhãn mốc thời gian '{m.group(0)}' — sanitizer sẽ cắt và có thể để lại câu cụt. "
            "Diễn đạt nhịp bằng lời văn ('for the first three seconds ...').",
            match=m.group(0),
        ))

    if POLICY_CLAUSE_RE.search(text):
        warnings.append(PromptWarning(
            "policy_clause", "error",
            "[POLICY COMPLIANCE] đã bị khai tử — không chèn vào prompt video.",
        ))

    for term in _find_terms(text, IMAGE_RESTATE_TERMS):
        warnings.append(PromptWarning(
            "empty_modifier", "warn",
            f"Từ đệm '{term}' không giúp ích và có thể gây cảm giác video AI giả.",
            match=term,
        ))

    ok = not any(w.level == "error" for w in warnings)
    return LintResult(ok=ok, word_count=words, warnings=warnings)


def lint_image_prompt(prompt: str) -> LintResult:
    """Kiểm tra nhẹ cho prompt ảnh (không áp ngân sách từ của video)."""
    warnings: list[PromptWarning] = []
    text = (prompt or "").strip()
    words = _word_count(text)

    if not text:
        warnings.append(PromptWarning("empty", "error", "Prompt ảnh rỗng."))
        return LintResult(ok=False, word_count=0, warnings=warnings)

    if POLICY_CLAUSE_RE.search(text):
        warnings.append(PromptWarning(
            "policy_clause", "error",
            "[POLICY COMPLIANCE] đã bị khai tử — không chèn vào prompt ảnh.",
        ))

    if not HEIGHT_BLOCK_RE.search(text):
        warnings.append(PromptWarning(
            "missing_height_block", "warn",
            "Prompt ảnh try-on thiếu khối [HEIGHT & PROPORTION OPTIMIZATION] (§2.2.2) — "
            "tỷ lệ hình thể sẽ lệch giữa các ảnh trong cùng lookbook. Chèn nguyên văn khối cố định.",
        ))

    for term in _find_affirmed_terms(text, IMAGE_ANATOMY_REWRITES):
        warnings.append(PromptWarning(
            "anatomy_rewrite", "error",
            f"Cụm '{term}' bảo model vẽ lại giải phẫu ⇒ đổi vóc dáng so với Ảnh 1. "
            "Dùng 'long unbroken leg line' / 'balanced leg-to-torso ratio' thay thế (§2.3.1).",
            match=term,
        ))

    for term in _find_affirmed_terms(text, IMAGE_PERSPECTIVE_ERRORS):
        warnings.append(PromptWarning(
            "unflattering_perspective", "warn",
            f"Cụm '{term}' chọn góc máy/tiêu cự bất lợi cho chiều cao. "
            "Dùng 'subtle low-angle perspective at hip level' và tiêu cự 70mm.",
            match=term,
        ))

    for term in _find_affirmed_terms(text, IMAGE_LEG_POSE_ERRORS):
        warnings.append(PromptWarning(
            "leg_pose", "warn",
            f"Tư thế '{term}' làm hai chân dính/chồng thành một khối ⇒ mất đường chân, "
            "đọc ra lùn. Dùng 'one foot slightly forward without crossing the centreline'.",
            match=term,
        ))

    ok = not any(w.level == "error" for w in warnings)
    return LintResult(ok=ok, word_count=words, warnings=warnings)


def lint_prompt(prompt: str, kind: str) -> LintResult:
    return lint_video_prompt(prompt) if kind == "video" else lint_image_prompt(prompt)


def lint_script_prompts(script: dict) -> dict:
    """Lint toàn bộ motion_prompt trong một lookbook script."""
    results: dict[str, dict] = {}
    ok = True
    for clip in script.get("clips") or []:
        cid = clip.get("id") or "?"
        res = lint_video_prompt(clip.get("motion_prompt") or "")
        results[cid] = res.to_dict()
        ok = ok and res.ok
    return {"ok": ok, "clips": results}

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

#: Từ khiến Flow từ chối cả request bằng `PUBLIC_ERROR_UNSAFE_GENERATION` (gRPC `[3]`),
#: kể cả khi từ đó nằm trong mệnh đề phủ định. Đo trên server thật (2026‑11‑12, profile
#: `aaaaa`): cùng một prompt + cùng ảnh tham chiếu,
#:   - `Avoid: no brand logo.` / `Avoid: no brand.`  → REJECT
#:   - `Avoid: no logo.` / `Avoid: no watermark.`    → 200 OK + ảnh
#:   - bỏ hẳn hai từ `branding` trong prompt try-on → 200 OK + ảnh đúng
#: Phủ định dùng `_find_terms` chứ không `_find_affirmed_terms`: "no brand" vẫn bị chặn.
IMAGE_FILTER_TRIGGER_TERMS = (
    "brand", "brands", "branded", "branding", "brand logo", "brand name",
)

#: Ngân sách từ cho prompt video. Trước đây là 80 vì skill chỉ cho phép 1 câu camera + 2 câu cơ thể.
#: Khi prompt phải mang 3 beat có mốc thời gian (xem `motion_prompt.beats_to_prompt`), 80 không đủ
#: để vừa diễn đạt nhịp vừa nói điều KHÔNG được xảy ra. Đo trên script mẫu: 99–110 từ đi qua
#: `sanitize_video_prompt(aggressive=False)` nguyên văn, nên trần 120 vẫn an toàn.
VIDEO_MAX_WORDS = 120
VIDEO_MIN_WORDS = 40

#: Trần ký tự cho prompt ảnh try-on. Template V3 trong skill đo được 3.451 ký tự; sau khi agent điền
#: tên món đồ và chèn `prompt_core` của pose thì thực tế rơi vào 3.800–4.200. 4.500 là mốc để phát
#: hiện prompt phình trở lại: bản V1 người dùng dán dài ~7.000 ký tự và phần lớn trong đó là diễn giải
#: lặp — chính thứ đã bị cắt ở V3. Đây là **warn**, không phải error: có outfit nhiều món thật sự cần
#: mô tả dài, và linter không đủ khôn để phân biệt.
IMAGE_PROMPT_MAX_CHARS = 4500

#: Câu neo độ dài khi ảnh trang phục là coordinate sheet (flat-lay). Xem
#: `prompt-skills/try-on-image-prompter.md` §2.1.1.
#:
#: Sheet xếp từng món **cùng cỡ cho dễ nhìn**, nên tỷ lệ giữa các món trên sheet là tỷ lệ
#: *trình bày*, không phải tỷ lệ *trên người*. Đo thực tế 2026‑11‑12 (bike shorts đen +
#: sweatshirt hồng): shorts/áo trên sheet 0.755, trên cơ thể ~0.44, ảnh ra 0.685 — ảnh bám
#: sheet, quần ra dài gấp ~1.6 lần.
#:
#: Dùng bởi `prompt_agent` khi nó **biết chắc** ảnh tham chiếu là sheet (tên file). Linter
#: không dùng được: prompt thật không hề viết "flat-lay", nên một luật dò chữ trong prompt
#: sẽ không bao giờ cháy — tức là guard giả.
SHEET_LENGTH_ANCHOR_RE = re.compile(
    r"length\s+is\s+anchored|anchored\s+to\s+(?:<<\s*model\s*>>|the\s+body)"
    r"|scale\s+each\s+hem|never\s+to\s+the\s+layout",
    re.IGNORECASE,
)

#: Tên file cho biết ảnh tham chiếu là một coordinate sheet / flat-lay chứ không phải người
#: mặc thật. Đây là tín hiệu **chắc chắn** duy nhất không cần nhìn pixel: pipeline đặt tên
#: file theo loại ảnh (`..._editorial_fashion_coordinate_sheet_verti.jpg`).
SHEET_FILENAME_RE = re.compile(
    r"coordinate[_-]?sheet|flat[_-]?lay|ghost[_-]?mannequin|product[_-]?sheet|cutout",
    re.IGNORECASE,
)


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
_NEGATION_RE_TMPL = (
    r"(?:no|not|never|without|avoid|avoiding|avoid distortions like"
    r"|with no|and no|or no|nor"
    r"|no added|no extra|no any|without any|without added)\s+$"
)


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


#: Dấu phân cách clause. Phủ định có phạm vi **trong một clause**: câu
#: "staying inside the frame, with no cut, no added banner or caption" là một clause phủ định trọn
#: vẹn, trong khi "turns with a banner or caption" không có phủ định nào.
_CLAUSE_SPLIT_RE = re.compile(r"(?:[,;.!?]\s+|\n)")

#: Dấu hiệu mở đầu một clause phủ định.
_CLAUSE_NEGATION_RE = re.compile(
    r"^(?:no|not|never|without|avoid|avoiding|nor|with no|and no|or no|"
    r"no added|no extra|without any|without added|staying inside)\b",
    re.IGNORECASE,
)


def _in_negative_clause(text: str, pos: int) -> bool:
    """Lần khớp tại `pos` có nằm trong một clause phủ định không."""
    start = 0
    for sep in _CLAUSE_SPLIT_RE.finditer(text):
        if sep.end() > pos:
            break
        start = sep.end()
    clause = text[start:pos]
    # Bỏ liên từ nối đầu clause: "..., and no added lettering" → "no added lettering".
    clause = re.sub(r"^(?:and|or|but|then|with)\s+", "", clause.strip(), flags=re.IGNORECASE)
    return bool(_CLAUSE_NEGATION_RE.match(clause))


def _find_affirmed_in_clause(text: str, terms: tuple[str, ...]) -> list[str]:
    """Như `_find_affirmed_terms` nhưng dùng phạm vi clause.

    Dùng cho từ vựng UI: prompt video **buộc** phải nói điều không được xảy ra, và payload Flow
    không có trường negative riêng. Nếu linter phạt cả mệnh đề cấm thì nó đang phạt đúng câu mà
    skill yêu cầu viết.
    """
    hits: list[str] = []
    for t in terms:
        pattern = re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])", re.IGNORECASE)
        for m in pattern.finditer(text):
            if _in_negative_clause(text, m.start()):
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

    for term in _find_affirmed_in_clause(text, UI_TERMS):
        # `_find_affirmed_terms` chứ không `_find_terms`: skill video yêu cầu prompt nói rõ điều KHÔNG
        # được xảy ra ("staying inside the frame, with no cut", "no added lettering or printed
        # graphics"). Trước đây "no added banner" bị coi là dùng từ vựng UI, tức linter phạt đúng câu
        # mà skill bảo phải viết.
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

    if len(text) > IMAGE_PROMPT_MAX_CHARS:
        warnings.append(PromptWarning(
            "image_prompt_too_long", "warn",
            f"Prompt {len(text)} ký tự, vượt {IMAGE_PROMPT_MAX_CHARS}. Prompt dài không làm ảnh "
            "chính xác hơn — V1 dài ~7.000 ký tự mà vẫn lệch tỷ lệ. Cắt phần diễn giải lặp "
            "(§2.2.2a) trước khi thêm mô tả mới.",
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

    for term in _find_terms(text, IMAGE_FILTER_TRIGGER_TERMS):
        warnings.append(PromptWarning(
            "filter_trigger", "error",
            f"Từ '{term}' làm Flow từ chối cả request bằng PUBLIC_ERROR_UNSAFE_GENERATION "
            "(gRPC 3), kể cả trong câu phủ định. Viết 'no added marks', 'no labels', "
            "'no logos' — đừng dùng họ từ 'brand'.",
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

"""Beat → prompt renderer cho node video Lookbook.

Vì sao module này tồn tại
------------------------
Prompt video gửi Flow **không mang được nhãn thời gian**:

1. `sanitize_video_prompt()` (`src/Bridge/flow_video_bridge.py`) xoá mọi mốc `0s-2s:` / `[0-2s]`
   trước khi gửi, và để lại rác với dạng `(0s-2s)`.
2. Payload `abra_i2v_8s` (`build_video_args`) chỉ có một chuỗi prompt — không có trường timeline,
   không có trường negative.

Nên nhịp phải sống ở **dữ liệu** (`clips[].beats` trong script) và chỉ được **diễn đạt** thành văn
xuôi thứ tự ở đây. Định dạng văn xuôi dưới đây là định dạng duy nhất đã đo được là đi qua sanitizer
nguyên văn ở cả `aggressive=False` và `aggressive=True` (chỉ đổi đại từ ở mode sau).

Nguyên tắc: **tất định**. Cùng một script → cùng một prompt, byte-for-byte. Agent không được viết
lại câu beat, vì gate round-trip chỉ có giá trị khi đầu vào không đổi giữa các lần chạy.
"""

from __future__ import annotations

import re

from .script_contract import BeatSpec, ClipSpec

#: Trần cứng để khớp `prompt_lint.VIDEO_MAX_WORDS`. Vượt ngưỡng này thì prompt dài tới mức bộ lọc
#: aggressive càng có nhiều bề mặt để phá, và model càng dễ bỏ beat cuối.
MAX_PROMPT_WORDS = 120

#: Ngân sách đích: 1 câu camera + 3 beat + câu phủ định. Đo trên script mẫu: 99–110 từ.
#: Đích rộng hơn của plan ban đầu (70–100) vì văn xuôi 3 beat + phủ định không xuống dưới ~95 từ mà
#: vẫn giữ được mốc giây; trần cứng vẫn là `MAX_PROMPT_WORDS`.
TARGET_PROMPT_WORDS = (70, 115)

_CARDINAL = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}
_ORDINAL = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
}

#: Câu camera theo `clips[].camera`. Giữ đúng bộ từ skill video §3, không tự chế cụm mới — cụm lạ
#: sẽ bị `aggressive=True` viết lại ở lần retry thứ 2.
CAMERA_SENTENCES: dict[str, str] = {
    "locked": "Camera stays locked on a fixed frame",
    "push_in_slow": "Camera pushes in slowly at natural real-time speed",
    "drift_same_axis": "Camera drifts closer on the same axis",
    "pan_down": "Camera pans gently downward to the waist and hem",
    "handheld_subtle": "Camera carries subtle handheld breathing",
}
DEFAULT_CAMERA = "push_in_slow"

#: Động từ mở đầu mỗi beat phải nằm trong danh sách này. Mục đích không phải kiểm ngữ pháp mà là
#: chặn agent/người viết trượt sang mô tả ngoại hình ("is wearing", "looks beautiful") — thứ đã có
#: trong ảnh first frame và chỉ làm loãng token chuyển động.
MOTION_VERBS = frozenset({
    "stands", "plants", "turns", "pivots", "completes", "settles", "angles", "rolls",
    "shifts", "steps", "walks", "brushes", "adjusts", "lifts", "raises", "returns",
    "holds", "pauses", "drops", "crosses", "leans", "releases", "brings",
})

#: Cụm sẽ bị `sanitize_video_prompt(aggressive=True)` viết lại (xem skill §0 ràng buộc 2) hoặc bị
#: linter coi là từ vựng UI / từ đệm rỗng. Renderer từ chối thay vì render ra prompt sẽ bị phá.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "glances over her shoulder",
    "looks at the camera",
    "looking directly at the camera",
    "facing the camera",
    "the woman", "the girl", "the lady",
    "slow motion", "slow-motion",
    "8k", "ultra-photorealistic", "masterpiece", "best quality", "award-winning",
    "sidebar", "progress bar", "split screen", "banner", "caption", "card",
    "collage", "infographic", "thumbnail", "panel", "label", "overlay",
)

#: Đại từ làm `aggressive=True` sinh câu cụt vì nó thay `She` → `the subject` mà không viết hoa lại.
PRONOUN_RE = re.compile(r"\b(she|her|hers|his)\b", re.IGNORECASE)


class MotionPromptError(ValueError):
    """Script không render được prompt an toàn (từ ngoài bộ từ vựng, beat hỏng, …)."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _words(n: float) -> str:
    key = int(round(n))
    if key not in _CARDINAL:
        raise MotionPromptError(
            f"beat dài {n}s — renderer chỉ diễn đạt được 1..10 giây bằng chữ."
        )
    return _CARDINAL[key]


def _seconds(n: float) -> str:
    return f"{_words(n)} second" if int(round(n)) == 1 else f"{_words(n)} seconds"


def _ordinal(n: float) -> str:
    key = int(round(n))
    if key not in _ORDINAL:
        raise MotionPromptError(f"mốc {n}s vượt quá thứ tự renderer hỗ trợ (1..10).")
    return _ORDINAL[key]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _strip_period(text: str) -> str:
    return text.strip().rstrip(".")


def _normalize_action(action: str) -> str:
    """Bỏ phần dẫn thừa, trả về câu chuyển động thuần.

    `Continuing from that pose` thuộc câu camera của clip có `chain_from`; nếu người viết beat cũng
    mở đầu bằng nó thì prompt lặp cụm đó hai lần.
    """
    body = _strip_period(action)
    body = re.sub(r"^continuing from that pose,?\s*", "", body, flags=re.IGNORECASE)
    # `the model angles ...` và `angles ...` là cùng một câu; bỏ tiền tố để kiểm động từ đầu tiên.
    body = re.sub(r"^the model\s+", "", body, flags=re.IGNORECASE)
    return body


def _check_action(action: str, label: str) -> None:
    """Chặn từ vựng sai trước khi nó tới Flow."""
    clean = _normalize_action(action)
    if not clean:
        raise MotionPromptError(f"{label}: `action` rỗng")

    first = clean.split()[0].lower()
    if first not in MOTION_VERBS:
        raise MotionPromptError(
            f"{label}: `action` mở đầu bằng '{first}', không có trong MOTION_VERBS. "
            f"Prompt video chỉ mô tả chuyển động; ngoại hình/trang phục đã nằm trong ảnh first frame."
        )

    low = clean.lower()
    for term in FORBIDDEN_TERMS:
        # Khớp theo ranh giới từ: `card` không được khớp `cardigan`, `panel` không khớp `panels`.
        # Đây đúng là lỗi mà `test_linter_word_boundary_does_not_match_cardigan` bảo vệ ở linter.
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", low):
            raise MotionPromptError(
                f"{label}: chứa cụm bị bộ lọc phá hoặc từ vựng UI '{term}'. Xem skill §0 và §6."
            )
    m = PRONOUN_RE.search(clean)
    if m:
        raise MotionPromptError(
            f"{label}: dùng đại từ '{m.group(0)}' — gọi 'the model', nếu không "
            "`sanitize(aggressive=True)` sẽ tạo câu cụt."
        )


def _beat_clause(beat: BeatSpec, index: int, total: int) -> str:
    """Một beat → một câu, mở đầu bằng mốc thời gian diễn đạt bằng lời."""
    if total == 1:
        prefix = "Throughout the clip"
    elif index == 0:
        prefix = f"For the first {_seconds(beat.duration_s)}"
    elif index == total - 1:
        prefix = f"In the final {_seconds(beat.duration_s)}"
    else:
        prefix = (
            f"From the {_ordinal(beat.at_s)} to the {_ordinal(beat.end_s)} second"
        )

    body = _lower_first(_normalize_action(beat.action))

    clause = f"{prefix} the model {body}"
    if beat.holds_gaze and "eye contact" not in body.lower() and "lens" not in body.lower():
        # Lưới an toàn: beat khai `holds_gaze` mà người viết quên nhắc mắt thì renderer bù vào ngay
        # sau chủ thể, không phải ở cuối câu — cuối câu beat thường đã có mệnh đề phụ ("so the clip
        # loops") và nhét thêm vào đó sẽ đọc gãy.
        clause = f"{prefix} the model, holding steady eye contact with the lens, {body}"
    return clause


def _camera_sentence(clip: ClipSpec) -> str:
    key = clip.camera or DEFAULT_CAMERA
    sentence = CAMERA_SENTENCES.get(key)
    if sentence is None:
        raise MotionPromptError(
            f"clip '{clip.id}': camera='{key}' không có trong CAMERA_SENTENCES "
            f"({', '.join(sorted(CAMERA_SENTENCES))})."
        )
    if clip.chain_from:
        # Clip nối tiếp phải mở đầu bằng dấu hiệu "nối từ frame trước", nếu không model coi đây là
        # một cảnh mới và đặt lại tư thế ở khung đầu.
        return f"Continuing from that pose, {_lower_first(sentence)}"
    return sentence


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #


def beats_to_prompt(clip: ClipSpec) -> str:
    """Render `clip.beats` thành một prompt tiếng Anh đi qua sanitizer nguyên vẹn.

    Cấu trúc: `1 câu camera` + `N câu beat` + `các câu negative`. Không header, không nhãn giây.
    """
    if not clip.beats:
        raise MotionPromptError(
            f"clip '{clip.id}' không có `beats`. Renderer chỉ dùng khi script khai beat; "
            "ngược lại để agent tự viết theo skill."
        )

    parts: list[str] = [f"{_strip_period(_camera_sentence(clip))}."]

    total = len(clip.beats)
    for index, beat in enumerate(clip.beats):
        _check_action(beat.action, f"clip '{clip.id}' beat #{index + 1}")
        parts.append(f"{_beat_clause(beat, index, total)}.")

    for clause in clip.negative:
        clean = _strip_period(clause)
        if clean:
            parts.append(f"{clean[:1].upper()}{clean[1:]}.")

    prompt = " ".join(parts)
    prompt = re.sub(r"\s{2,}", " ", prompt).strip()

    words = len(prompt.split())
    if words > MAX_PROMPT_WORDS:
        raise MotionPromptError(
            f"clip '{clip.id}': prompt {words} từ, vượt trần {MAX_PROMPT_WORDS}. "
            "Rút gọn `action` hoặc `negative` trong script."
        )
    return prompt


def prompt_warnings(clip: ClipSpec, prompt: str) -> list[str]:
    """Cảnh báo mềm: prompt chạy được nhưng lệch ngân sách đích."""
    out: list[str] = []
    words = len(prompt.split())
    low, high = TARGET_PROMPT_WORDS
    if words < low:
        out.append(
            f"clip '{clip.id}': prompt {words} từ, dưới ngân sách {low}–{high}. "
            "Nhiều khả năng thiếu beat hoặc thiếu câu phủ định."
        )
    elif words > high:
        out.append(
            f"clip '{clip.id}': prompt {words} từ, trên ngân sách {low}–{high} (trần {MAX_PROMPT_WORDS})."
        )
    if not clip.negative:
        out.append(
            f"clip '{clip.id}': không có `negative` — prompt không nói gì về điều KHÔNG được xảy ra "
            "(cắt cảnh, chữ dán, bước ra khỏi khung)."
        )
    return out


__all__ = [
    "CAMERA_SENTENCES",
    "DEFAULT_CAMERA",
    "FORBIDDEN_TERMS",
    "MAX_PROMPT_WORDS",
    "MOTION_VERBS",
    "MotionPromptError",
    "TARGET_PROMPT_WORDS",
    "beats_to_prompt",
    "prompt_warnings",
]

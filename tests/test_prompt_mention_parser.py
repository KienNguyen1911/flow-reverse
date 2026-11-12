import pytest
from src.Bridge.flow.composer import (
    MentionSegment,
    TextSegment,
    parse_prompt_segments,
)


def test_parse_prompt_segments_declares_each_reference_once():
    """Mỗi tham chiếu được khai báo **một** lần ở đầu, rồi thân prompt giữ token dạng chữ."""
    refs = [
        {"alias_name": "model_a1b2c3", "media_id": "uuid-1"},
        {"alias_name": "garment_d4e5f6", "media_id": "uuid-2"},
        {"alias_name": "scene_789abc", "media_id": "uuid-3"},
    ]
    prompt = "Try-on photo of <<model>> wearing <<garment>> in <<background>>"
    segments = parse_prompt_segments(prompt, refs)

    chips = [s for s in segments if isinstance(s, MentionSegment)]
    assert [c.alias_name for c in chips] == ["model_a1b2c3", "garment_d4e5f6", "scene_789abc"]
    assert [c.media_id for c in chips] == ["uuid-1", "uuid-2", "uuid-3"]

    text = "".join(s.text for s in segments if isinstance(s, TextSegment))
    # Khai báo xuất hiện đúng một lần cho mỗi slot.
    assert text.count("<<model>>") == 2       # khai báo + thân
    assert text.count("<<garment>>") == 2
    assert text.count("<<background>>") == 2
    # Không còn alias nào bị chèn thẳng vào text.
    assert "@model_a1b2c3" not in text
    assert "@garment_d4e5f6" not in text


def test_parse_prompt_segments_body_keeps_tokens_not_alias():
    """Thân prompt không bị đổi token thành `@alias`.

    Pipeline cũ thay mỗi lần lặp thành `@model_518cd6`, và một prompt try-on thật chứa 12
    chuỗi như vậy — dạng payload Flow trả INVALID_ARGUMENT.
    """
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    prompt = "A shot of <<model>> wearing <<garment>>, then <<model>> again."
    segments = parse_prompt_segments(prompt, refs)
    text = "".join(s.text for s in segments if isinstance(s, TextSegment))

    assert "@model_111" not in text and "@garment_222" not in text
    assert text.count("<<model>>") == 3    # 1 khai báo + 2 trong thân
    assert text.count("<<garment>>") == 2


def test_parse_prompt_segments_declares_refs_body_never_mentions():
    """Reference không được nhắc trong thân vẫn phải khai báo — Flow cần ảnh đính kèm."""
    refs = [
        {"alias_name": "model_111", "media_id": "m1"},
        {"alias_name": "garment_222", "media_id": "m2"},
    ]
    segments = parse_prompt_segments("Close-up portrait of a smile", refs)

    chips = [s for s in segments if isinstance(s, MentionSegment)]
    assert len(chips) == 2
    assert [c.alias_name for c in chips] == ["model_111", "garment_222"]


def test_parse_prompt_segments_declaration_precedes_body():
    """Chip phải nằm TRƯỚC phần thân, không xen giữa câu."""
    refs = [{"alias_name": "model_111", "media_id": "m1"}]
    segments = parse_prompt_segments("Body text here.", refs)

    types = [type(s).__name__ for s in segments]
    first_chip = types.index("MentionSegment")
    body_at = next(i for i, s in enumerate(segments)
                   if isinstance(s, TextSegment) and "Body text here." in s.text)
    assert first_chip < body_at


def test_parse_prompt_segments_empty_prompt():
    refs = [{"alias_name": "model_111", "media_id": "m1"}]
    segments = parse_prompt_segments("", refs)

    chips = [s for s in segments if isinstance(s, MentionSegment)]
    assert len(chips) == 1
    assert chips[0].alias_name == "model_111"


def test_agent_written_declaration_block_is_not_duplicated():
    """Agent đôi khi tự viết khối khai báo; tầng gửi cũng tạo khối đó.

    Đo thật: 1/3 lần gọi agent trả về khối khai báo ngay đầu prompt, rồi hệ thống chèn
    thêm một khối nữa ⇒ `Image 1, the person` xuất hiện 3 lần trong khi chỉ nên 1 lần mỗi
    dòng. Khối do agent viết phải bị bỏ, vì nó không mang chip.
    """
    refs = [
        {"alias_name": "model_518cd6", "media_id": "m1"},
        {"alias_name": "garment_c104c3", "media_id": "m2"},
    ]
    agent_prompt = (
        "<<model>> = Image 1, the person\n"
        "<<garment>> = Image 2, the outfit\n\n"
        "Try-on of <<model>> wearing <<garment>>."
    )
    body = _flatten(parse_prompt_segments(agent_prompt, refs))

    # Mỗi nhãn khai báo xuất hiện đúng một lần, không bị nhân đôi.
    assert body.count("Image 1, the person") == 1
    assert body.count("Image 2, the outfit") == 1
    # Và vẫn đúng một chip mỗi tham chiếu.
    assert body.count("@model_518cd6") == 1
    assert body.count("@garment_c104c3") == 1


def test_declaration_stripping_only_touches_the_leading_lines():
    """Chỉ bỏ khối ở ĐẦU prompt; câu trích giữa bài phải còn."""
    refs = [{"alias_name": "model_111", "media_id": "m1"}]
    prompt = (
        "<<model>> = Image 1, the person\n\n"
        "Keep the face of <<model>>.\n"
        "Do not write `<<garment>> = Image 2` yourself."
    )
    body = _flatten(parse_prompt_segments(prompt, refs))
    assert "<<model>> = Image 1, the person" in body   # khối do hệ thống tạo, 1 lần
    assert body.count("<<model>> = Image 1, the person") == 1
    # Câu trích giữa bài không bị xoá.
    assert "Do not write" in body


def test_parse_prompt_segments_no_refs():
    segments = parse_prompt_segments("simple text prompt", [])
    assert len(segments) == 1
    assert segments[0] == TextSegment("simple text prompt")


# --------------------------------------------------------------------------- #
# Regression: the request body must never carry literal `@alias` text.
# --------------------------------------------------------------------------- #

#: A prompt that mentions each reference several times, like the real try-on template.
_REPEATING_PROMPT = (
    "Try-on of <<model>> wearing <<garment>>.\n"
    "[IDENTITY] keep the face of <<model>>; <<model>> is the sole identity reference.\n"
    "[GARMENT] copy <<garment>> exactly; where text and <<garment>> disagree, "
    "<<garment>> wins.\n"
    "[ENV] take only light from <<background>>, never the person from <<background>>."
)


def _flatten(segments) -> str:
    """The prompt text that ends up in the request body (chips shown as their alias)."""
    out = []
    for s in segments:
        out.append(s.text if isinstance(s, TextSegment) else f"@{s.alias_name}")
    return "".join(out)


def test_no_repeated_mention_becomes_literal_alias_text():
    """Đây là lỗi đã làm Flow trả INVALID_ARGUMENT và bị đọc nhầm thành lỗi an toàn.

    Pipeline cũ thay *mỗi lần lặp* một tham chiếu bằng chữ `@model_51aad2`. Đo trên một
    prompt try-on thật: 12 chuỗi như vậy nằm thẳng trong `spec[8]` của request ogiZ0b.
    Sau khi đổi sang khai báo đầu prompt, mỗi alias chỉ được xuất hiện **một lần** — dưới
    dạng chip, không phải text.
    """
    refs = [
        {"alias_name": "model_518cd6", "media_id": "m1"},
        {"alias_name": "garment_c104c3", "media_id": "m2"},
        {"alias_name": "scene_28e836", "media_id": "m3"},
    ]
    body = _flatten(parse_prompt_segments(_REPEATING_PROMPT, refs))

    for alias in ("model_518cd6", "garment_c104c3", "scene_28e836"):
        assert body.count(f"@{alias}") == 1, (
            f"@{alias} xuất hiện {body.count('@' + alias)} lần — chỉ được 1 (chip khai báo)"
        )
    # Và token vẫn còn trong thân, để model biết đang nói về ảnh nào.
    # = 1 dòng khai báo + số lần trong _REPEATING_PROMPT (3 / 4 / 2).
    assert body.count("<<model>>") == 4
    assert body.count("<<garment>>") == 5
    assert body.count("<<background>>") == 3


# --------------------------------------------------------------------------- #
# Prompt completeness gate — the composer must hold the whole prompt before Generate.
# --------------------------------------------------------------------------- #

#: A realistic two-reference prompt, long and varied enough that a lost chunk is detectable.
_PROMPT = (
    "Try-on photograph of the exact same model from Image 1, wearing the exact garment "
    "from Image 2.\n\n[IDENTITY LOCK]\nPreserve the exact identity, facial features, "
    "hairstyle, hair colour and skin texture of the model in Image 1. Image 1 is the sole "
    "identity reference. Do not beautify, slim, symmetrise or age the face.\n\n"
    "[GARMENT FIDELITY]\nReproduce the complete outfit from Image 2 exactly: pale blue "
    "jacquard silk brocade tunic with woven floral patterns, a modest mandarin collar, "
    "wide flared three-quarter sleeves and high side waist slits.\n\n"
    "[POSE]\nBody turned about thirty to forty-five degrees away from the camera so the "
    "silhouette reads tall and narrow, shoulders and hips at a three-quarter angle.\n\n"
    "[HEIGHT & PROPORTION OPTIMIZATION]\nCamera at waist level with a three-degree upward "
    "tilt, horizon level, crown 12 percent below the top edge, figure filling 76 percent "
    "of the frame height.\n\n[ENVIRONMENT & LIGHTING]\nHistoric pavilion architecture "
    "with carved stone pillars and a red lacquered balustrade, soft outdoor daylight.\n\n"
    "Constraints: no altered facial identity, no garment redesign, no stretched limbs, "
    "no cropped head or feet, no text, no logos, no UI, no cards, no border, no collage."
)


def _composer_mirror(rendered: str) -> str:
    """What `prompt_value()` returns for `rendered`: chips show as `@alias`, plus padding."""
    return (
        rendered.replace("Image 1", "@model_518cd6  ")
        .replace("Image 2", "@garment_c104c3  ")
    )


def _gate(expected: str, composer_text: str) -> bool:
    """The verdict of `assert_prompt_complete`, without a live page."""
    from src.Bridge.flow.composer import PageInteractionError

    class _Probe:
        assert_prompt_complete = None

        def prompt_value(self_inner):
            return composer_text

    probe = _Probe()
    probe.prompt_value = _Probe.prompt_value.__get__(probe)
    from src.Bridge.flow.composer import ComposerMixin

    try:
        ComposerMixin.assert_prompt_complete(probe, expected)
        return True
    except PageInteractionError:
        return False


def test_prompt_gate_accepts_complete_prompt_with_chips():
    """Chip form (`@model_ab12`) must pass: it is the *normal* rendering, not a truncation.

    Comparing literally would reject every real prompt, so the gate would be dead weight.
    """
    assert _gate(_PROMPT, _composer_mirror(_PROMPT))
    # And the plain `Image N` form passes too (no references attached).
    assert _gate(_PROMPT, _PROMPT)


def test_prompt_gate_rejects_prefix_truncation():
    """A paste loop that dies part way leaves a prefix — the case users actually hit.

    Flow answers a malformed request with PUBLIC_ERROR_UNSAFE_GENERATION, which reads like
    a safety refusal and hides the real cause. The gate must catch it before the click.
    """
    full = _composer_mirror(_PROMPT)
    assert not _gate(_PROMPT, full[: len(full) // 2])
    assert not _gate(_PROMPT, full[:900])
    # Losing only the tail still counts as incomplete.
    assert not _gate(_PROMPT, full[: int(len(full) * 0.93)])


def test_prompt_gate_rejects_empty_and_middle_gap():
    full = _composer_mirror(_PROMPT)
    assert not _gate(_PROMPT, "")
    # Head and tail intact but a middle chunk swallowed: only the length test catches this.
    gap = full[:300] + full[-300:]
    assert not _gate(_PROMPT, gap)
    # Only the tail: a reversed head/tail test would let this through.
    assert not _gate(_PROMPT, full[-600:])

"""Kiểm tra 3 skill mới: prompt sinh ra có sống sót qua sanitize + parse không.

Chạy:  python tests/test_prompt_skills_contract.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.Bridge.flow_video_bridge import sanitize_video_prompt
from src.Bridge.gemini_bridge import parse_gemini_video_prompts
from src.Workflows.skill_manager import get_skill_manager

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "prompt-skills"
POSE_ASSETS = SKILLS / "poses" / "pose_assets.json"


def _pose_assets() -> dict:
    """Nguồn sự thật của thư viện pose (schema v2)."""
    return json.loads(POSE_ASSETS.read_text(encoding="utf-8"))

# Cụm mà bộ lọc aggressive sẽ viết lại (xem prompt-skills/lookbook-video-prompter.md mục 0)
FORBIDDEN_VIDEO_PHRASES = [
    "glances over her shoulder",
    "looks at the camera",
    "looking directly at the camera",
    "facing the camera",
    "the woman",
    "the girl",
    "the lady",
    "slow-motion",
    "slow motion",
]

# Header mốc thời gian bị regex cắt hoặc để lại rác
FORBIDDEN_VIDEO_HEADERS = [
    "Camera & Realism:",
    "- 0s to 3s",
    "- 2s to 6s",
    "[0-3s]",
]


def test_skills_load():
    mgr = get_skill_manager()
    mgr.reload()
    ids = {s.id for s in mgr.list_skills()}
    assert {
        "lookbook-video-prompter",
        "lookbook-item-cutout-prompter",
        "try-on-image-prompter",
    } <= ids
    # Skill plate riêng đã gộp vào try-on §2.5; nếu nó quay lại thì hai nguồn sự thật
    # cho 50mm/76% lại xuất hiện và lệch nhau.
    assert "lookbook-model-only-prompter" not in ids
    # Board NABI đã bị xoá: cột item chuyển hẳn sang lớp dựng, ảnh bìa cũng lấy từ canvas.
    assert "lookbook-thumbnail-prompter" not in ids


def test_no_skill_emits_policy_compliance_clause():
    """[POLICY COMPLIANCE] đã bị khai tử: không skill nào được chèn dòng này vào prompt.

    Dòng này từng được thêm để né bộ lọc Prominent People, nhưng nó làm loãng prompt và
    đã bị người dùng yêu cầu bỏ ở mọi skill. Test này chặn việc tự thêm lại.
    """
    mgr = get_skill_manager()
    mgr.reload()
    assert not hasattr(mgr.get_skill("try-on-image-prompter"), "policy_clause")

    for path in SKILLS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            # Nhắc tới trong văn xuôi ("không chèn dòng [POLICY COMPLIANCE]") là hợp lệ;
            # chỉ cấm dòng thực sự được chèn vào prompt.
            if stripped.startswith("[POLICY COMPLIANCE]"):
                raise AssertionError(f"{path.name} còn chèn clause: {stripped[:80]}")


def test_skill_templates_start_with_content_not_clause():
    """Template trong SKILL.md phải mở đầu bằng mô tả, không bằng clause."""
    for path in SKILLS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"```text\n(.*?)\n```", text, re.DOTALL):
            body = block.strip()
            if not body:
                continue
            assert not body.lower().startswith("[policy compliance]"), path.name


def test_obsolete_push_ui_skills_removed():
    """Hai skill 'đẩy văng cột UI' đã bị khai tử — cột UI không được nằm trong pixel nữa."""
    assert not (SKILLS / "lookbook-video-1-push.md").exists()
    assert not (SKILLS / "lookbook-video-2-showcase.md").exists()


def test_plate_mode_lives_in_tryon_skill():
    """Chế độ plate từng là skill riêng `lookbook-model-only-prompter` — đã gộp vào §2.5
    của skill try-on vì nó chỉ là try-on với một ảnh + studio thay thế.

    Ba thứ phải còn, nếu không plate sinh ra sẽ hỏng pipeline tách lớp: bối cảnh thay
    (không kế thừa), negative nền sạch, và đầu vào một ảnh.
    """
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "2.5" in text
    section = text.split("Chế độ Plate")[-1][:4000].lower()
    assert "chỉ 1 ảnh" in section or "chỉ một ảnh" in section, "thiếu ràng buộc một ảnh"
    assert "no props" in section and "no other people" in section
    assert "no progress bar" in section and "no product cards" in section
    assert "seamless warm light beige studio" in section, "thiếu câu thay bối cảnh"


def test_plate_mode_does_not_require_second_image():
    """Template plate không được nhắc `<<garment>>` / `<<background>>` trong khối code —
    node plate chỉ có một ảnh, nhắc tới ảnh không tồn tại thì agent tự ứng biến mỗi lần một kiểu."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    section = text.split("**2.5.1 Đầu vào chỉ có một ảnh**")[-1][:800]
    blocks = re.findall(r"```text\n(.*?)\n```", section, re.DOTALL)
    assert blocks, "thiếu khối code mẫu câu mở đầu cho plate"
    opening = blocks[0]
    assert "<<model>>" in opening
    assert "<<garment>>" not in opening and "<<background>>" not in opening


def test_image_board_skill_removed():
    """Board NABI chưa từng dùng được cho video (chữ dính pixel, phải crop 1/3 khung), và
    cột item giờ do lớp dựng lo. File skill đã xoá — giữ lại thì agent có hai nguồn quy
    tắc ảnh bìa mâu thuẫn nhau."""
    assert not (SKILLS / "lookbook-thumbnail-prompter.md").exists()


def test_cutout_skill_rejects_human_seg():
    """Skill sheet phải chỉ rõ vì sao không tách nền trực tiếp từ ảnh lifestyle."""
    text = (SKILLS / "lookbook-item-cutout-prompter.md").read_text(encoding="utf-8")
    assert "human_seg" in text.lower()
    assert "rembg" in text.lower()
    assert "no person" in text.lower()


def test_cutout_skill_has_one_output_only():
    """Skill chỉ còn coordinate sheet — không còn template plate hay phạm vi để chọn.

    Từng có bốn đường ra (`top`/`bottom`/`full_set`/`coordinate_sheet`) và người dùng phải
    chọn đúng trước khi bấm AI Prompt. Bốn đường sinh ra bốn template, và agent chọn nhầm
    template là chuyện có thật.
    """
    text = (SKILLS / "lookbook-item-cutout-prompter.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
    openers = [b.strip() for b in blocks if b.strip()]
    assert any(o.startswith("Editorial fashion coordinate sheet") for o in openers)
    # Không còn template flat-lay của plate.
    assert not any("Flat-lay product photograph" in o for o in openers)
    assert not any("Flat-lay product arrangement" in o for o in openers)
    # Không còn khái niệm phạm vi.
    assert "item_scope" not in text
    assert "full_set" not in text


def test_coordinate_sheet_keeps_typography_and_drops_plate_negatives():
    """Sheet là ngoại lệ có chủ đích: có chữ, nhiều món, **không** qua rembg.

    Hai lỗi phá sheet ngay: (1) bê negative của ảnh plate (`no text`, `no collage`,
    `no grid`, `no multiple items`) — xoá đúng thứ sheet cần; (2) quên khoá chi tiết lạ
    nên model "sửa" keyhole / gấu xẻ / cạp trễ. Test khoá cả hai, và khoá luôn palette 5 ô.
    """
    text = (SKILLS / "lookbook-item-cutout-prompter.md").read_text(encoding="utf-8")
    block = next(
        b for b in re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
        if b.strip().startswith("Editorial fashion coordinate sheet")
    )
    for needle in ("FIDELITY LOCKS", "COLOR PALETTE", "DETAIL", "01 /"):
        assert needle in block, f"sheet thiếu '{needle}'"
    assert "no person" in block.lower()

    negative = block.split("Negative:", 1)[-1].lower()
    for banned in ("no text", "no collage", "no grid", "no multiple items"):
        assert banned not in negative, f"negative sheet chứa '{banned}' — sẽ xoá chính sheet"


def _prompt_templates(name: str) -> list[str]:
    """Khối ```text trong skill là prompt mẫu — thứ thực sự được gửi lên Flow."""
    text = (SKILLS / name).read_text(encoding="utf-8")
    return re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)


def test_prompt_templates_avoid_the_unsafe_generation_trigger_word():
    """Họ từ `brand` làm Flow từ chối cả request, kể cả trong câu phủ định.

    Đo trên server thật (2026‑11‑12, profile `aaaaa`, Nano Banana Pro, cùng prompt + cùng
    ảnh tham chiếu): `Avoid: no brand logo.` và `Avoid: no brand.` → REJECT
    `PUBLIC_ERROR_UNSAFE_GENERATION`; `Avoid: no logo.` và `Avoid: no watermark.` → 200 OK.
    Prompt try-on thật, chỉ đổi hai từ `branding`, cũng từ REJECT thành 200 OK.

    Chỉ kiểm tra **khối prompt mẫu**, không kiểm tra văn xuôi: skill phải được phép viết
    "đừng dùng họ từ brand" và liệt kê nó trong danh sách từ vựng để tra.
    """
    for name in ("try-on-image-prompter.md", "lookbook-item-cutout-prompter.md"):
        blocks = _prompt_templates(name)
        assert blocks, f"{name} không có khối prompt mẫu nào"
        for block in blocks:
            hits = re.findall(r"\b(?:brand|brands|branded|branding)\b", block, re.IGNORECASE)
            assert not hits, f"{name}: prompt mẫu còn họ từ 'brand' {hits} ⇒ Flow chặn request"

    tpl = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "no added marks beyond what the reference garment actually carries" in tpl


def _skill_example_prompts() -> list[str]:
    """Prompt mẫu trong skill, đọc từ khối ```text bắt đầu bằng câu camera.

    Nguồn sự thật của prompt là `motion_prompt.beats_to_prompt()`; khối trong skill là **bản sao**
    để người đọc thấy kết quả. `test_skill_example_matches_renderer` khoá hai bên khớp nhau.
    """
    text = (SKILLS / "lookbook-video-prompter.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
    return [b.strip() for b in blocks if b.strip().startswith(("Camera", "Continuing"))]


def test_video_skill_templates_survive_sanitizer():
    """Prompt mẫu trong skill phải đi qua sanitize ở cả 2 chế độ mà không bị xoá nội dung."""
    prompts = _skill_example_prompts()
    assert len(prompts) == 2, f"expected 2 clip prompts, got {len(prompts)}"

    for p in prompts:
        for mode in (False, True):
            out = sanitize_video_prompt(p, aggressive=mode)
            assert out.strip(), f"prompt bị xoá sạch (aggressive={mode})"
            # Không mất quá 15% nội dung
            assert len(out) > len(p) * 0.85, f"mất nội dung (aggressive={mode}): {out!r}"
            # Chuyển động cốt lõi phải còn
            assert "camera" in out.lower()
        # Không vượt ngân sách của skill (`prompt_lint.VIDEO_MAX_WORDS`)
        from src.Workflows.prompt_lint import VIDEO_MAX_WORDS

        assert len(p.split()) <= VIDEO_MAX_WORDS, len(p.split())


def test_skill_example_matches_renderer():
    """Khối mẫu trong skill phải **bằng đúng** output của renderer trên script mẫu.

    Trước đây skill chứa template viết tay (`lifts the woven tote`, `halter neckline`) trỏ vào một bộ
    đồ khác hoàn toàn, và không ai phát hiện vì agent không thấy script. Giữ hai bên khớp bằng test
    để lần lệch sau bị bắt ngay.
    """
    from src.Workflows.motion_prompt import beats_to_prompt
    from src.Workflows.script_contract import load_default_script

    script = load_default_script()
    assert script is not None
    expected = [beats_to_prompt(clip) for clip in script.clips]
    assert _skill_example_prompts() == expected


def test_video_skill_avoids_filtered_phrases():
    """Skill phải dạy tránh đúng những cụm bị bộ lọc viết lại — kiểm tra ở phần template,
    không kiểm tra ở phần bảng cảnh báo (bảng có nhắc tới chúng để dẫn tránh)."""
    templates = _skill_example_prompts()
    assert templates
    for tpl in templates:
        for bad in FORBIDDEN_VIDEO_PHRASES:
            assert bad not in tpl.lower(), f"template chứa cụm bị lọc: {bad}"
        for hdr in FORBIDDEN_VIDEO_HEADERS:
            assert hdr not in tpl, f"template chứa header bị cắt: {hdr}"


def test_video_skill_avoids_filtered_phrases():
    """Skill phải dạy tránh đúng những cụm bị bộ lọc viết lại — kiểm tra ở phần template,
    không kiểm tra ở phần bảng cảnh báo (bảng có nhắc tới chúng để dặn tránh)."""
    text = (SKILLS / "lookbook-video-prompter.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)
    templates = [b for b in blocks if b.strip().startswith(("Camera", "Continuing"))]
    assert templates
    for tpl in templates:
        for bad in FORBIDDEN_VIDEO_PHRASES:
            assert bad not in tpl.lower(), f"template chứa cụm bị lọc: {bad}"
        for hdr in FORBIDDEN_VIDEO_HEADERS:
            assert hdr not in tpl, f"template chứa header bị cắt: {hdr}"


def test_gemini_parser_reads_skill_output_shape():
    """Output của skill là 2 code block riêng biệt — parser Pattern C phải đọc ra đúng 2 prompt.

    Ghi chú: header dạng `[Video Prompt 2]` (có ngoặc vuông) làm parser Pattern A để lại
    rác `[` ở cuối prompt 1, nên skill cố ý KHÔNG dùng header đó.
    """
    p1 = (
        "Camera pushes in slowly at natural real-time speed. The model holds steady eye contact "
        "with the lens for three seconds, then turns a full 360 degrees in place."
    )
    p2 = (
        "Continuing from that pose, the model angles forty-five degrees and returns to the lens. "
        "Camera drifts closer on the same axis as the model settles into the opening stance."
    )
    raw = f"```text\n{p1}\n```\n\n```text\n{p2}\n```\n"
    a, b = parse_gemini_video_prompts(raw)
    assert a.strip() == p1
    assert b.strip() == p2
    # Không được sót ký tự rác từ header
    assert "[" not in a and "[" not in b


def test_tryon_skill_does_not_emit_video_prompts():
    """Skill này chỉ sinh prompt ảnh. Prompt video thuộc `lookbook-video-prompter`; để lẫn
    vào đây thì agent có hai nguồn quy tắc video và sẽ viết theo bộ cũ
    (`glances over her shoulder`, header mốc thời gian) — đúng thứ sanitizer cắt nát."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "TÍNH NĂNG 2" not in text
    assert "VIDEO PROMPT" not in text
    # Không được còn template clip nào
    for opener in ("Camera pushes in", "Continuing from that pose"):
        assert opener not in text, f"còn template video: {opener}"
    # Nhưng phải trỏ sang skill video để agent không tự nghĩ ra
    assert "lookbook-video-prompter" in text


# --------------------------------------------------------------------------- #
# Height & Proportion Optimization — khối cố định của skill try-on
# --------------------------------------------------------------------------- #

def _tryon_blocks() -> list[str]:
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    return re.findall(r"```text\n(.*?)\n```", text, re.DOTALL)


def _tryon_template() -> str:
    return next(
        b for b in _tryon_blocks()
        if b.strip().startswith("Try-on photograph")
    )


def test_tryon_template_embeds_height_block():
    """Template Bản 2 phải chèn nguyên văn khối Height — nếu chỉ tài liệu hoá mà quên
    nhúng vào template thì agent copy template sẽ mất khối."""
    tpl = _tryon_template()
    assert "[HEIGHT & PROPORTION OPTIMIZATION]" in tpl
    assert "[END HEIGHT & PROPORTION OPTIMIZATION]" in tpl
    # Đủ 7 nhóm yếu tố
    for facet in (
        "Body Proportion:", "Camera Perspective:", "Lens:",
        "Composition:", "Posture:", "Visual Silhouette:", "Anatomical Integrity:",
    ):
        assert facet in tpl, f"khối Height thiếu nhóm {facet}"


def test_tryon_template_keeps_quantitative_anchors():
    """Ba con số định lượng là phần mạnh nhất của khối Height. Mất chúng thì model tự
    chọn tỷ lệ khung và tiêu cự, ảnh trong cùng bộ sẽ lệch cỡ nhau.

    `76%` và `50mm` được hiệu chuẩn từ batch 8 ảnh thật trong `prompt-skills/poses/results/`
    (xem `poses_reference.md` §4). Bản trước dùng `82-85%` + `70mm`: occupancy đó quá sát mép
    nên cắt gót ở các pose có gối nâng / mũi chân duỗi, còn 70mm nén dẹt các pose có tay giơ cao.
    Đừng đổi ngược lại nếu không chạy lại một batch kiểm chứng.
    """
    tpl = _tryon_template().lower()
    assert "76 percent" in tpl, "thiếu mốc 76% chiều cao khung"
    assert "horizon level" in tpl, "thiếu mốc horizon level"
    assert "50mm" in tpl, "thiếu khoá tiêu cự 50mm"
    # Chống trôi ngược về cặp số cũ
    assert "82-85 percent" not in tpl and "82–85 percent" not in tpl
    assert "70mm" not in tpl


def test_tryon_template_has_no_leg_collapse_instructions():
    """Cụm 'front foot slightly across the body line' từng làm hai chân giao nhau trong
    khung 2D ⇒ đùi chồng thành một khối. Template không được quay lại cụm đó."""
    tpl = _tryon_template().lower()
    for bad in ("across the body line", "crossed legs, no", "one leg in front"):
        # "across the body line" và "crossed legs" chỉ được xuất hiện trong negative
        if bad in tpl:
            idx = tpl.index(bad)
            assert "no " in tpl[max(0, idx - 6):idx], f"'{bad}' xuất hiện ngoài negative"


def test_tryon_template_constraints_cover_legs_and_garment():
    """Khối chặn lỗi phải gom đủ 4 nhóm: UI, phối cảnh, giải phẫu, chân + garment drift.

    Đọc theo marker `constraints:` chứ không phải `negative:` — Flow không có trường negative
    (`docs/api_specs/flow_create_image.md` §3.1), nên từ V3 khối này là câu khẳng định.
    """
    tpl = _tryon_template().lower()
    assert "constraints:" in tpl, "template thiếu khối Constraints"
    tail = tpl.split("constraints:")[-1]
    for needle in (
        "overlapping thighs", "crossed legs", "legs merging",
        "high-angle", "wide-angle", "artificial body stretching",
        "garment redesign", "altered facial identity",
    ):
        assert needle in tail, f"Constraints thiếu '{needle}'"


def test_height_block_never_orders_anatomy_redraw():
    """Khối Height chỉ được đổi *cách nhìn*. Nếu nó chứa lệnh kéo giãn cơ thể thì nó
    mâu thuẫn với Identity Lock và làm vóc dáng lệch khỏi Ảnh 1."""
    from src.Workflows.prompt_lint import lint_image_prompt

    tpl = _tryon_template()
    result = lint_image_prompt(tpl)
    anatomy = [w for w in result.warnings if w.code == "anatomy_rewrite"]
    assert not anatomy, anatomy
    perspective = [w for w in result.warnings if w.code == "unflattering_perspective"]
    assert not perspective, perspective


def test_tryon_template_passes_image_lint():
    """Template phải sạch linter ảnh — nếu không, skill tự dạy điều linter báo lỗi."""
    from src.Workflows.prompt_lint import lint_image_prompt

    result = lint_image_prompt(_tryon_template())
    assert result.ok, [w.to_dict() for w in result.warnings]
    assert not [w for w in result.warnings if w.code == "missing_height_block"]


def test_height_block_header_variants_recognised():
    """Skill và mẫu người dùng đặt tên khối khác nhau. Linter phải nhận mọi biến thể,
    nếu không prompt đúng vẫn bị báo 'thiếu khối'."""
    from src.Workflows.prompt_lint import HEIGHT_BLOCK_RE

    for header in (
        "[HEIGHT & PROPORTION OPTIMIZATION]",
        "[POSE & HEIGHT PERCEPTION OPTIMIZATION V4]",
        "[HEIGHT PERCEPTION OPTIMIZATION]",
        "[END POSE & HEIGHT PERCEPTION OPTIMIZATION]",
    ):
        assert HEIGHT_BLOCK_RE.search(header), header


def test_leg_pose_lint_flags_old_skill_phrase():
    """Cụm cũ 'across the body line' chính là nguyên nhân làm hai chân giao nhau.
    Linter phải bắt nó, nhưng KHÔNG bắt cụm thay thế đúng."""
    from src.Workflows.prompt_lint import lint_image_prompt

    bad = (
        "Try-on photograph. [HEIGHT & PROPORTION OPTIMIZATION] "
        "the front foot placed forward and slightly across the body line."
    )
    codes = {w.code for w in lint_image_prompt(bad).warnings}
    assert "leg_pose" in codes

    good = (
        "Try-on photograph. [HEIGHT & PROPORTION OPTIMIZATION] "
        "one foot placed slightly forward without crossing the body's vertical centreline."
    )
    codes = {w.code for w in lint_image_prompt(good).warnings}
    assert "leg_pose" not in codes, "cụm đúng bị báo nhầm"


def test_tryon_skill_defines_two_pose_modes():
    """Skill phải nêu cả Mode A (ba phần tư) và Mode B (gần trực diện cho garment
    fidelity) — nếu chỉ còn một mode thì agent sẽ ép mọi ảnh về cùng một dáng."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "Mode A" in text and "Mode B" in text
    assert "5–10" in text or "five to ten" in text
    assert "30–45" in text or "thirty to forty-five" in text
    # Hướng dẫn chọn mode phải nêu tiêu chí, không chỉ nêu tên
    assert "chi tiết chỉ đọc được từ mặt trước" in text or "garment" in text.lower()


def test_tryon_skill_offers_concrete_pose_library():
    """Mode A/B chỉ là ngân sách xoay thân. Nếu skill không trỏ sang pose thật trong
    `pose_assets.json`, agent phải tự nghĩ dáng mỗi lần ⇒ không tái lập được kết quả."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "2.2.1a" in text, "thiếu mục chọn pose cụ thể"
    assert "pose_assets.json" in text
    assert "prompt_core" in text

    ids = {p["id"] for p in _pose_assets()["poses"]}
    # Skill trích dẫn ID dạng ngắn (`pose_12`) cho gọn bảng; chấp nhận cả dạng đầy đủ.
    short = {i.split("_")[0] + "_" + i.split("_")[1] for i in ids}
    referenced = set(re.findall(r"\bpose_(?:0[1-9]|1[0-6])(?:_[a-z0-9_]+)?", text))
    assert referenced, "skill không nêu pose ID nào"
    unknown = {r for r in referenced if r not in ids and r not in short}
    assert not unknown, f"skill trỏ tới pose không tồn tại: {unknown}"


def test_tryon_skill_excludes_unusable_poses():
    """Có pose đẹp nhưng phá khả năng đọc trang phục (tay che ngực, gối nâng che ống quần).
    Skill phải ghi rõ danh sách loại trừ, nếu không agent sẽ chọn theo 'đẹp' thay vì 'hợp'."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    excluded_block = text.split("Loại trừ")[-1][:1200]
    for pose_id in ("pose_10", "pose_11", "pose_14", "pose_15"):
        assert pose_id in excluded_block, f"{pose_id} phải nằm trong danh sách loại trừ"


def test_tryon_skill_reconciles_mode_b_with_ban_list():
    """pose_12 / pose_05 / pose_02 mô tả thân vuông góc 0°, nhưng bảng CẤM lại cấm
    `zero-degree body rotation`. Skill phải nói rõ phải sửa gì trước khi chèn, nếu không
    agent hoặc bê nguyên 0° (vi phạm luật của chính skill) hoặc bỏ luôn pose đó."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    section = text.split("Bắt buộc khi dùng nhóm Mode B")[-1][:900]
    assert "five to ten degrees off the camera axis" in section
    assert "slight outward angle" in section


def test_tryon_mode_b_poses_really_declare_square_stance():
    """Nếu dữ liệu pose đổi và không còn cụm vuông góc, cảnh báo hoà giải ở trên thành
    thừa và sẽ khiến agent sửa pose vô cớ."""
    poses = {p["id"]: p for p in _pose_assets()["poses"]}
    for short in ("pose_12", "pose_05", "pose_02"):
        core = next(v["prompt_core"].lower() for k, v in poses.items() if k.startswith(short))
        assert "square" in core or "frontal" in core, (
            f"{short} không còn mô tả dáng vuông góc — cập nhật lại §2.2.1a"
        )


def test_tryon_and_pose_library_share_the_same_lock():
    """Hai skill dùng chung một bộ thông số máy. Nếu lệch, người dùng ghép ảnh từ hai
    nguồn sẽ ra bộ lookbook có người mẫu to nhỏ khác nhau."""
    tryon = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8").lower()
    macro = _pose_assets()["consistency_lock"]["height_anchor"].lower()

    for token in ("76 percent", "50mm", "waist level", "three-degree", "horizon level"):
        assert token in tryon, f"try-on thiếu '{token}'"
        assert token in macro, f"macro thiếu '{token}'"

    # Không được trôi ngược về cặp số cũ của bản 82-85% / 70mm
    assert "82-85 percent" not in tryon and "82–85 percent" not in tryon
    assert "70mm" not in tryon


def test_pose_assets_helper_is_shared():
    """Helper đọc JSON dùng chung, tránh mỗi test tự parse một kiểu."""
    data = _pose_assets()
    assert data["schema_version"] == 2
    assert len(data["poses"]) == 16


def test_height_block_documents_forbidden_substitutions():
    """Bảng cấm → thay thế là thứ agent dựa vào khi người dùng đòi 'cho cao hơn'.
    Mất bảng thì agent sẽ tự nghĩ ra cụm kéo giãn."""
    text = (SKILLS / "try-on-image-prompter.md").read_text(encoding="utf-8")
    assert "2.3.1" in text
    for banned, safe in (
        ("make her look taller", "emphasize vertical proportions"),
        ("elongated legs", "long unbroken leg line"),
        ("worm's-eye view", "subtle low-angle perspective"),
    ):
        assert banned in text.lower(), banned
        assert safe in text.lower(), safe


# --------------------------------------------------------------------------- #
# Sanitizer regression — bug "Camera & Realism" nuốt phần đuôi prompt
# --------------------------------------------------------------------------- #

def test_sanitizer_keeps_tail_after_camera_realism_header():
    """`clean` bị join thành 1 dòng, nên regex `.*$` từng xoá sạch mọi thứ sau header.

    Nếu bug quay lại, prompt gửi Flow sẽ rỗng hoặc mất toàn bộ phần chuyển động.
    """
    src = "Camera & Realism: x. The model turns a full 360 degrees in place."
    for mode in (False, True):
        out = sanitize_video_prompt(src, aggressive=mode)
        assert "360 degrees" in out, f"mất phần đuôi prompt (aggressive={mode}): {out!r}"
        assert out.strip(), f"prompt rỗng (aggressive={mode})"


def test_sanitizer_strips_timecode_labels_but_keeps_content():
    cases = [
        ("0s - 3s (Hook): The model holds eye contact. 3s-8s (Turn): The model turns.",
         ["holds eye contact", "turns"]),
        ("Timeline: 0-1s: stand still. 1-2s: turn slowly.", ["stand still", "turn slowly"]),
        ("[2s-5s] The model lifts the hem.", ["lifts the hem"]),
    ]
    for src, must_keep in cases:
        out = sanitize_video_prompt(src, aggressive=False)
        for frag in must_keep:
            assert frag in out, f"mất '{frag}' từ {src!r} → {out!r}"
        assert "Hook" not in out
        assert "[2s-5s]" not in out


# --------------------------------------------------------------------------- #
# Prompt linter
# --------------------------------------------------------------------------- #

def test_linter_flags_ui_vocabulary_and_rewrites():
    from src.Workflows.prompt_lint import lint_video_prompt

    bad = (
        "The model pushes the sidebar card away and she looks at the camera. "
        "Camera pushes in slowly at natural real-time speed across the studio floor."
    )
    result = lint_video_prompt(bad)
    codes = {w.code for w in result.warnings}
    assert "ui_vocabulary" in codes
    assert "pronoun" in codes
    assert "aggressive_rewrite" in codes
    assert not result.ok


def test_linter_word_boundary_does_not_match_cardigan():
    from src.Workflows.prompt_lint import lint_video_prompt

    ok = (
        "Camera drifts closer on the same axis as the model lifts the light cardigan "
        "higher on the shoulder, eyes settling downward once, then returning to the lens "
        "with natural blinks and quiet breathing at real-time speed."
    )
    result = lint_video_prompt(ok)
    assert not [w for w in result.warnings if w.code == "ui_vocabulary"], result.warnings


def test_linter_ignores_ui_terms_inside_negative_clause():
    """Prompt video buộc phải nói điều KHÔNG được xảy ra, mà payload Flow không có trường negative.

    Nếu linter phạt cả mệnh đề cấm thì nó đang phạt đúng câu skill yêu cầu viết, và người dùng sẽ
    bỏ mệnh đề cấm để hết đỏ — mất luôn ràng buộc duy nhất chống cắt cảnh.
    """
    from src.Workflows.prompt_lint import lint_video_prompt

    body = "Camera pushes in slowly at natural real-time speed."
    banned_but_negated = (
        f"{body} The model stands still and holds eye contact. "
        "One continuous shot, staying inside the frame, with no cut, no added lettering or printed graphics."
    )
    assert not [w for w in lint_video_prompt(banned_but_negated).warnings if w.code == "ui_vocabulary"]

    still_caught = f"{body} The model turns with a banner on screen."
    assert [w for w in lint_video_prompt(still_caught).warnings if w.code == "ui_vocabulary"]


def test_linter_budget_matches_skill():
    """Ngân sách từ của linter và skill phải cùng một con số, nếu không agent bị dạy hai chuẩn."""
    from src.Workflows.prompt_lint import VIDEO_MAX_WORDS

    text = (SKILLS / "lookbook-video-prompter.md").read_text(encoding="utf-8")
    assert f"trần cứng **{VIDEO_MAX_WORDS}**" in text or f"Trần cứng **{VIDEO_MAX_WORDS}**" in text


def test_script_motion_prompts_are_lint_clean():
    """Mọi motion_prompt trong script mẫu phải pass linter — nếu không, script tự mâu thuẫn."""
    import json

    from src.Workflows.prompt_lint import lint_script_prompts

    script = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    result = lint_script_prompts(script)
    assert result["ok"], result


def test_script_satisfies_schema():
    """Script mẫu phải hợp lệ theo JSON Schema — delivery đọc thẳng file này."""
    import json

    import jsonschema

    schema = json.loads((ROOT / "configs" / "lookbook_script.schema.json").read_text(encoding="utf-8"))
    script = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=script, schema=schema)


def test_script_timeline_fits_inside_clips():
    """shots[].clip_offset_s + duration_s không được vượt quá duration_s của clip."""
    import json

    script = json.loads((ROOT / "configs" / "lookbook_script.json").read_text(encoding="utf-8"))
    clip_dur = {c["id"]: c.get("duration_s", 8) for c in script["clips"]}
    for shot in script["shots"]:
        end = shot["clip_offset_s"] + shot["duration_s"]
        assert end <= clip_dur[shot["clip"]] + 1e-6, (
            f"shot {shot['id']} kết thúc ở {end}s nhưng {shot['clip']} chỉ dài "
            f"{clip_dur[shot['clip']]}s"
        )

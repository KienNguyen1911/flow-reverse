"""Prompt Agent — Orchestrates dynamic prompt generation for canvas nodes using local AI agents (`agy`/`pi`)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .local_agent_runner import LocalAgentRunner, get_agent_runner
from .media_service import resolve_input_path
from .script_contract import LookbookScript, ScriptError, load_default_script, load_script
from .skill_manager import PromptSkill, get_skill_manager

ROOT = Path(__file__).resolve().parents[2]

#: Phạm vi món đồ của node ảnh sản phẩm. Skill cutout mặc định bắt "chỉ một món", nên
#: phải nói rõ món nào — không thì model tự chọn vật thể nổi bật nhất (thường là chiếc áo).
#: `full_set` là ngoại lệ duy nhất: người dùng chủ động muốn cả bộ trên một ảnh.
ITEM_SCOPES: dict[str, dict[str, str]] = {
    "top": {
        "label": "chỉ ÁO",
        "rule": (
            "Isolate the UPPER garment only (top / shirt / blouse / camisole / jacket). "
            "Exclude every bottom piece (skirt, shorts, trousers): they must not appear "
            "in the image at all."
        ),
        "exclude": "bottoms, skirt, shorts, trousers, and any second garment",
    },
    "bottom": {
        "label": "chỉ QUẦN / VÁY",
        "rule": (
            "Isolate the LOWER garment only (skirt / shorts / trousers). Exclude every top "
            "piece (shirt, camisole, cardigan): they must not appear in the image at all."
        ),
        "exclude": "tops, shirt, camisole, cardigan, and any second garment",
    },
    "full_set": {
        "label": "CẢ BỘ (nhiều món)",
        "rule": (
            "This is the ONLY case where the skill's single-garment rule is overridden: the "
            "user wants the COMPLETE SET on one plate. Lay every piece of the outfit together "
            "as one coordinated flat-lay — the top and the bottom arranged next to each other "
            "(top above, bottom below, or side by side), all pieces fully visible and not "
            "overlapping. Same background, lighting and framing for the whole set."
        ),
        "exclude": "background scenery, furniture, props",
    },
}


@dataclass
class NodePromptTask:
    node_id: str
    node_type: str  # "image" | "video"
    upstream_media_urls: list[str]
    skill_id: Optional[str] = None
    custom_hint: Optional[str] = None
    is_video_continuation: bool = False
    agent: Optional[str] = None
    model: Optional[str] = None
    # Ngữ cảnh cắt ra từ configs/lookbook_script.json (không bắt buộc)
    clip_id: Optional[str] = None       # "clip1" | "clip2" | ...
    clip_role: Optional[str] = None     # "hook" | "showcase" | "detail"
    item_id: Optional[str] = None       # "item_1" khi sinh ảnh cutout
    #: Node ảnh được đánh dấu là **ảnh sản phẩm** ⇒ dùng skill cutout, và `item_name` là
    #: tên món người dùng đặt (ngữ cảnh duy nhất khi không có ảnh tham chiếu).
    is_item: bool = False
    item_name: Optional[str] = None
    #: Phạm vi món đồ người dùng chọn trên node ảnh sản phẩm:
    #: `"top"` (chỉ áo) | `"bottom"` (chỉ quần/váy) | `"full_set"` (cả bộ, ngoại lệ của
    #: quy tắc "một món" trong skill cutout). `None` ⇒ giữ nguyên hành vi cũ.
    item_scope: Optional[str] = None
    #: Node ảnh sinh **first frame cho video** ⇒ agent dùng chế độ plate của skill try-on
    #: (§2.5): chỉ một ảnh đầu vào, bối cảnh studio thay thế, negative thêm nhóm nền sạch.
    #: Trước đây là skill riêng `lookbook-model-only-prompter`; đã gộp vào try-on.
    plate_mode: bool = False
    #: Đường dẫn script (mặc định `configs/lookbook_script.json` nếu tồn tại). Khi có,
    #: agent nhận đúng brief của clip + các shot rơi vào clip đó để viết prompt khớp phim.
    script_path: Optional[str] = None


@dataclass
class NodePromptResult:
    node_id: str
    prompt: str
    skill_id: str
    agent: str
    upstream_files: list[str]
    elapsed_s: float
    raw_response: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class PromptAgent:
    """Intelligent prompt director for Flow Bench visual workflow nodes."""

    def __init__(self, runner: Optional[LocalAgentRunner] = None):
        self.runner = runner or get_agent_runner()
        self.skill_mgr = get_skill_manager()

    def resolve_upstream_files(self, urls: list[str]) -> list[Path]:
        """Convert /api/uploads/..., /api/assets/..., /api/node/files/... to local existing file paths."""
        paths: list[Path] = []
        for u in urls:
            if not u:
                continue
            resolved = resolve_input_path(u)
            if resolved.is_file():
                paths.append(resolved)
        return paths

    #: ID của skill đã gộp vào `try-on-image-prompter`. Project lưu trên đĩa và template
    #: canvas cũ vẫn ghi ID này, nên phải map chứ không để rơi về nhánh mặc định — rơi
    #: xuống đó sẽ mất cờ plate_mode và agent lại viết prompt cần 2 ảnh.
    LEGACY_SKILL_ALIASES = {"lookbook-model-only-prompter": "try-on-image-prompter"}

    def select_skill(self, task: NodePromptTask) -> PromptSkill:
        """Find matching skill or pick best default.

        Thứ tự ưu tiên: skill chỉ định rõ → role của clip trong script → loại node.
        Không bao giờ rơi sang một skill khác loại (ảnh ↔ video chéo nhau).
        """
        if task.skill_id:
            sid = task.skill_id.strip().lower()
            if sid in self.LEGACY_SKILL_ALIASES:
                task.plate_mode = True
                sid = self.LEGACY_SKILL_ALIASES[sid]
            s = self.skill_mgr.get_skill(sid)
            if s:
                return s

        if task.node_type == "video":
            # Mọi clip video đều dùng chung skill motion-only.
            s = self.skill_mgr.get_skill("lookbook-video-prompter")
            if s:
                return s
        else:
            if task.item_id or task.is_item:
                # Ảnh sản phẩm phẳng trên nền trơn. `is_item` là cờ người dùng tick trên
                # node; `item_id` là kiểu cũ khi còn gắn cứng vào `items[]` của script.
                s = self.skill_mgr.get_skill("lookbook-item-cutout-prompter")
                if s:
                    return s
            hint = (task.custom_hint or "").lower()
            if "plate" in hint or task.clip_role:
                # Ảnh first frame cho video lookbook. Không còn skill riêng: chế độ plate
                # là §2.5 của skill try-on, nên vẫn trả về đúng skill đó. Cờ này chỉ để
                # `format_agent_instruction` nói rõ chế độ cho agent, tránh nó lấy 2 ảnh.
                task.plate_mode = True
            s = self.skill_mgr.get_skill("try-on-image-prompter")
            if s:
                return s

        # Fallback: skill cùng loại đầu tiên, tránh trả về skill khác loại
        for s in self.skill_mgr.list_skills():
            if task.node_type == "video" and "video" in s.id:
                return s
            if task.node_type != "video" and "video" not in s.id:
                return s

        raise RuntimeError("Không tìm thấy skill nào trong thư mục prompt-skills/.")

    def resolve_item_scope(self, task: NodePromptTask) -> Optional[tuple[str, dict[str, str]]]:
        """Phạm vi tách món đồ đang áp dụng cho task, `None` khi không liên quan.

        Chỉ node ẢNH đánh dấu `is_item` mới có phạm vi — video không tách món. Giá trị
        lạ (dữ liệu cũ, gõ tay) bị coi như không có, để không đổi hành vi cũ.
        """
        if task.node_type == "video" or not task.is_item:
            return None
        key = (task.item_scope or "").strip().lower()
        spec = ITEM_SCOPES.get(key)
        return (key, spec) if spec else None

    def format_agent_instruction(
        self,
        task: NodePromptTask,
        skill: PromptSkill,
        upstream_files: list[Path],
    ) -> str:
        """Build high-context prompt instruction for the local agent (agy / pi)."""
        rel_files = []
        for p in upstream_files:
            try:
                rel_files.append(str(p.relative_to(ROOT)).replace("\\", "/"))
            except ValueError:
                rel_files.append(str(p).replace("\\", "/"))

        is_video = task.node_type == "video"

        # Skill .md là nguồn sự thật duy nhất. Ở đây chỉ bổ sung NGỮ CẢNH NODE
        # (loại node, file upstream, spec cắt ra từ script), không lặp lại quy tắc của skill.
        lines = [
            "Bạn là AI Prompt Director cho workflow Google Flow (Flow Bench).",
            f"Quy chuẩn kỹ năng BẮT BUỘC tuân theo nằm trong file: {skill.file_path}",
            "Đọc kỹ toàn bộ skill dưới đây; nó là nguồn quy tắc duy nhất, đừng tự suy diễn thêm.",
            "",
            "--- NỘI DUNG SKILL QUY CHUẨN ---",
            skill.raw_content,
            "---------------------------------",
            "",
            "--- BỐI CẢNH NODE HIỆN TẠI ---",
            f"- Loại node: {'VIDEO' if is_video else 'ẢNH (IMAGE)'}",
            f"- Mã node: {task.node_id}",
            f"- Skill đang áp dụng: {skill.id}",
        ]

        if task.clip_id or task.clip_role:
            lines.append(
                f"- Clip trong script: id={task.clip_id or '?'}, role={task.clip_role or '?'}"
            )
        if task.plate_mode:
            lines.extend([
                "- **Chế độ PLATE** (ảnh này làm first frame cho node video).",
                "  → Áp §2.5 của skill: giả định chỉ có MỘT ảnh tham chiếu đóng cả vai identity và",
                "    trang phục. Không viết câu nào nhắc tới `Image 2` / `Image 3`.",
                "  → Bối cảnh: LUÔN thay bằng studio trơn §2.5.2, kể cả khi ảnh gốc chụp ngoài trời.",
                "  → Negative: nối thêm nhóm nền sạch §2.5.3 (no props / no other people /",
                "    no progress bar / no banner / no product cards / no catalog strip / no thumbnails).",
                "  → Bố cục: căn giữa trục dọc như khối Height — KHÔNG dùng mẹo lệch phải cũ,",
                "    HyperFrames desktop đã tự canh lớp chữ nên không cần chừa cột trái nữa.",
            ])
        if task.item_id:
            lines.append(f"- Món đồ trong script: {task.item_id}")
        elif task.is_item and task.item_name:
            lines.append(f"- Món đồ cần dựng ảnh sản phẩm: {task.item_name}")

        scope = self.resolve_item_scope(task)
        if scope is not None:
            key, spec = scope
            lines.append(f"- Phạm vi cần tách: **{spec['label']}**.")
            lines.append(f"  → {spec['rule']}")
            lines.append(f"  → Ảnh phải KHÔNG có: {spec['exclude']}.")
            if key == "full_set":
                lines.append(
                    "  → Ngoại lệ có chủ đích: bỏ quy tắc 'một món' của skill; giữ nguyên "
                    "các quy tắc còn lại (nền trơn, cấm người, cấm chữ)."
                )

        # Ngữ cảnh script: shot nào rơi vào clip này, đang nhấn món nào. Đây là thứ
        # trước kia agent không hề biết, nên prompt sinh ra không khớp timeline.
        #
        # Với node ẢNH thường (không phải item, không phải plate) thì KHÔNG nạp: script mô
        # tả một bộ phim khác (`slug`/`title` như "HAVANA DONNA"), agent đọc thấy tên đó rồi
        # viết prompt đúng bộ Donna trong khi ảnh garment là áo lệch vai. Ngữ cảnh duy nhất
        # đáng tin ở đây là pixel của chính các ảnh upstream.
        script = self._load_script_context(task)
        if script is not None and (is_video or task.is_item or task.item_id):
            lines.extend(self._script_context_lines(script, task))
        if is_video and task.is_video_continuation:
            lines.append(
                "- Clip này nối tiếp clip trước: dùng frame cuối của clip trước làm starting frame."
            )

        if rel_files:
            lines.append("- File ảnh upstream đang kết nối vào node này, THEO ĐÚNG THỨ TỰ:")
            for idx, rf in enumerate(rel_files, 1):
                lines.append(f"  {idx}. {rf}")
            if not is_video:
                lines.extend(self._image_role_lines(task, len(rel_files)))
                lines.append(
                    "  => ĐỌC TRỰC TIẾP các file trên (màu sắc, phom dáng, chất liệu vải, chi tiết may mặc) "
                    "để prompt khớp 100% với sản phẩm thật."
                )
        else:
            lines.append("- Node chưa có file upstream; viết prompt tổng quát theo quy chuẩn của skill.")

        if task.custom_hint and task.custom_hint.strip():
            lines.append(f"- Ghi chú bổ sung từ người dùng: \"{task.custom_hint.strip()}\"")

        lines.extend([
            "",
            "--- ĐỊNH DẠNG ĐẦU RA ---",
            "Trả về CHỈ các khối code markdown, mỗi khối một prompt tiếng Anh hoàn chỉnh.",
            "Số khối đúng bằng số clip/món đồ được giao ở trên (1 nếu chỉ có 1).",
            "Không lời chào, không giải thích, không header dạng '[Video Prompt N]'.",
            "```markdown",
            "<prompt tiếng Anh>",
            "```",
        ])

        return "\n".join(lines)

    def _beat_lines(self, clip) -> list[str]:
        """Nhịp của clip, kèm câu prompt đã render sẵn.

        Agent **không được viết lại câu beat**: renderer tất định và gate round-trip sanitizer chỉ có
        giá trị khi đầu vào không đổi giữa các lần chạy. Ở đây đưa cả hai dạng — beat có cấu trúc để
        agent hiểu thứ tự, và prompt đã render để agent thấy đúng câu sẽ gửi Flow.
        """
        from .motion_prompt import MotionPromptError, beats_to_prompt, prompt_warnings

        lines = [f"- Nhịp {clip.duration_s}s của clip này (nguồn: `clips[].beats`):"]
        for idx, beat in enumerate(clip.beats, 1):
            bits = [f"{beat.at_s}–{beat.end_s}s"]
            if beat.holds_gaze:
                bits.append("GIỮ MẮT với ống kính")
            bits.append(beat.action)
            lines.append("  · " + " · ".join(bits))
            if beat.must_not:
                lines.append(f"    cấm: {', '.join(beat.must_not)}")

        try:
            rendered = beats_to_prompt(clip)
        except MotionPromptError as exc:  # script hỏng: báo cho agent, không chặn
            lines.append(f"  → KHÔNG render được prompt từ beats: {exc}")
            return lines

        lines.extend([
            "",
            "  Prompt ĐÃ RENDER từ beats ở trên — dùng nguyên văn, chỉ được sửa khi người dùng yêu cầu:",
            "  ```text",
            f"  {rendered}",
            "  ```",
            "  → KHÔNG đổi thứ tự beat, KHÔNG thêm nhãn giây (`0-2s:` / `[0-2s]`), KHÔNG tả lại "
            "khuôn mặt/trang phục/ánh sáng. Nếu buộc phải sửa, giữ đúng cấu trúc "
            "'For the first … / From the … to the … / In the final …'.",
        ])
        for warn in prompt_warnings(clip, rendered):
            lines.append(f"  → cảnh báo: {warn}")
        return lines


    def _image_role_lines(self, task: NodePromptTask, count: int) -> list[str]:
        """Nói rõ ảnh nào là gì, để agent khỏi đoán theo thứ tự.

        Lỗi thật đã xảy ra: node nối 3 ảnh (model / garment / background) nhưng prompt
        sinh ra lại tả bộ DONNA - tức agent lấy chữ từ ngữ cảnh script thay vì pixel.
        Khi đã bỏ chữ khỏi ngữ cảnh thì phải nói rõ vai trò từng vị trí, nếu không agent
        vẫn có thể hoán đổi model và garment.
        """
        if task.plate_mode:
            return [
                "  → Vai trò ảnh (chế độ PLATE — chỉ MỘT ảnh): Ảnh 1 đóng cả hai vai",
                "     identity (khuôn mặt, dáng) VÀ trang phục. Không có ảnh nào khác.",
            ]
        if count >= 3:
            return [
                "  → Vai trò ảnh: Ảnh 1 = MODEL (identity: mặt, tóc, dáng — giữ nguyên).",
                "     Ảnh 2 = GARMENT (trang phục cần mặc — chép đúng phom, màu, chất liệu).",
                "     Ảnh 3 = BACKGROUND (bối cảnh + ánh sáng — kế thừa).",
                "     Thứ tự này cố định; đừng suy ra vai trò từ tên file hay thứ tự khác.",
            ]
        if count == 2:
            return [
                "  → Vai trò ảnh: Ảnh 1 = MODEL (identity: mặt, tóc, dáng — giữ nguyên).",
                "     Ảnh 2 = GARMENT (trang phục cần mặc — chép đúng phom, màu, chất liệu).",
                "     Không có ảnh bối cảnh riêng: dùng studio trơn ở module Environment của skill,",
                "     KHÔNG kế thừa bối cảnh Ảnh 2 (ảnh Shopee ngoài đường sẽ lọt vào khung).",
            ]
        return [
            "  → Chỉ có MỘT ảnh: nó đóng cả vai model và trang phục.",
            "     Không được nhắc tới `Image 2` / `Image 3`.",
        ]

    def _load_script_context(self, task: NodePromptTask) -> Optional[LookbookScript]:
        """Script để bổ sung ngữ cảnh; không có cũng chạy bình thường."""
        try:
            if task.script_path:
                return load_script(task.script_path)
            return load_default_script()
        except ScriptError:
            return None

    def _script_context_lines(self, script: LookbookScript, task: NodePromptTask) -> list[str]:
        is_video = task.node_type == "video"
        lines = ["", "--- KỊCH BẢN PHIM (nguồn: configs/lookbook_script.json) ---"]
        lines.append(f"- Bộ: {script.slug} — {script.title}")
        lines.append(
            f"- Khung hình {script.canvas.get('width')}×{script.canvas.get('height')} @ "
            f"{script.fps}fps, tổng {script.duration_s}s / {len(script.clips)} clip"
        )

        clip_id = task.clip_id
        if not clip_id and is_video and len(script.clips) == 1:
            clip_id = script.clips[0].id

        if is_video and not clip_id:
            # Trước đây nhánh này im lặng: `clip_id` rỗng + script nhiều clip ⇒ `if is_video and
            # clip_id` không chạy, `elif not is_video` cũng không chạy ⇒ node video chỉ nhận
            # slug/title/fps. Agent không thấy role, shots, chain_from, beats — và vì thế cả hai
            # node video sinh ra cùng một prompt. Nói thẳng ra thay vì để lặng.
            lines.append(
                "- **THIẾU `clip_id`**: không đọc được vai (role), shots, chain_from hay beats của clip. "
                "Chọn clip trên node (Config → Clip trong kịch bản), nếu không prompt sẽ bỏ qua nhịp "
                "0–2s / 2–5s / 5–8s và mục tiêu riêng của từng clip."
            )
            if len(script.clips) > 1:
                lines.append(
                    "  Clip có sẵn: "
                    + ", ".join(f"`{c.id}` ({c.role}, {c.duration_s}s)" for c in script.clips)
                )

        if is_video and clip_id:
            try:
                clip = script.clip(clip_id)
            except ScriptError:
                clip = None
            if clip is not None:
                lines.append(
                    f"- Clip đang viết: {clip.id} — vai **{clip.role}**, "
                    f"{clip.duration_s}s, camera={clip.camera or 'tự do'}"
                )
                if clip.goal:
                    lines.append(f"  → Mục tiêu của clip (dùng để đọc, KHÔNG chép vào prompt): {clip.goal}")
                if clip.beats:
                    lines.extend(self._beat_lines(clip))
                if clip.chain_from:
                    lines.append(
                        f"  → nối tiếp từ `{clip.chain_from}`: mở đầu phải khớp tư thế frame cuối clip trước."
                    )
                shots = script.shots_for_clip(clip.id)
                if shots:
                    lines.append("- Các shot rơi vào clip này (lớp dựng phim lo phần chữ/UI):")
                    for s in shots:
                        bits = [f"{s.clip_offset_s}–{s.end_s}s"]
                        if s.text:
                            bits.append(f'chữ: "{s.text}"')
                        if s.emphasis_item:
                            bits.append(f"nhấn {s.emphasis_item}")
                        lines.append("  · " + " · ".join(bits))
                    lines.append(
                        "  → Prompt video KHÔNG mô tả chữ/caption/card; chỉ mô tả chuyển động "
                        "camera + cơ thể đủ để lớp dựng đặt được chữ lên trên."
                    )
                if task.item_id:
                    try:
                        item = script.item(task.item_id)
                        lines.append(
                            f"- Món đồ đang nhấn: {item.id} — {item.name}"
                            + (f" (callout: {item.callout})" if item.callout else "")
                        )
                    except ScriptError:
                        pass
        elif not is_video and not task.is_item:
            # Ảnh không phải sản phẩm: hoặc plate (first frame cho video), hoặc try-on trả
            # cho khách. Chỉ nhánh plate mới được nói "không chữ/không UI" — nếu gán nhãn
            # đó cho ảnh try-on thường thì agent viết prompt lệch mục tiêu.
            #
            # KHÔNG liệt kê `script.items` ở đây. Danh sách đó là món của *một bộ phim cụ
            # thể*, không phải món đang nằm trong ảnh tham chiếu. Node ảnh của người dùng
            # thường nối ảnh khác hoàn toàn; nhét tên món của script vào thì agent tin chữ
            # hơn pixel và viết ra đúng bộ DONNA dù ảnh garment là áo lệch vai + váy bong
            # bóng. Chỉ nêu món khi chính node đó được gắn `item_id`.
            if task.item_id:
                try:
                    item = script.item(task.item_id)
                    lines.append(f"- Món đồ của script cho node này: {item.id} — {item.name}")
                except ScriptError:
                    lines.append(f"- Món đồ của script cho node này: {task.item_id}")
            if task.plate_mode:
                lines.append(
                    "- Ảnh này là **plate nền** cho video: người mẫu toàn thân, không chữ, không cột UI."
                )
            else:
                lines.append(
                    "- Ảnh này là **ảnh thành phẩm trả cho khách**, không phải plate cho video."
                )

        return lines

    async def generate_prompt_for_node(self, task: NodePromptTask) -> NodePromptResult:
        """Executes prompt generation for a single canvas node."""
        t0 = time.perf_counter()
        skill = self.select_skill(task)
        upstream_files = self.resolve_upstream_files(task.upstream_media_urls)

        instruction = self.format_agent_instruction(task, skill, upstream_files)
        raw_output = await self.runner.run_prompt_instruction(
            instruction=instruction,
            agent=task.agent,
            model=task.model,
        )

        elapsed = round(time.perf_counter() - t0, 2)
        rel_names = [p.name for p in upstream_files]

        return NodePromptResult(
            node_id=task.node_id,
            prompt=raw_output,
            skill_id=skill.id,
            agent=task.agent or self.runner.config.preferred_agent,
            upstream_files=rel_names,
            elapsed_s=elapsed,
            raw_response=raw_output,
        )


# Global agent instance
_prompt_agent: Optional[PromptAgent] = None


def get_prompt_agent() -> PromptAgent:
    global _prompt_agent
    if _prompt_agent is None:
        _prompt_agent = PromptAgent()
    return _prompt_agent

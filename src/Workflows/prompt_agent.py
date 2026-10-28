"""Prompt Agent — Orchestrates dynamic prompt generation for canvas nodes using local AI agents (`agy`/`pi`)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .local_agent_runner import LocalAgentRunner, get_agent_runner
from .media_service import resolve_input_path
from .skill_manager import PromptSkill, get_skill_manager

ROOT = Path(__file__).resolve().parents[2]


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

    def select_skill(self, task: NodePromptTask) -> PromptSkill:
        """Find matching skill or pick best default."""
        if task.skill_id:
            s = self.skill_mgr.get_skill(task.skill_id)
            if s:
                return s

        # Auto-detect default based on node type
        if task.node_type == "video":
            s = self.skill_mgr.get_skill("lookbook-video-prompter")
            if s:
                return s
            s = self.skill_mgr.get_skill("try-on-image-prompter")
            if s:
                return s
        else:
            if task.custom_hint and "lookbook" in task.custom_hint.lower():
                s = self.skill_mgr.get_skill("lookbook-image-prompter")
                if s:
                    return s
            s = self.skill_mgr.get_skill("try-on-image-prompter")
            if s:
                return s

        # Fallback to first available skill
        skills = self.skill_mgr.list_skills()
        if skills:
            return skills[0]

        raise RuntimeError("Không tìm thấy skill nào trong thư mục prompt-skills/.")

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
        is_cont = task.is_video_continuation

        # Craft prompt instruction
        lines = [
            f"Bạn là AI Prompt Director chuyên nghiệp cho workflow Google Flow (Flow Bench).",
            f"Quy chuẩn kỹ năng bắt buộc tuân theo nằm trong file: {skill.file_path}",
            "",
            "--- NỘI DUNG SKILL QUY CHUẨN ---",
            skill.raw_content,
            "---------------------------------",
            "",
            "--- THÔNG TIN ĐẦU VÀO VÀ BỐI CẢNH CỦA NODE HIỆN TẠI ---",
            f"- Loại Node cần tạo prompt: {'VIDEO' if is_video else 'ẢNH (IMAGE)'}",
            f"- Mã Node: {task.node_id}",
        ]

        if is_video:
            if is_cont:
                lines.append(
                    "- Vai trò Video: VIDEO 2 (8s-16s Nối tiếp) — Bắt đầu từ Frame Cuối của Video 1. "
                    "Yêu cầu: Người mẫu tiếp tục cử động tự nhiên từ tư thế kết thúc của Video 1, xoay 45-180 độ "
                    "để khoe lưng/cạnh trang phục, chuyển động liền mạch 1x speed, 24fps cadence."
                )
            else:
                lines.append(
                    "- Vai trò Video: VIDEO 1 (0s-8s The Hook & Outfit Showcase) — Bắt đầu từ ảnh First Frame. "
                    "Yêu cầu: Camera chậm rãi tự nhiên (slow push-in), chuyển động vi mô chân thực, 1x speed, 24fps cadence."
                )

        if rel_files:
            lines.append("- Các file ảnh kết quả từ node trước / ảnh tham chiếu đang kết nối vào node này:")
            for idx, rf in enumerate(rel_files, 1):
                lines.append(f"  {idx}. {rf}")
            lines.append(
                "  => HÃY ĐỌC VÀ PHÂN TÍCH TRỰC TIẾP các file ảnh trên (nhận diện màu sắc, phom dáng, chất liệu vải, "
                "chi tiết may mặc và tư thế thực tế của người mẫu) để viết prompt khớp 100% với ảnh thật vừa tạo."
            )
        else:
            lines.append("- Node chưa có file ảnh kết nối trực tiếp, hãy tạo prompt tổng quát dựa theo quy chuẩn của skill.")

        if task.custom_hint and task.custom_hint.strip():
            lines.append(f"- Ghi chú phong cách bổ sung từ người dùng: \"{task.custom_hint.strip()}\"")

        lines.extend([
            "",
            "--- YÊU CẦU ĐẦU RA ---",
            "1. BẮT BUỘC chèn mệnh đề khẳng định nhân vật hư cấu AI (Policy Compliance) để chống bộ lọc Prominent People.",
            "2. Trả về CHỈ nội dung Prompt hoàn chỉnh bằng tiếng Anh (English) đặt gọn gàng trong 1 khối code markdown:",
            "```markdown",
            "<nội dung prompt tiếng Anh>",
            "```",
            "Không kèm lời chào hỏi hay giải thích rườm rà ngoài khối code.",
        ])

        return "\n".join(lines)

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

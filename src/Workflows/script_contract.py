"""Script Contract — đọc & kiểm tra `configs/lookbook_script.schema.json`.

Script là **hợp đồng dữ liệu** giữa ba lớp:
  1. prompt agent  → đọc `clips[].role` / `motion_prompt` để viết prompt đúng vai;
  2. delivery      → đọc `clips`, `items`, `shots` để dựng thư mục nguyên liệu;
  3. HyperFrames   → đọc `delivery.json` (sinh từ script) để dựng timeline.

Trước đây ba lớp này mỗi bên tự đoán, nên không bên nào khớp bên nào. Đọc script qua
đúng một chỗ để mọi thứ còn khớp khi script đổi.

Không dùng pydantic: schema JSON là nguồn khai báo, module này chỉ bọc nó lại.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"
DEFAULT_SCHEMA_PATH = CONFIG_DIR / "lookbook_script.schema.json"

#: Giá trị mặc định khi script không khai. 24 là trần thật của nguồn Flow (ffprobe
#: `r_frame_rate=24/1`), không phải một lựa chọn thẩm mỹ.
DEFAULT_FPS = 24
DEFAULT_CANVAS = {"width": 1080, "height": 1920}
#: Một clip Flow dài cố định 8s; chaining bằng last frame là cách duy nhất để dài hơn.
CLIP_MAX_S = 8.0


class ScriptError(ValueError):
    """Script sai cấu trúc hoặc sai ràng buộc nghiệp vụ."""


@dataclass
class ClipSpec:
    id: str
    role: str
    motion_prompt: str
    duration_s: float
    camera: Optional[str] = None
    chain_from: Optional[str] = None
    source: str = "video_node"

    @property
    def chain_source_clip(self) -> Optional[str]:
        """`clip1.last_frame` → `clip1`."""
        if not self.chain_from:
            return None
        return self.chain_from.split(".", 1)[0] or None


@dataclass
class ShotSpec:
    id: str
    clip: str
    clip_offset_s: float
    duration_s: float
    text: Optional[str] = None
    text_enter: Optional[str] = None
    emphasis_item: Optional[str] = None
    transition: str = "cut"

    @property
    def end_s(self) -> float:
        return round(self.clip_offset_s + self.duration_s, 3)


@dataclass
class ItemSpec:
    id: str
    name: str
    cutout: Optional[str] = None
    cutout_back: Optional[str] = None
    callout: Optional[str] = None
    focus_s: Optional[list[float]] = None
    source_images: Optional[list[str]] = None


@dataclass
class LookbookScript:
    version: int
    slug: str
    title: str
    aspect: str
    fps: int
    duration_s: float
    canvas: dict[str, int]
    clips: list[ClipSpec]
    shots: list[ShotSpec]
    items: list[ItemSpec]
    audio: dict[str, Any]
    path: Optional[str] = None

    # -- truy vấn ------------------------------------------------------------- #

    def clip(self, clip_id: str) -> ClipSpec:
        for c in self.clips:
            if c.id == clip_id:
                return c
        raise ScriptError(f"script không có clip '{clip_id}'")

    def item(self, item_id: str) -> ItemSpec:
        for it in self.items:
            if it.id == item_id:
                return it
        raise ScriptError(f"script không có item '{item_id}'")

    def shots_for_clip(self, clip_id: str) -> list[ShotSpec]:
        return [s for s in self.shots if s.clip == clip_id]

    @property
    def total_clip_duration_s(self) -> float:
        return round(sum(c.duration_s for c in self.clips), 3)

    def brief(self) -> dict:
        """Bản rút gọn để chèn vào instruction của prompt agent."""
        return {
            "slug": self.slug,
            "title": self.title,
            "aspect": self.aspect,
            "fps": self.fps,
            "duration_s": self.duration_s,
            "clips": [
                {
                    "id": c.id,
                    "role": c.role,
                    "duration_s": c.duration_s,
                    "camera": c.camera,
                    "chain_from": c.chain_from,
                }
                for c in self.clips
            ],
            "items": [{"id": i.id, "name": i.name, "callout": i.callout} for i in self.items],
        }


# --------------------------------------------------------------------------- #
# Đọc / validate
# --------------------------------------------------------------------------- #


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_script(source: str | Path | dict) -> LookbookScript:
    """Đọc script từ đường dẫn hoặc dict đã parse. Raise `ScriptError` nếu sai."""
    raw: dict
    path: Optional[str] = None
    if isinstance(source, dict):
        raw = source
    else:
        p = Path(source)
        if not p.is_file():
            candidate = ROOT / p
            if candidate.is_file():
                p = candidate
            else:
                raise ScriptError(f"không tìm thấy script: {source}")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ScriptError(f"script không phải JSON hợp lệ: {exc}") from exc
        path = str(p.resolve())

    clips = [
        ClipSpec(
            id=str(c.get("id") or f"clip{i + 1}"),
            role=str(c.get("role") or "showcase"),
            motion_prompt=str(c.get("motion_prompt") or ""),
            duration_s=_as_float(c.get("duration_s"), CLIP_MAX_S),
            camera=c.get("camera"),
            chain_from=c.get("chain_from"),
            source=str(c.get("source") or "video_node"),
        )
        for i, c in enumerate(raw.get("clips") or [])
    ]
    if not clips:
        raise ScriptError("script phải có ít nhất một clip")

    shots = [
        ShotSpec(
            id=str(s.get("id") or f"s{i + 1}"),
            clip=str(s.get("clip") or ""),
            clip_offset_s=_as_float(s.get("clip_offset_s"), 0.0),
            duration_s=_as_float(s.get("duration_s"), 1.0),
            text=s.get("text"),
            text_enter=s.get("text_enter"),
            emphasis_item=s.get("emphasis_item"),
            transition=str(s.get("transition") or "cut"),
        )
        for i, s in enumerate(raw.get("shots") or [])
    ]

    items = [
        ItemSpec(
            id=str(it.get("id") or f"item_{i + 1}"),
            name=str(it.get("name") or ""),
            cutout=it.get("cutout"),
            cutout_back=it.get("cutout_back"),
            callout=it.get("callout"),
            focus_s=it.get("focus_s"),
            source_images=it.get("source_images"),
        )
        for i, it in enumerate(raw.get("items") or [])
    ]

    canvas = dict(DEFAULT_CANVAS)
    canvas.update({k: int(v) for k, v in (raw.get("canvas") or {}).items() if isinstance(v, (int, float))})

    script = LookbookScript(
        version=int(raw.get("version") or 1),
        slug=str(raw.get("slug") or "untitled"),
        title=str(raw.get("title") or ""),
        aspect=str(raw.get("aspect") or "9:16"),
        fps=int(raw.get("fps") or DEFAULT_FPS),
        duration_s=_as_float(raw.get("duration_s"), sum(c.duration_s for c in clips)),
        canvas=canvas,
        clips=clips,
        shots=shots,
        items=items,
        audio=raw.get("audio") or {},
        path=path,
    )
    validate_script(script)
    return script


def validate_script(script: LookbookScript) -> None:
    """Kiểm tra ràng buộc nghiệp vụ mà JSON Schema không diễn đạt được."""
    if script.fps not in (24, 30):
        raise ScriptError(
            f"fps={script.fps} không hợp lệ. Nguồn Flow là 24fps; đặt 60 chỉ nhân bản khung."
        )

    clip_ids = {c.id for c in script.clips}
    if len(clip_ids) != len(script.clips):
        raise ScriptError("id clip bị trùng")

    for c in script.clips:
        if c.duration_s > CLIP_MAX_S + 1e-6:
            raise ScriptError(
                f"clip '{c.id}' dài {c.duration_s}s — Flow chỉ sinh tối đa {CLIP_MAX_S:.0f}s mỗi clip. "
                "Chia thành clip nối bằng `chain_from`."
            )
        if c.chain_from:
            src = c.chain_source_clip
            if src not in clip_ids:
                raise ScriptError(f"clip '{c.id}' nối từ '{c.chain_from}' nhưng không có clip '{src}'")
            if src == c.id:
                raise ScriptError(f"clip '{c.id}' không thể nối từ chính nó")

    item_ids = {it.id for it in script.items}
    if len(item_ids) != len(script.items):
        raise ScriptError("id item bị trùng")

    for s in script.shots:
        if s.clip not in clip_ids:
            raise ScriptError(f"shot '{s.id}' trỏ tới clip '{s.clip}' không tồn tại")
        clip_dur = script.clip(s.clip).duration_s
        if s.end_s > clip_dur + 1e-6:
            raise ScriptError(
                f"shot '{s.id}' kết thúc ở {s.end_s}s nhưng clip '{s.clip}' chỉ dài {clip_dur}s"
            )
        if s.emphasis_item and s.emphasis_item not in item_ids:
            raise ScriptError(
                f"shot '{s.id}' nhấn item '{s.emphasis_item}' nhưng script không có item đó"
            )


def load_default_script() -> Optional[LookbookScript]:
    """Script mẫu trong `configs/lookbook_script.json`, nếu có."""
    p = CONFIG_DIR / "lookbook_script.json"
    return load_script(p) if p.is_file() else None


__all__ = [
    "CLIP_MAX_S",
    "DEFAULT_CANVAS",
    "DEFAULT_FPS",
    "ClipSpec",
    "ItemSpec",
    "LookbookScript",
    "ScriptError",
    "ShotSpec",
    "load_default_script",
    "load_script",
    "validate_script",
]

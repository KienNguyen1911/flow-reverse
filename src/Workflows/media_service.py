"""Node Media Service — standalone image/video generation for canvas nodes.

This service is the single entry point for "one node = one generation" flows. It
wraps the protocol cores (:class:`~src.Workflows.flow_client.FlowClient` for
images, :class:`~src.Bridge.flow_video_bridge.FlowVideoBridge` for videos) and
adds the concerns that every caller needs but that previously lived only inside
the try-on pipeline or the WebUI job layer:

* project resolution (explicit → project open in the tab → newest project → create);
* optional i2i reference-image template cache (account + sha256);
* video watermark removal (images already handle it inside ``FlowClient``);
* per-CDP-tab serialization, so two canvas nodes cannot drive the same tab at once;
* node run directories under ``out/nodes/`` with deterministic naming.

Nothing here depends on ``auto_tryon_pipeline`` — the pipeline is a consumer,
not an owner, of image/video generation.

Usage::

    svc = MediaService(cdp_url="http://127.0.0.1:4022")
    img = svc.generate_image(prompt="...", aspect_ratio="16:9")
    vid = svc.generate_video(prompt="...", frame_path=img.file_path, aspect_ratio="9:16")

Limitations (verified against docs/api_specs/*):
* Image aspect ratios are an int enum; only ``16:9 == 3`` is verified. Extra
  ratios must be captured with ``discovery/capture_image_aspects.py`` (written
  to ``configs/image_aspect_enums.json``) — never guessed.
* Video is image-to-video only (``abra_i2v_8s``): a starting frame is required.
  Without one, ``auto_image=True`` chains an image generation first. There is
  no reverse-engineered text-to-video RPC (see ``discovery/probe_video_composer.py``).
* Video duration is fixed at 8s by the model key; resolution supports 1080p
  (default, upsampled via ``p0UkFb`` with 720p fallback) and 720p.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

from ..Bridge.flow_bridge import DEFAULT_CDP_URL
from ..Bridge.flow_video_bridge import FlowVideoBridge, VIDEO_EDIT_MODEL_KEY
from .account_pool import ReferenceMediaRegistry, sha256_file
from .flow_client import FlowClient
from .flow_models import GenerationResult, ReferenceTemplate, parse_project_ref
from .limits import load_limits
from .media_options import (
    UnsupportedOptionError,
    VIDEO_DURATIONS_S,
    VIDEO_DURATION_S,
    VIDEO_RATIOS,
    VIDEO_RESOLUTIONS,
    VideoSubmitPlan,
    normalize_ratio_label,
    normalize_video_ratio,
    normalize_video_resolution,
    plan_video_submit,
    validate_video_duration,
)
from .media_probe import probe_video
from .watermark_remover import remove_video_watermark
from .flow_catalog import (
    IMAGE_ASPECT_ENUM,
    IMAGE_ASPECT_ORDER,
    MediaModel,
    agent_mode_catalog,
    image_catalog,
    image_model_key,
    normalize_count,
    resolve_image_model,
    video_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NODE_OUT = ROOT / "out" / "nodes"
IMAGE_ASPECT_CONFIG = ROOT / "configs" / "image_aspect_enums.json"

#: Aspect enum values verified against a captured Flow request.
#: ``docs/api_specs/flow_create_image.md`` §2: ``spec[4] = 3`` (16:9).
#: 9:16 = 2 captured from the app's own blocked request (0 credit), 2026-10-28,
#: via discovery/capture_image_aspects.py (traces/image_aspects_20261028T165133.json).
#: 4:3 = 5, 1:1 = 1, 3:4 = 4 captured 0-credit on 2026-11-03 (discovery/probe_count_res.py).
#: Kept in sync with :mod:`src.Workflows.flow_catalog` (single source of truth).
VERIFIED_IMAGE_ASPECTS: dict[str, int] = dict(IMAGE_ASPECT_ENUM)

class AspectNotVerifiedError(ValueError):
    """Raised when a ratio has no captured enum value yet."""


# --------------------------------------------------------------------------- #
# Aspect / option resolution
# --------------------------------------------------------------------------- #


def load_image_aspects(config_path: Optional[Path | str] = None) -> dict[str, int]:
    """Verified ratio → enum map (config file overrides/augments the built-ins).

    The config file is written by ``discovery/capture_image_aspects.py``::

        {"version": 1, "ratios": {"16:9": 3, "9:16": 1, "1:1": 2}}
    """
    ratios = dict(VERIFIED_IMAGE_ASPECTS)
    path = Path(config_path) if config_path else IMAGE_ASPECT_CONFIG
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw.get("ratios") if isinstance(raw, dict) else None
            if isinstance(entries, dict):
                for ratio, enum in entries.items():
                    try:
                        ratios[str(ratio).strip()] = int(enum)
                    except (TypeError, ValueError):
                        continue
    except Exception:  # noqa: BLE001 - a broken config must not break generation
        pass
    return ratios


def _normalize_ratio_label(value: str) -> str:
    """Kept as a local alias so image-aspect call sites read the same as before."""
    return normalize_ratio_label(value)


def resolve_image_aspect(
    aspect_ratio: Optional[str] = None,
    aspect: Optional[int] = None,
    *,
    config_path: Optional[Path | str] = None,
) -> tuple[str, int]:
    """Resolve a user-facing ratio (or raw enum) to ``(label, enum)``.

    ``aspect`` (int) always wins and is passed through untouched — it is the
    escape hatch for values captured manually. ``aspect_ratio`` accepts
    ``"16:9"``, aliases (``"portrait"``) and numeric strings (``"3"``).
    """
    ratios = load_image_aspects(config_path)

    if aspect is not None:
        enum = int(aspect)
        if enum <= 0:
            raise UnsupportedOptionError(f"aspect enum phải > 0 (nhận {enum})")
        label = next((k for k, v in ratios.items() if v == enum), f"aspect_{enum}")
        return label, enum

    if aspect_ratio is None or str(aspect_ratio).strip() == "":
        label = next(iter(ratios))
        return label, ratios[label]

    raw = str(aspect_ratio).strip()
    if raw.isdigit():
        return resolve_image_aspect(aspect=int(raw), config_path=config_path)

    label = _normalize_ratio_label(raw)
    if label not in ratios:
        known = ", ".join(f"{k}={v}" for k, v in ratios.items())
        raise AspectNotVerifiedError(
            f"Tỷ lệ ảnh {raw!r} chưa được verify (enum chưa capture). "
            f"Đã biết: {known}. Chạy `python -m discovery.capture_image_aspects` khi browser đang mở "
            f"để ghi configs/image_aspect_enums.json, hoặc truyền `aspect` (int) đã capture thủ công."
        )
    return label, ratios[label]


def node_options(config_path: Optional[Path | str] = None) -> dict:
    """Machine-readable option list for building canvas node UIs.

    ``config_path`` is kept for backwards compatibility: the image aspect enums now
    come from :mod:`src.Workflows.flow_catalog` (captured, not from a mutable file),
    so the parameter no longer changes the result.
    """
    _ = config_path

    # Danh sách clip của kịch bản mặc định: node video cần `clip_id` để agent biết đang viết clip
    # nào (`role`, `shots`, `chain_from`, beats). Trước đây FE không có nguồn nào để chọn, và
    # `_script_context_lines` lặng lẽ in context rỗng cho mọi node video.
    script_info: dict = {"path": None, "clips": []}
    try:
        from .script_contract import load_default_script

        script = load_default_script()
        if script is not None:
            script_info = {
                "path": "configs/lookbook_script.json",
                "slug": script.slug,
                "title": script.title,
                "duration_s": script.duration_s,
                "clips": [
                    {
                        "id": c.id,
                        "role": c.role,
                        "duration_s": c.duration_s,
                        "camera": c.camera,
                        "chain_from": c.chain_from,
                        "goal": c.goal,
                        "has_beats": c.has_beats,
                    }
                    for c in script.clips
                ],
            }
    except Exception:  # noqa: BLE001 - script hỏng không được chặn việc dựng UI
        pass

    return {
        #: Validation caps enforced by the API — the UI mirrors these instead of
        #: hard-coding its own numbers (see ``src/Workflows/limits.py``).
        "limits": load_limits().as_dict(),
        "script": script_info,
        #: Everything below is Observed Evidence from the real composer
        #: (``src/Workflows/flow_catalog.py``, capture notes in
        #: ``.turbo/node-config-parity/matrix.md``). The UI reads these lists —
        #: it must never hard-code ratios/models/counts on its own.
        "image": image_catalog(),
        "video": video_catalog(),
        "agent": agent_mode_catalog(),
    }


# --------------------------------------------------------------------------- #
# Input path resolution (attachments may be filesystem paths or API URLs)
# --------------------------------------------------------------------------- #


def resolve_input_path(raw: Path | str, *, run_roots: Iterable[Path | str] = ()) -> Path:
    """Map an attachment reference (path or ``/api/...`` URL) to a local file.

    The returned path may not exist; callers validate with ``is_file()`` so the
    error message can name the original reference.
    """
    s = str(raw or "").strip().strip('"').strip("'")
    if "?" in s:
        s = s.split("?", 1)[0]
    if s.startswith("/api/"):
        m = re.match(r"^/api/([a-z_]+)/(.+)$", s)
        if m:
            kind, rel = m.group(1), m.group(2)
            if kind == "tryon":
                rel = re.sub(r"^files/", "", rel)
                roots = [Path(r) for r in (run_roots or [ROOT / "out" / "affiliate_runs"])]
                for root in roots:
                    cand = (root / rel).resolve()
                    if cand.is_file():
                        return cand
                return (roots[0] / rel).resolve()
            elif kind == "node":
                return (DEFAULT_NODE_OUT / re.sub(r"^files/", "", rel)).resolve()
            elif kind == "uploads":
                return (ROOT / "out" / "uploads" / rel).resolve()
            elif kind == "references":
                return (ROOT / "out" / "references" / rel).resolve()
            elif kind == "assets":
                return (ROOT / "assets" / rel).resolve()
    p = Path(s)
    if p.is_file():
        return p.resolve()
    if (ROOT / p).is_file():
        return (ROOT / p).resolve()
    return p


# --------------------------------------------------------------------------- #
# Per-tab serialization
# --------------------------------------------------------------------------- #

_CDP_LOCKS: dict[str, threading.RLock] = {}
_CDP_LOCKS_GUARD = threading.Lock()


def cdp_lock(cdp_url: str) -> threading.RLock:
    """Process-wide re-entrant lock per browser tab (same CDP endpoint = same tab pool)."""
    key = str(cdp_url or DEFAULT_CDP_URL).rstrip("/")
    with _CDP_LOCKS_GUARD:
        lock = _CDP_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _CDP_LOCKS[key] = lock
        return lock


def _unique_run_dir(root: Path, prefix: str) -> tuple[str, Path]:
    """Create ``<prefix>_<timestamp>[_n]`` under *root* and return ``(name, path)``."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{prefix}_{ts}"
    cand = root / base
    n = 2
    while cand.exists():
        cand = root / f"{base}_{n}"
        n += 1
    cand.mkdir(parents=True, exist_ok=False)
    return cand.name, cand


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass
class NodeImageResult:
    status: str
    prompt: str
    aspect_ratio: str
    aspect_enum: int
    project_id: str = ""
    seed_used: Optional[int] = None
    run_id: str = ""
    run_dir: str = ""
    file_path: Optional[str] = None
    file_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    resolution: Optional[list[int]] = None
    signed_url: Optional[str] = None
    media_id: Optional[str] = None
    reference_sha256: Optional[str] = None
    reference_media_id: Optional[str] = None
    #: Composer model actually used (catalog id) and how many images were requested.
    model: str = "nano_banana_2_1"
    model_label: str = "Nano Banana 2.1"
    count: int = 1
    #: True when the composer was in "Tác nhân" mode (config hidden, defaults used).
    agent_mode: bool = False
    dry_run: bool = False
    elapsed_s: float = 0.0
    reason: Optional[str] = None
    hint: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NodeVideoResult:
    status: str
    prompt: str
    aspect_ratio: str
    run_id: str
    run_dir: str
    project_id: str = ""
    seed_used: Optional[int] = None
    video_path: Optional[str] = None
    video_bytes: Optional[int] = None
    resolution: str = "1080p"
    #: Composer config actually used (see ``src/Workflows/flow_catalog.py``).
    model: str = "omni_1_1_flash"
    model_label: str = "Omni 1.1 Flash"
    model_key: Optional[str] = None
    sub_mode: str = "frames"
    count: int = 1
    #: True when the composer was in "Tác nhân" mode (config hidden, defaults used).
    agent_mode: bool = False
    #: Tham số YÊU CẦU 8s. Số đo thật nằm ở `measured_*` bên dưới — đừng dùng field này
    #: để đặt thời lượng trên timeline dựng phim.
    duration_s: int = VIDEO_DURATION_S
    frame_path: Optional[str] = None
    frame_source: Optional[Literal["provided", "generated"]] = None
    #: Ảnh khung "Kết thúc" đã gắn (None = video một khung). Khi có, submit đi RPC
    #: `nprQif` và Flow hạ trần thời lượng xuống 10s.
    last_frame_path: Optional[str] = None
    reference_image_paths: Optional[list[str]] = None
    image_prompt: Optional[str] = None
    watermark_removed: bool = False
    dry_run: bool = False
    elapsed_s: float = 0.0
    reason: Optional[str] = None
    hint: Optional[str] = None
    # -- đo bằng ffprobe sau khi tải xong (None nếu dry-run/không đo được) ---------- #
    measured_duration_s: Optional[float] = None
    measured_fps: Optional[float] = None
    measured_width: Optional[int] = None
    measured_height: Optional[int] = None
    has_audio: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class MediaService:
    """One image or one video per call, safe to share across canvas node workers."""

    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        out_dir: Optional[Path | str] = None,
        *,
        account_id: str = "default",
        registry: Optional[ReferenceMediaRegistry] = None,
        log: Optional[Callable[[str, str], None]] = None,
        image_client: Optional[FlowClient] = None,
        video_bridge: Optional[FlowVideoBridge] = None,
        workspace_store: Optional[Any] = None,
        projects_store: Optional[Any] = None,
    ):
        self.cdp_url = cdp_url
        self.out_root = Path(out_dir) if out_dir else DEFAULT_NODE_OUT
        self.account_id = account_id or "default"
        self.registry = registry
        self._log = log or (lambda kind, msg: None)
        self._lock = cdp_lock(cdp_url)
        self._project_cache: Optional[str] = None
        self.workspace_store = workspace_store
        self.projects_store = projects_store
        self.image = image_client or FlowClient(
            cdp_url=cdp_url,
            out_dir=self.out_root,
            log=lambda msg: self._log("info", msg),
            account_id=self.account_id,
        )
        if not hasattr(self.image, "account_id") or not getattr(self.image, "account_id", None):
            try:
                setattr(self.image, "account_id", self.account_id)
            except Exception:
                pass
        self.video = video_bridge or FlowVideoBridge(
            cdp_url=cdp_url,
            log=lambda kind, msg: self._log(kind, msg),
        )

    def _get_workspace_store(self) -> Optional[Any]:
        if self.workspace_store is not None:
            return self.workspace_store
        try:
            from ..WebUI.workspace import WorkspaceStore
            ws_file = (self.out_root.parent / "flowbench_workspace.json") if self.out_root else (ROOT / "out" / "flowbench_workspace.json")
            self.workspace_store = WorkspaceStore(ws_file)
            return self.workspace_store
        except Exception:
            return None

    def _get_projects_store(self) -> Optional[Any]:
        if self.projects_store is not None:
            return self.projects_store
        try:
            from ..WebUI.jobs.projects_store import ProjectsStore
            pj_file = (self.out_root.parent / "playground_projects.json") if self.out_root else (ROOT / "out" / "playground_projects.json")
            self.projects_store = ProjectsStore(pj_file)
            return self.projects_store
        except Exception:
            return None

    def _lazy_create_workspace_project(
        self,
        workspace_project_id: str,
        on_event: Optional[Callable[..., None]] = None,
    ) -> str:
        ws_store = self._get_workspace_store()
        ws = ws_store.get(workspace_project_id) if ws_store else None
        ws_name = ws.name if ws else ((ws_store.name_of(workspace_project_id) if ws_store else None) or workspace_project_id)
        title = f"FlowBench - {ws_name}"
        created = self.image.create_project(title, on_event=on_event)
        new_pid = parse_project_ref(created.id)
        if ws_store:
            ws_store.set_flow_project(workspace_project_id, self.account_id, new_pid)
        pj_store = self._get_projects_store()
        if pj_store:
            from ..Workflows.flow_models import ProjectInfo
            if isinstance(created, ProjectInfo):
                pj_store.upsert(created)
            else:
                pj_store.upsert(ProjectInfo(id=new_pid, title=getattr(created, "title", title), source="created"))
        self._project_cache = new_pid
        self._emit(on_event, "info", f"Đã khởi tạo & gắn Google Flow Project mới [{new_pid}] cho Workspace [{ws_name}] trên account [{self.account_id}]")
        return new_pid

    # -- project -------------------------------------------------------------- #

    def resolve_project(
        self,
        project_id: Optional[str] = None,
        *,
        workspace_project_id: Optional[str] = None,
        create_title: str = "Node Media",
        on_event: Optional[Callable[..., None]] = None,
    ) -> str:
        """Return a usable project id: explicit → workspace mapping (lazy-created) → open tab → newest → newly created."""
        if project_id:
            cleaned = parse_project_ref(project_id)
            self._project_cache = cleaned
            return cleaned
        with self._lock:
            ev = on_event
            if workspace_project_id:
                ws_store = self._get_workspace_store()
                mapped_pid = ws_store.get_flow_project(workspace_project_id, self.account_id) if ws_store else None
                if mapped_pid:
                    cleaned_pid = parse_project_ref(mapped_pid)
                    self._project_cache = cleaned_pid
                    self._emit(ev, "info", f"Dùng Google Flow Project [{cleaned_pid}] cho Workspace [{workspace_project_id}] trên account [{self.account_id}]")
                    return cleaned_pid
                # Lazy-create flow project for workspace
                return self._lazy_create_workspace_project(workspace_project_id, on_event=ev)

            if self._project_cache:
                return self._project_cache
            st = self.image.status()
            if st.flow_project_id:
                self._project_cache = st.flow_project_id
                self._emit(ev, "info", f"Dùng dự án đang mở trên tab Flow: {self._project_cache}")
                return self._project_cache
            listed = self.image.list_projects(on_event=ev)
            if listed:
                self._project_cache = parse_project_ref(listed[0].id)
                self._emit(ev, "info", f"Dùng dự án có sẵn: {listed[0].title or self._project_cache[:8]}")
                return self._project_cache
            created = self.image.create_project(create_title, on_event=ev)
            self._project_cache = created.id
            self._emit(ev, "info", f"Đã tạo dự án mới: {created.title} ({created.id[:8]}…)")
            return self._project_cache

    @staticmethod
    def _emit(ev: Optional[Callable[..., None]], kind: str, message: str, data: Optional[dict] = None) -> None:
        if ev is None:
            return
        try:
            ev(kind, message, data or {})
        except TypeError:
            try:
                ev(kind, message)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    # -- reference image ------------------------------------------------------ #

    def _reference_template(
        self,
        project_id: str,
        reference_image: Optional[Path | str],
        prompt: str,
        on_event: Optional[Callable[..., None]],
    ) -> tuple[Optional[ReferenceTemplate], Optional[str]]:
        if not reference_image:
            return None, None
        path = resolve_input_path(reference_image)
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy ảnh tham chiếu: {reference_image} (đã thử {path})")
        sha = sha256_file(path)
        if self.registry is not None:
            cached = self.registry.get(self.account_id, sha)
            if cached:
                try:
                    self._emit(on_event, "info", f"Trúng cache ảnh tham chiếu sha {sha[:8]}…")
                    return ReferenceTemplate(**cached), sha
                except Exception:  # noqa: BLE001 - stale entry, re-capture
                    pass
        self._emit(on_event, "step", f"Upload ảnh tham chiếu lần đầu ({path.name}) — 0 credit")
        tpl = self.image.upload_reference_image(
            project_id,
            path,
            prompt_probe=(prompt or "reference")[:60],
            on_event=on_event,
        )
        if self.registry is not None:
            self.registry.put(self.account_id, tpl.model_dump())
        return tpl, sha

    # -- image ---------------------------------------------------------------- #

    def generate_image(
        self,
        *,
        prompt: str,
        aspect_ratio: Optional[str] = None,
        aspect: Optional[int] = None,
        seed: Optional[int] = None,
        reference_image: Optional[Path | str] = None,
        reference_images: Optional[list[Path | str]] = None,
        project_id: Optional[str] = None,
        workspace_project_id: Optional[str] = None,
        dry_run: bool = False,
        remove_watermark: bool = True,
        model: Optional[str] = None,
        count: int = 1,
        agent_mode: bool = False,
        on_event: Optional[Callable[..., None]] = None,
    ) -> NodeImageResult:
        """Generate ``count`` images for one node (~1 credit each if accepted).

        ``model`` accepts a catalog id (``nano_banana_pro``) or the composer label
        (``Nano Banana Pro``); ``count`` mirrors the composer's ``x1..x4``.

        ``agent_mode`` mirrors the composer's "Tác nhân" chip: Flow hides the
        model/aspect/count controls entirely, so user values are ignored and the
        catalog defaults are used. The result records both facts.
        """
        t0 = time.time()
        if agent_mode:
            # Flow hides model/aspect/count while "Tác nhân" is on; use the catalog defaults
            # and say so instead of applying values the composer would ignore.
            model, aspect_ratio, aspect, count = None, None, None, 1
            default_model = resolve_image_model(None)
            self._emit(
                on_event,
                "info",
                f"Tác nhân bật: dùng mặc định {default_model.label} · 16:9 · x1 "
                "(Flow ẩn cấu hình model/tỷ lệ/số lượng).",
            )
        label, enum = resolve_image_aspect(aspect_ratio, aspect)
        model_info = resolve_image_model(model)
        n = normalize_count(count)
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt rỗng")
        with self._lock:
            project = self.resolve_project(project_id, workspace_project_id=workspace_project_id, on_event=on_event)
            ref_paths: list[Path] = []
            if reference_images:
                for r in reference_images:
                    if r:
                        rp = resolve_input_path(r)
                        if not rp.is_file():
                            raise FileNotFoundError(f"Không tìm thấy ảnh tham chiếu: {r} (đã thử {rp})")
                        if rp not in ref_paths:
                            ref_paths.append(rp)
            if reference_image:
                rp = resolve_input_path(reference_image)
                if not rp.is_file():
                    raise FileNotFoundError(f"Không tìm thấy ảnh tham chiếu: {reference_image} (đã thử {rp})")
                if rp not in ref_paths:
                    ref_paths.insert(0, rp)

            sha = sha256_file(ref_paths[0]) if ref_paths else None
            gen_kwargs = {
                "aspect": enum,
                "seed": seed,
                "dry_run": dry_run,
                "remove_watermark": remove_watermark,
                "on_event": on_event,
            }
            # Detect whether image client supports direct reference_path / reference_paths / aspect_ratio
            import inspect
            try:
                sig = inspect.signature(self.image.generate_image)
                supports_ref_paths = "reference_path" in sig.parameters or "reference_paths" in sig.parameters
                if "aspect_ratio" in sig.parameters:
                    gen_kwargs["aspect_ratio"] = label
                if "model_key" in sig.parameters:
                    gen_kwargs["model_key"] = image_model_key(model_info)
                if "model_label" in sig.parameters:
                    gen_kwargs["model_label"] = model_info.label
                if "count" in sig.parameters:
                    gen_kwargs["count"] = n
            except Exception:
                supports_ref_paths = True
                gen_kwargs["aspect_ratio"] = label

            tpl = None
            if ref_paths:
                if supports_ref_paths:
                    gen_kwargs["reference_path"] = ref_paths[0]
                    gen_kwargs["reference_paths"] = ref_paths
                else:
                    tpl, _ = self._reference_template(project, ref_paths[0], prompt, on_event)
                    gen_kwargs["reference"] = tpl

            try:
                res: GenerationResult = self.image.generate_image(
                    project,
                    prompt,
                    **gen_kwargs,
                )
            except Exception as exc:
                if workspace_project_id and ("404" in str(exc) or "không tồn tại" in str(exc)):
                    self._emit(on_event, "warn", f"Dự án {project} không tồn tại trên mây (404). Khởi tạo lại dự án mới...")
                    ws_store = self._get_workspace_store()
                    if ws_store:
                        ws_store.remove_flow_project(workspace_project_id, self.account_id)
                    from .project_media_registry import get_project_media_registry
                    get_project_media_registry().clear_project(self.account_id, project)
                    project = self._lazy_create_workspace_project(workspace_project_id, on_event=on_event)
                    if ref_paths and not supports_ref_paths:
                        tpl, _ = self._reference_template(project, ref_paths[0], prompt, on_event)
                        gen_kwargs["reference"] = tpl
                    res = self.image.generate_image(
                        project,
                        prompt,
                        **gen_kwargs,
                    )
                else:
                    raise
        return self._image_result(
            res, prompt, label, enum, project, sha, tpl, t0, model_info, n, agent_mode
        )

    @staticmethod
    def _image_result(
        res: GenerationResult,
        prompt: str,
        label: str,
        enum: int,
        project: str,
        reference_sha: Optional[str],
        tpl: Optional[ReferenceTemplate],
        t0: float,
        model_info: Optional[MediaModel] = None,
        count: int = 1,
        agent_mode: bool = False,
    ) -> NodeImageResult:
        img = res.image
        run_dir = Path(res.run_dir) if res.run_dir else None
        return NodeImageResult(
            status=res.status,
            prompt=prompt,
            aspect_ratio=label,
            aspect_enum=enum,
            project_id=project,
            seed_used=res.seed_used,
            run_id=run_dir.name if run_dir else "",
            run_dir=str(run_dir) if run_dir else "",
            file_path=img.file_path if img else None,
            file_bytes=img.file_bytes if img else None,
            width=img.width if img else None,
            height=img.height if img else None,
            resolution=img.resolution if img else None,
            signed_url=img.signed_url if img else None,
            media_id=img.media_id if img else None,
            reference_sha256=reference_sha or (tpl.sha256 if tpl else None),
            reference_media_id=(tpl.media_id if tpl else None),
            model=(model_info.id if model_info else "nano_banana_2_1"),
            model_label=(model_info.label if model_info else "Nano Banana 2.1"),
            count=count,
            agent_mode=agent_mode,
            dry_run=res.status == "dry_run",
            elapsed_s=res.elapsed_s or round(time.time() - t0, 2),
            reason=res.reason,
            hint=res.hint,
            detail=res.detail,
        )

    # -- video ---------------------------------------------------------------- #

    def animate_frame(
        self,
        *,
        frame_path: Path | str,
        prompt: str,
        dest_path: Path | str,
        aspect_ratio: str = "9:16",
        seed: Optional[int] = None,
        resolution: str = "1080p",
        duration_s: int = VIDEO_DURATION_S,
        project_id: Optional[str] = None,
        workspace_project_id: Optional[str] = None,
        timeout_s: float = 300.0,
        model: Optional[str] = None,
        count: int = 1,
        last_frame_path: Optional[Path | str] = None,
        on_event: Optional[Callable[..., None]] = None,
    ) -> Path:
        """Bridge-level image→video call (no run dir, no watermark) under the tab lock.

        Used by :meth:`generate_video` and by multi-step workflows (try-on chain)
        that own their output paths and post-processing.

        ``last_frame_path`` fills the composer's "Kết thúc" slot; the submit then goes out
        on `nprQif` and Flow caps the duration at 10s.
        """
        has_last_frame = last_frame_path is not None
        plan = plan_video_submit(
            aspect_ratio=aspect_ratio,
            model=model,
            sub_mode="frames",
            resolution=resolution,
            duration_s=duration_s,
            count=count,
            has_last_frame=has_last_frame,
        )
        model_info, ratio = plan.model, plan.ratio
        res_label, duration = plan.resolution, plan.duration_s
        n, capture_res, key = plan.count, plan.capture_res, plan.model_key
        if not (prompt or "").strip():
            raise ValueError("prompt rỗng")
        prompt = (prompt or "").strip()
        frame = resolve_input_path(frame_path)
        if not frame.is_file():
            raise FileNotFoundError(f"Không tìm thấy ảnh đính kèm: {frame_path}")
        last_frame = resolve_input_path(last_frame_path) if last_frame_path else None
        if last_frame is not None and not last_frame.is_file():
            raise FileNotFoundError(f"Không tìm thấy ảnh khung 'Kết thúc': {last_frame_path}")
        dest = Path(dest_path)
        bridge_kwargs = dict(
            frame_path=frame,
            prompt_text=prompt,
            dest_path=dest,
            duration_s=duration,
            timeout_s=timeout_s,
            aspect_ratio=ratio,
            seed=seed,
            resolution=res_label,
            model_key=key,
            model_label=model_info.label,
            count=n,
            offer_resolution=model_info.has_resolution,
            offer_duration=model_info.has_duration,
            capture_resolution=capture_res,
            last_frame_path=last_frame,
        )
        with self._lock:
            project = self.resolve_project(project_id, workspace_project_id=workspace_project_id, on_event=on_event)
            try:
                self.video.generate_video_flow(project_id=project, **bridge_kwargs)
            except Exception as exc:
                if workspace_project_id and ("404" in str(exc) or "không tồn tại" in str(exc)):
                    self._emit(on_event, "warn", f"Dự án {project} không tồn tại trên mây (404). Khởi tạo lại dự án mới...")
                    ws_store = self._get_workspace_store()
                    if ws_store:
                        ws_store.remove_flow_project(workspace_project_id, self.account_id)
                    from .project_media_registry import get_project_media_registry
                    get_project_media_registry().clear_project(self.account_id, project)
                    project = self._lazy_create_workspace_project(workspace_project_id, on_event=on_event)
                    self.video.generate_video_flow(project_id=project, **bridge_kwargs)
                else:
                    raise
            return dest

    def generate_text_video(
        self,
        *,
        prompt: str,
        dest_path: Path | str,
        aspect_ratio: str = "9:16",
        seed: Optional[int] = None,
        resolution: str = "1080p",
        duration_s: int = VIDEO_DURATION_S,
        project_id: Optional[str] = None,
        workspace_project_id: Optional[str] = None,
        timeout_s: float = 300.0,
        model: Optional[str] = None,
        count: int = 1,
        reference_paths: Optional[list[Path | str]] = None,
        video_reference_title: Optional[str] = None,
        on_event: Optional[Callable[..., None]] = None,
    ) -> Path:
        """Bridge-level text/ingredients video call under the lock.

        ``video_reference_title`` switches the submit to the video-reference path (``jIps6``,
        key ``abra_edit``) by mounting a clip from the project; image references are ignored
        then because Flow fires a single submit RPC.
        """
        plan = plan_video_submit(
            aspect_ratio=aspect_ratio,
            model=model,
            sub_mode="ingredients",
            resolution=resolution,
            duration_s=duration_s,
            count=count,
        )
        model_info, ratio = plan.model, plan.ratio
        res_label, duration = plan.resolution, plan.duration_s
        n, capture_res, key = plan.count, plan.capture_res, plan.model_key
        if not (prompt or "").strip():
            raise ValueError("prompt rỗng")
        prompt = (prompt or "").strip()
        dest = Path(dest_path)
        with self._lock:
            project = self.resolve_project(project_id, workspace_project_id=workspace_project_id, on_event=on_event)
            try:
                self.video.generate_text_video_flow(
                    prompt_text=prompt,
                    dest_path=dest,
                    duration_s=duration,
                    timeout_s=timeout_s,
                    project_id=project,
                    aspect_ratio=ratio,
                    seed=seed,
                    resolution=res_label,
                    reference_paths=reference_paths,
                    video_reference_title=video_reference_title,
                    model_key=key,
                    model_label=model_info.label,
                    count=n,
                    offer_resolution=model_info.has_resolution,
                    offer_duration=model_info.has_duration,
                    capture_resolution=capture_res,
                )
            except Exception as exc:
                if workspace_project_id and ("404" in str(exc) or "không tồn tại" in str(exc)):
                    self._emit(on_event, "warn", f"Dự án {project} không tồn tại trên mây (404). Khởi tạo lại dự án mới...")
                    ws_store = self._get_workspace_store()
                    if ws_store:
                        ws_store.remove_flow_project(workspace_project_id, self.account_id)
                    from .project_media_registry import get_project_media_registry
                    get_project_media_registry().clear_project(self.account_id, project)
                    project = self._lazy_create_workspace_project(workspace_project_id, on_event=on_event)
                    self.video.generate_text_video_flow(
                        prompt_text=prompt,
                        dest_path=dest,
                        duration_s=duration,
                        timeout_s=timeout_s,
                        project_id=project,
                        aspect_ratio=ratio,
                        seed=seed,
                        resolution=res_label,
                        reference_paths=reference_paths,
                        video_reference_title=video_reference_title,
                        model_key=key,
                        model_label=model_info.label,
                        count=n,
                        offer_resolution=model_info.has_resolution,
                        offer_duration=model_info.has_duration,
                        capture_resolution=capture_res,
                    )
                else:
                    raise
        return dest

    def generate_video(
        self,
        *,
        prompt: str,
        frame_path: Optional[Path | str] = None,
        reference_image_path: Optional[Path | str] = None,
        reference_image_paths: Optional[list[Path | str]] = None,
        aspect_ratio: str = "9:16",
        seed: Optional[int] = None,
        resolution: str = "1080p",
        duration_s: int = VIDEO_DURATION_S,
        project_id: Optional[str] = None,
        workspace_project_id: Optional[str] = None,
        dry_run: bool = False,
        remove_watermark: bool = True,
        timeout_s: float = 300.0,
        auto_image: bool = True,
        image_prompt: Optional[str] = None,
        image_aspect_ratio: str = "16:9",
        model: Optional[str] = None,
        sub_mode: str = "frames",
        count: int = 1,
        agent_mode: bool = False,
        last_frame_path: Optional[Path | str] = None,
        video_reference_title: Optional[str] = None,
        on_event: Optional[Callable[..., None]] = None,
    ) -> NodeVideoResult:
        """Generate ``count`` videos for one node, mirroring the Flow composer.

        Two sub-modes, both captured 0-credit (see ``src/Workflows/flow_catalog.py``):

        * ``sub_mode="frames"`` (Khung hình / image→video, ``eb1hJf``): needs a starting
          frame; when ``frame_path`` is omitted and ``auto_image`` is true an image is
          generated first. Supplying ``last_frame_path`` fills the composer's "Kết thúc"
          slot, which switches the submit to `nprQif` and caps the duration at 10s.
        * ``sub_mode="ingredients"`` (Thành phần / text→video, ``YhhmEf``): prompt-driven,
          with optional reference images uploaded as ingredient chips into the composer.

        ``agent_mode`` mirrors the composer's "Tác nhân" chip: Flow hides the
        model/sub-mode/aspect/resolution/duration/count controls, so the catalog
        defaults are used and the result says so.
        """
        t0 = time.time()
        # A last frame only exists in the "Khung hình" sub-mode; the ingredients composer has
        # no "Kết thúc" slot, so drop it rather than silently ignoring it later.
        wants_last_frame = bool(last_frame_path) and str(sub_mode or "frames").strip().lower() == "frames"
        plan = plan_video_submit(
            aspect_ratio=aspect_ratio,
            model=model,
            sub_mode=sub_mode,
            resolution=resolution,
            duration_s=duration_s,
            count=count,
            agent_mode=agent_mode,
            has_last_frame=wants_last_frame,
        )
        ratio, model_info, sub = plan.ratio, plan.model, plan.sub_mode
        res_label, duration = plan.resolution, plan.duration_s
        n, capture_res, model_key = plan.count, plan.capture_res, plan.model_key
        if agent_mode:
            self._emit(
                on_event,
                "info",
                f"Tác nhân bật: dùng mặc định {model_info.label} · {model_info.fixed_resolution} · "
                f"{model_info.fixed_duration_s}s · {ratio} · x{n} (Flow ẩn cấu hình).",
            )
        if not (prompt or "").strip():
            raise ValueError("prompt rỗng")
        prompt = (prompt or "").strip()

        # Collect & resolve all reference image paths (only in ingredients mode)
        actual_ref_paths: list[Path] = []
        if sub == "ingredients":
            if reference_image_paths:
                for rp in reference_image_paths:
                    if rp:
                        p = resolve_input_path(rp)
                        if p.is_file() and p.resolve() not in actual_ref_paths:
                            actual_ref_paths.append(p.resolve())
            if reference_image_path:
                p = resolve_input_path(reference_image_path)
                if p.is_file() and p.resolve() not in actual_ref_paths:
                    actual_ref_paths.insert(0, p.resolve())
            if frame_path:
                p = resolve_input_path(frame_path)
                if p.is_file() and p.resolve() not in actual_ref_paths:
                    actual_ref_paths.append(p.resolve())

        with self._lock:
            project = self.resolve_project(project_id, workspace_project_id=workspace_project_id, on_event=on_event)
            run_id, run_dir = _unique_run_dir(self.out_root, "video")
            last_frame: Optional[Path] = None
            if wants_last_frame:
                last_frame = resolve_input_path(last_frame_path)  # type: ignore[arg-type]
                if not last_frame.is_file():
                    raise FileNotFoundError(f"Không tìm thấy ảnh khung 'Kết thúc': {last_frame_path}")
            frame_source: Optional[Literal["provided", "generated"]] = None
            frame: Optional[Path] = None
            planned_image_prompt: Optional[str] = None
            image_status: Optional[str] = None

            if sub == "ingredients":
                if actual_ref_paths:
                    frame = actual_ref_paths[0]
                    frame_source = "provided"
                    self._emit(
                        on_event,
                        "info",
                        f"Dùng {len(actual_ref_paths)} ảnh tham chiếu làm thành phần (ingredients): "
                        f"{', '.join(p.name for p in actual_ref_paths)}",
                    )
                else:
                    self._emit(
                        on_event,
                        "info",
                        "Sub-mode 'Thành phần' tạo video từ câu lệnh (không kèm ảnh tham chiếu).",
                    )
            elif frame_path:
                src = resolve_input_path(frame_path)
                if not src.is_file():
                    raise FileNotFoundError(f"Không tìm thấy ảnh đính kèm: {frame_path}")
                frame = run_dir / f"starting_frame{src.suffix or '.png'}"
                if src != frame:
                    shutil.copy(src, frame)
                frame_source = "provided"
                self._emit(on_event, "info", f"Dùng ảnh đính kèm làm starting frame: {src.name}")
            elif auto_image:
                planned_image_prompt = (image_prompt or prompt).strip()
                img_res = self.generate_image(
                    prompt=planned_image_prompt,
                    aspect_ratio=image_aspect_ratio,
                    project_id=project_id,
                    workspace_project_id=workspace_project_id,
                    dry_run=dry_run,
                    remove_watermark=remove_watermark,
                    on_event=on_event,
                )
                image_status = img_res.status
                if img_res.project_id:
                    project = img_res.project_id
                if img_res.file_path:
                    frame = run_dir / f"starting_frame{Path(img_res.file_path).suffix or '.png'}"
                    shutil.copy(img_res.file_path, frame)
                    frame_source = "generated"
                elif not dry_run:
                    raise RuntimeError(
                        f"Không tạo được ảnh khung hình cho video: {img_res.reason or img_res.status} "
                        f"({img_res.hint or 'không có hint'})"
                    )
            else:
                raise UnsupportedOptionError(
                    "Sub-mode 'Khung hình' (image→video) cần ảnh đính kèm (frame_path) hoặc "
                    "bật auto_image=True để tạo ảnh trước; dùng sub_mode='ingredients' nếu "
                    "chỉ muốn text→video từ câu lệnh."
                )

            result = NodeVideoResult(
                status="dry_run" if dry_run else "ok",
                prompt=prompt,
                aspect_ratio=ratio,
                run_id=run_id,
                run_dir=str(run_dir),
                project_id=project,
                seed_used=seed,
                resolution=res_label,
                duration_s=duration,
                frame_path=str(frame) if frame else None,
                frame_source=frame_source,
                last_frame_path=str(last_frame) if last_frame else None,
                reference_image_paths=[str(p) for p in actual_ref_paths] if actual_ref_paths else None,
                image_prompt=planned_image_prompt,
                dry_run=dry_run,
                model=model_info.id,
                model_label=model_info.label,
                # A video reference takes the `jIps6` path, whose key is `abra_edit`: the
                # duration lives in the clip, so the plan's Omni key would misreport it.
                model_key=VIDEO_EDIT_MODEL_KEY if video_reference_title is not None else model_key,
                sub_mode=sub,
                count=n,
                agent_mode=agent_mode,
            )

            if dry_run:
                if image_status:
                    result.hint = f"Chuỗi image→video: ảnh dự kiến status={image_status} (dry-run, không tạo file)."
                self._emit(
                    on_event,
                    "info",
                    f"[DRY-RUN] Không gọi bridge video, không tạo file. "
                    f"model={model_info.label} ({model_key}), sub_mode={sub}, x{n}, "
                    f"{ratio} {res_label} {duration}s",
                )
                result.elapsed_s = round(time.time() - t0, 2)
                self._write_manifest(result)
                return result

            video_path = run_dir / "video.mp4"
            if sub == "ingredients":
                ref_desc = f"kèm {len(actual_ref_paths)} ảnh tham chiếu" if actual_ref_paths else "không cần frame"
                self._emit(
                    on_event,
                    "step",
                    f"Tạo video text→video {ratio} {res_label} {duration}s "
                    f"({model_info.label} · {model_key} · x{n}) — {ref_desc}",
                )
                self.generate_text_video(
                    prompt=prompt,
                    dest_path=video_path,
                    aspect_ratio=ratio,
                    seed=seed,
                    resolution=res_label,
                    duration_s=duration,
                    project_id=project,
                    workspace_project_id=workspace_project_id,
                    timeout_s=timeout_s,
                    model=model_info.id,
                    count=n,
                    reference_paths=actual_ref_paths if actual_ref_paths else None,
                    video_reference_title=video_reference_title,
                    on_event=on_event,
                )
            else:
                if frame is None:
                    raise RuntimeError("Thiếu starting frame sau bước chuẩn bị ảnh.")
                self._emit(
                    on_event,
                    "step",
                    f"Tạo video {ratio} {res_label} {duration}s từ {frame_source or '?'} frame "
                    f"({model_info.label} · {model_key} · x{n})",
                )
                self.animate_frame(
                    frame_path=frame,
                    prompt=prompt,
                    dest_path=video_path,
                    aspect_ratio=ratio,
                    seed=seed,
                    resolution=res_label,
                    duration_s=duration,
                    project_id=project,
                    workspace_project_id=workspace_project_id,
                    timeout_s=timeout_s,
                    model=model_info.id,
                    count=n,
                    last_frame_path=last_frame,
                    on_event=on_event,
                )
            if self._project_cache:
                result.project_id = self._project_cache
            result.video_path = str(video_path) if video_path.is_file() else None
            result.video_bytes = video_path.stat().st_size if video_path.is_file() else None

            if remove_watermark and video_path.is_file():
                self._emit(on_event, "step", "Xóa watermark (✦) trên video…")
                try:
                    remove_video_watermark(video_path, log=lambda kind, msg: self._emit(on_event, kind, msg))
                    result.watermark_removed = True
                    result.video_bytes = video_path.stat().st_size
                except Exception as exc:  # noqa: BLE001 - keep the render, warn only
                    self._emit(on_event, "warn", f"Xóa watermark video bỏ qua: {exc}")

            # Đo thật thay vì tin `duration_s` (tham số yêu cầu). Editor dựng phim đọc
            # thẳng manifest, nếu ghi số yêu cầu thì timeline lệch mà không ai biết.
            if video_path.is_file():
                info = probe_video(video_path)
                result.measured_duration_s = info.duration_s
                result.measured_fps = info.fps
                result.measured_width = info.width
                result.measured_height = info.height
                result.has_audio = info.has_audio
                if info.measured and info.duration_s is not None:
                    self._emit(
                        on_event, "info",
                        f"Đo được: {info.width}×{info.height} @ {info.fps or '?'}fps, "
                        f"{info.duration_s}s, audio={'có' if info.has_audio else 'không'}",
                    )
                elif info.error:
                    self._emit(on_event, "warn", f"Không đo được thông số video: {info.error}")

            result.elapsed_s = round(time.time() - t0, 2)
            self._write_manifest(result)
            self._emit(on_event, "done", f"Video xong: {video_path.name} ({result.video_bytes or 0} bytes)")
            return result

    def _write_manifest(self, result: NodeVideoResult) -> None:
        try:
            Path(result.run_dir, "manifest.json").write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "AspectNotVerifiedError",
    "UnsupportedOptionError",
    "MediaService",
    "NodeImageResult",
    "NodeVideoResult",
    "DEFAULT_NODE_OUT",
    "IMAGE_ASPECT_CONFIG",
    "VIDEO_RATIOS",
    "VIDEO_RESOLUTIONS",
    "VIDEO_DURATIONS_S",
    "VIDEO_DURATION_S",
    "VERIFIED_IMAGE_ASPECTS",
    "cdp_lock",
    "load_image_aspects",
    "node_options",
    "normalize_video_ratio",
    "normalize_video_resolution",
    "plan_video_submit",
    "resolve_image_aspect",
    "resolve_input_path",
    "validate_video_duration",
]

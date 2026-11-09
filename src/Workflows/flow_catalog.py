"""Flow option catalog — the single source of truth for composer configuration.

Why this module exists: the node UI used to hard-code a few ratios in React and the
backend hard-coded one model key (``BELUGA``). Google Flow actually exposes a whole
matrix (mode, aspect, model, resolution, duration, count) plus a separate text-to-video
sub-mode, and the matrix of *which options exist* depends on the selected model.

Everything here is **Observed Evidence**, captured 0-credit from the real composer by
blocking every ``/data/batchexecute`` right before clicking Generate
(see ``.turbo/node-config-parity/matrix.md`` and ``discovery/probe_*.py``). Never add a
key that was not captured — a guessed model key spends credits and fails.

Layout of the runtime payloads this module feeds:

Image (``ogiZ0b``), per spec::

    spec[3] = seed (int32)   spec[4] = aspect enum   spec[5] = model key
    args = [None, [spec, spec, ...], 1, ref, [gen_id]]     # count == len(args[1])

Video image→video (``eb1hJf``), per spec::

    spec[1] = model key   spec[2] = aspect enum   spec[4] = [None, sf_media_id, ...]
    spec[9] = [4]         # only for 360p, which makes the spec 10 long instead of 6

Video text→video (``YhhmEf``), per spec::

    spec[1] = model key   spec[2] = aspect enum   spec[4] = [None, None, None, None, u1, u2]
    spec[7] = [4]         # only for 360p, spec 8 long instead of 5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.Bridge.flow_video.constants import OMNI12_MAX_DURATION_S_WITH_LAST_FRAME

IMAGE_ASPECT_ENUM: dict[str, int] = {
    # captured from the blocked ogiZ0b request, one per composer radio
    "16:9": 3,
    "9:16": 2,
    "4:3": 5,
    "1:1": 1,
    "3:4": 4,
}

#: Composer order (left→right) as rendered by Google Flow.
IMAGE_ASPECT_ORDER: tuple[str, ...] = ("16:9", "4:3", "1:1", "3:4", "9:16")

VIDEO_ASPECT_ENUM: dict[str, int] = {"9:16": 1, "16:9": 2}
VIDEO_ASPECT_ORDER: tuple[str, ...] = ("16:9", "9:16")

VIDEO_SUB_MODES: tuple[str, ...] = ("frames", "ingredients")
VIDEO_SUB_MODE_LABELS: dict[str, str] = {
    "frames": "Khung hình",
    "ingredients": "Thành phần",
}
VIDEO_SUB_MODE_DESCRIPTIONS: dict[str, str] = {
    "frames": "Ảnh → video: cần ảnh khung hình bắt đầu (RPC eb1hJf).",
    "ingredients": "Thành phần: prompt và ảnh tham chiếu tuỳ chọn (RPC YhhmEf).",
}

COUNTS: tuple[int, ...] = (1, 2, 3, 4)


@dataclass(frozen=True)
class MediaModel:
    """One composer model.

    ``keys`` maps a *context* to the model key sent to Google. Contexts:

    * ``"i2v_916"`` / ``"i2v_169"`` — image→video, portrait / landscape
    * ``"t2v_916"`` / ``"t2v_169"`` — text→video, portrait / landscape
    * ``"i2v_dur"`` / ``"t2v_dur"`` — the key is a function of duration
      (``"{dur}"`` placeholder), used by Omni

    A missing context means "Flow does not offer that combination"; callers must
    raise instead of inventing a key.
    """

    id: str
    label: str
    #: Captured keys; ``{dur}`` is substituted with the duration in seconds.
    keys: dict[str, str]
    #: Whether the composer offers the resolution group for this model.
    has_resolution: bool = True
    #: Whether the composer offers the duration group for this model.
    has_duration: bool = True
    #: Durations the composer offers (seconds). Ignored when ``has_duration`` is False.
    durations_s: tuple[int, ...] = (4, 6, 8, 10)
    #: Resolution used when the model exposes no resolution group.
    fixed_resolution: str = "720p"
    #: Duration used when the model exposes no duration group.
    fixed_duration_s: int = 8
    #: Aspect ratios the model accepts (empty = all of ``VIDEO_ASPECT_ORDER``).
    aspect_ratios: tuple[str, ...] = ()
    #: Flow's own "this model retires on <date>" note, verbatim, when the menu shows one.
    deprecated_note: str = ""

    def aspects(self) -> tuple[str, ...]:
        return self.aspect_ratios or VIDEO_ASPECT_ORDER

    @property
    def is_deprecated(self) -> bool:
        return bool(self.deprecated_note)


IMAGE_MODELS: tuple[MediaModel, ...] = (
    MediaModel(
        id="nano_banana_pro",
        label="Nano Banana Pro",
        keys={"image": "GEM_PIX_2"},
    ),
    MediaModel(
        id="nano_banana_2_lite",
        label="Nano Banana 2 Lite",
        keys={"image": "HARBOR_SEAL"},
    ),
    MediaModel(
        id="nano_banana_2_1",
        label="Nano Banana 2.1",
        keys={"image": "BELUGA"},
    ),
)

VIDEO_MODELS: tuple[MediaModel, ...] = (
    MediaModel(
        id="omni_1_2_flash",
        label="Omni 1.2 Flash",
        keys={
            "i2v_dur": "macaron_cookie_i2v_{dur}s",
            "i2v_fl_dur": "macaron_cookie_i2v_fl_{dur}s",
            "t2v_dur": "macaron_cookie_t2v_{dur}s",
            "r2v_dur": "macaron_cookie_r2v_{dur}s",
        },
        has_resolution=True,
        has_duration=True,
        # Observed 2026-11-09: the 4/6/8/10 radios are gone; a 3..15s slider took over.
        durations_s=tuple(range(3, 16)),
        fixed_duration_s=8,
    ),
    MediaModel(
        id="omni_1_1_flash",
        label="Omni 1.1 Flash",
        keys={
            "i2v_dur": "abra_i2v_{dur}s",
            "t2v_dur": "abra_t2v_{dur}s",
        },
        has_resolution=True,
        has_duration=True,
        #: Flow flags this model "Sẽ ngừng hoạt động vào ngày 5 thg 12" (retires 2026-12-05).
        deprecated_note="Sẽ ngừng hoạt động vào ngày 5 thg 12",
    ),
    MediaModel(
        id="veo_3_1_lite",
        label="Veo 3.1 - Lite",
        keys={
            "i2v_916": "veo_3_1_i2v_lite",
            "i2v_169": "veo_3_1_i2v_lite",
            "t2v_916": "veo_3_1_t2v_lite",
            "t2v_169": "veo_3_1_t2v_lite",
        },
        # Observed: picking a Veo model removes the resolution + duration groups entirely.
        has_resolution=False,
        has_duration=False,
    ),
    MediaModel(
        id="veo_3_1_fast",
        label="Veo 3.1 - Fast",
        keys={
            "i2v_916": "veo_3_1_i2v_s_fast_portrait",
            "i2v_169": "veo_3_1_i2v_s_fast",
            "t2v_916": "veo_3_1_t2v_fast_portrait",
            "t2v_169": "veo_3_1_t2v_fast",
        },
        has_resolution=False,
        has_duration=False,
        deprecated_note="Sẽ ngừng hoạt động vào ngày 5 thg 12",
    ),
    MediaModel(
        id="veo_3_1_quality",
        label="Veo 3.1 - Quality",
        keys={
            "i2v_916": "veo_3_1_i2v_s_portrait",
            "i2v_169": "veo_3_1_i2v_s",
            "t2v_916": "veo_3_1_t2v_portrait",
            "t2v_169": "veo_3_1_t2v",
        },
        has_resolution=False,
        has_duration=False,
        deprecated_note="Sẽ ngừng hoạt động vào ngày 5 thg 12",
    ),
)

IMAGE_MODELS_BY_ID: dict[str, MediaModel] = {m.id: m for m in IMAGE_MODELS}
VIDEO_MODELS_BY_ID: dict[str, MediaModel] = {m.id: m for m in VIDEO_MODELS}

#: Label → id aliases so requests that still send the human label keep working.
IMAGE_MODEL_ALIASES: dict[str, str] = {
    **{m.id: m.id for m in IMAGE_MODELS},
    **{m.label.lower(): m.id for m in IMAGE_MODELS},
    **{f"🍌 {m.label}".lower(): m.id for m in IMAGE_MODELS},
    #: The pre-parity default — Nano Banana 2.1.
    "beluga": "nano_banana_2_1",
    "gem_pix_2": "nano_banana_pro",
    "harbor_seal": "nano_banana_2_lite",
}

VIDEO_MODEL_ALIASES: dict[str, str] = {
    **{m.id: m.id for m in VIDEO_MODELS},
    **{m.label.lower(): m.id for m in VIDEO_MODELS},
    #: Omni 1.2 Flash is the live default; the `macaron_cookie_*` family is not an alias
    #: a caller should type, but an old stored config may name it.
    "omni 1.2": "omni_1_2_flash",
    "omni_1.2_flash": "omni_1_2_flash",
}


class CatalogError(ValueError):
    """Raised when a model/option combination was never observed in Flow."""


def _norm(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def resolve_image_model(value: Optional[str]) -> MediaModel:
    """Resolve an id / label / legacy key to an image model (default: Nano Banana 2.1)."""
    key = _norm(value)
    if not key:
        return IMAGE_MODELS_BY_ID["nano_banana_2_1"]
    model_id = IMAGE_MODEL_ALIASES.get(key)
    if not model_id:
        known = ", ".join(m.id for m in IMAGE_MODELS)
        raise CatalogError(f"Mô hình ảnh {value!r} chưa capture. Đã biết: {known}.")
    return IMAGE_MODELS_BY_ID[model_id]


def resolve_video_model(value: Optional[str]) -> MediaModel:
    """Resolve an id / label to a video model (default: Omni 1.2 Flash)."""
    key = _norm(value)
    if not key:
        return VIDEO_MODELS_BY_ID["omni_1_2_flash"]
    model_id = VIDEO_MODEL_ALIASES.get(key)
    if not model_id:
        known = ", ".join(m.id for m in VIDEO_MODELS)
        raise CatalogError(f"Mô hình video {value!r} chưa capture. Đã biết: {known}.")
    return VIDEO_MODELS_BY_ID[model_id]


def normalize_count(value: object) -> int:
    """Clamp a batch count to what the composer offers (x1..x4)."""
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = 1
    if n not in COUNTS:
        raise CatalogError(f"Số lượng phải là một trong {COUNTS} (nhận {value!r}).")
    return n


def image_model_key(model: MediaModel | str | None) -> str:
    m = model if isinstance(model, MediaModel) else resolve_image_model(model)  # type: ignore[arg-type]
    key = m.keys.get("image")
    if not key:
        raise CatalogError(f"Mô hình ảnh {m.id} không có model key đã capture.")
    return key


def image_aspect_enum(aspect_ratio: str) -> int:
    label = str(aspect_ratio or "").strip()
    if label not in IMAGE_ASPECT_ENUM:
        known = ", ".join(f"{k}={v}" for k, v in IMAGE_ASPECT_ENUM.items())
        raise CatalogError(f"Tỷ lệ ảnh {aspect_ratio!r} chưa capture enum. Đã biết: {known}.")
    return IMAGE_ASPECT_ENUM[label]


def _aspect_suffix(aspect_ratio: str) -> str:
    label = str(aspect_ratio or "").strip()
    if label not in VIDEO_ASPECT_ENUM:
        raise CatalogError(
            f"Video chỉ hỗ trợ tỷ lệ {', '.join(VIDEO_ASPECT_ORDER)} (nhận {aspect_ratio!r})."
        )
    return "916" if label == "9:16" else "169"


def video_model_key(
    model: MediaModel | str | None,
    *,
    sub_mode: str = "frames",
    duration_s: int = 8,
    resolution: str = "720p",
    aspect_ratio: str = "9:16",
    has_last_frame: bool = False,
    has_references: bool = False,
) -> str:
    """Model key for a video submit, or :class:`CatalogError` for unobserved combos.

    ``sub_mode`` is ``"frames"`` (image→video) or ``"ingredients"`` (text/video→video).
    ``has_last_frame`` selects the first+last-frame key on models that captured one; with
    both frame slots filled Flow's duration window shrinks to 3..10s.
    ``has_references`` selects the ``r2v`` (reference→video) family inside ``ingredients``:
    the same composer sub-mode sends ``macaron_cookie_t2v_*`` without ingredient chips and
    ``macaron_cookie_r2v_*`` with them (observed 2026-11-09).
    """
    m = model if isinstance(model, MediaModel) else resolve_video_model(model)  # type: ignore[arg-type]
    sub = _norm(sub_mode) or "frames"
    if sub not in VIDEO_SUB_MODES:
        raise CatalogError(f"Sub-mode video {sub_mode!r} chưa capture. Đã biết: {', '.join(VIDEO_SUB_MODES)}.")

    aspect = _aspect_suffix(aspect_ratio)
    prefix = "i2v" if sub == "frames" else "t2v"
    if has_last_frame:
        if sub != "frames":
            raise CatalogError("Khung 'Kết thúc' chỉ có ở sub-mode 'Khung hình'.")
        prefix = "i2v_fl"
    elif has_references and sub == "ingredients":
        if "r2v_dur" not in m.keys:
            raise CatalogError(
                f"{m.label} chưa capture model key r2v (video từ ảnh tham chiếu)."
            )
        prefix = "r2v"
    elif has_references:
        raise CatalogError("Ảnh tham chiếu chỉ có ở sub-mode 'Thành phần'.")

    if m.has_duration:
        dur = int(duration_s)
        allowed = video_durations(m, has_last_frame=has_last_frame)
        if dur not in allowed:
            raise CatalogError(
                f"{m.label} chỉ hỗ trợ duration {allowed[0]}..{allowed[-1]}s"
                f"{' (có khung Kết thúc)' if has_last_frame else ''} (nhận {duration_s}s)."
            )
        template = m.keys.get(f"{prefix}_dur")
        if not template:
            raise CatalogError(
                f"{m.label} không có model key {prefix} (duration-based) đã capture."
            )
        key = template.replace("{dur}", str(dur))
        if _norm(resolution) == "360p":
            # Captured: 360p appends the suffix instead of a separate slot.
            key = f"{key}_360p"
        return key

    # Fixed-duration model (Veo): the aspect is baked into the key.
    if _norm(resolution) == "360p":
        raise CatalogError(f"{m.label} không hỗ trợ 360p (composer ẩn nhóm độ phân giải).")
    if m.has_duration is False and int(duration_s) != m.fixed_duration_s:
        raise CatalogError(
            f"{m.label} cố định {m.fixed_duration_s}s (composer ẩn nhóm thời lượng), "
            f"nhận {duration_s}s."
        )
    key = m.keys.get(f"{prefix}_{aspect}")
    if not key:
        raise CatalogError(
            f"{m.label} không có model key {prefix} cho tỷ lệ {aspect_ratio} đã capture."
        )
    return key


def video_durations(model: MediaModel | str | None, *, has_last_frame: bool = False) -> tuple[int, ...]:
    """Durations the composer offers for ``model``.

    Flow narrows the range when the fringe state changes: with both frame slots filled
    Omni 1.2's slider stops at 10s (observed 2026-11-09).
    """
    m = model if isinstance(model, MediaModel) else resolve_video_model(model)  # type: ignore[arg-type]
    if not m.has_duration:
        return (m.fixed_duration_s,)
    if has_last_frame:
        capped = tuple(d for d in m.durations_s if d <= OMNI12_MAX_DURATION_S_WITH_LAST_FRAME)
        if capped:
            return capped
    return m.durations_s


def video_resolutions(model: MediaModel | str | None) -> tuple[str, ...]:
    """Resolutions the composer offers for ``model``.

    ``1080p`` is *not* a Flow composer option: it is our own post-step that runs
    ``p0UkFb`` (``veo_3_1_upsampler_1080p``) on the downloaded 720p file, so it is
    derived rather than captured.
    """
    m = model if isinstance(model, MediaModel) else resolve_video_model(model)  # type: ignore[arg-type]
    base: tuple[str, ...] = ("360p", "720p") if m.has_resolution else (m.fixed_resolution,)
    return (*base, "1080p")


def capture_resolution(model: MediaModel | str | None, resolution: Optional[str]) -> str:
    """Resolution that must be *requested from Flow* for ``resolution``.

    1080p is produced by upsampling the 720p render, so the submit still asks for 720p.
    """
    m = model if isinstance(model, MediaModel) else resolve_video_model(model)  # type: ignore[arg-type]
    want = _norm(resolution) or "720p"
    if want in ("1080", "1080p", "fullhd", "full-hd"):
        return m.fixed_resolution if not m.has_resolution else "720p"
    if want in ("720", "720p", "hd"):
        want = "720p"
    if want in ("360", "360p"):
        want = "360p"
    if want not in video_resolutions(m):
        raise CatalogError(f"{m.label} không hỗ trợ độ phân giải {resolution!r}.")
    if want == "360p" and not m.has_resolution:
        raise CatalogError(f"{m.label} không hỗ trợ 360p.")
    return want


def video_sub_modes_for(model: MediaModel | str | None) -> tuple[str, ...]:
    """Both sub-modes were observed for every video model."""
    resolve_video_model(model)  # validates the model name
    return VIDEO_SUB_MODES


def image_catalog() -> dict:
    """Serializable image option block for ``GET /api/node/options``."""
    return {
        "modes": ["image", "video"],
        "mode_labels": {"image": "Hình ảnh", "video": "Video"},
        "aspect_ratios": list(IMAGE_ASPECT_ORDER),
        "aspect_enums": dict(IMAGE_ASPECT_ENUM),
        "default_aspect_ratio": "16:9",
        "models": [
            {"id": m.id, "label": m.label, "model_key": m.keys.get("image")}
            for m in IMAGE_MODELS
        ],
        "default_model": "nano_banana_2_1",
        "counts": list(COUNTS),
        "default_count": 1,
        "supports_reference_image": True,
        "supports_seed": True,
        "supports_watermark_removal": True,
    }


def video_catalog() -> dict:
    """Serializable video option block for ``GET /api/node/options``."""
    models = []
    for m in VIDEO_MODELS:
        models.append(
            {
                "id": m.id,
                "label": m.label,
                "aspect_ratios": list(m.aspects()),
                "resolutions": list(video_resolutions(m)),
                "durations_s": list(video_durations(m)),
                "durations_with_last_frame_s": list(video_durations(m, has_last_frame=True)),
                "has_resolution": m.has_resolution,
                "has_duration": m.has_duration,
                "has_last_frame": "i2v_fl_dur" in m.keys,
                "has_reference_video": m.id == "omni_1_2_flash",
                "is_deprecated": m.is_deprecated,
                "deprecated_note": m.deprecated_note,
                "model_keys": {
                    sub: {
                        aspect: video_model_key(m, sub_mode=sub, aspect_ratio=aspect,
                                                duration_s=video_durations(m)[0],
                                                resolution=capture_resolution(m, "720p"))
                        for aspect in m.aspects()
                    }
                    for sub in VIDEO_SUB_MODES
                },
            }
        )
    return {
        "modes": ["image", "video"],
        "sub_modes": list(VIDEO_SUB_MODES),
        "sub_mode_labels": dict(VIDEO_SUB_MODE_LABELS),
        "sub_mode_descriptions": dict(VIDEO_SUB_MODE_DESCRIPTIONS),
        "default_sub_mode": "frames",
        "aspect_ratios": list(VIDEO_ASPECT_ORDER),
        "aspect_enums": dict(VIDEO_ASPECT_ENUM),
        "default_aspect_ratio": "9:16",
        "models": models,
        "default_model": "omni_1_2_flash",
        "counts": list(COUNTS),
        "default_count": 1,
        "supports_starting_frame": True,
        "supports_last_frame": True,
        "supports_video_reference": True,
        "supports_text_to_video": True,
        "auto_image_chain": True,
        "supports_seed": True,
        "supports_watermark_removal": True,
    }


def agent_mode_catalog() -> dict:
    """What the composer allows while ``Tác nhân`` (Agent) is enabled.

    Observed: enabling the agent empties and hides ``button.settings-trigger-button``
    (0×0), so model/aspect/resolution/duration/count are no longer user-selectable.
    The extra ``tune`` button only holds canvas display settings.
    """
    return {
        "supported": True,
        "locks_config": True,
        "note": (
            "Bật 'Tác nhân' thì Flow ẩn toàn bộ cấu hình model/tỷ lệ/độ phân giải/thời lượng/"
            "số lượng — tác nhân tự quyết. Node chỉ gửi prompt."
        ),
        "locked_fields": [
            "model",
            "aspect_ratio",
            "resolution",
            "duration_s",
            "count",
            "sub_mode",
        ],
        "extra_buttons": [
            {"id": "tune", "label": "Cài đặt", "purpose": "canvas display settings"},
            {"id": "article_spark", "label": "Chỉ dẫn cho tác nhân"},
        ],
    }


__all__ = [
    "COUNTS",
    "CatalogError",
    "IMAGE_ASPECT_ENUM",
    "IMAGE_ASPECT_ORDER",
    "IMAGE_MODELS",
    "MediaModel",
    "VIDEO_ASPECT_ENUM",
    "VIDEO_ASPECT_ORDER",
    "VIDEO_MODELS",
    "VIDEO_SUB_MODES",
    "VIDEO_SUB_MODE_LABELS",
    "agent_mode_catalog",
    "capture_resolution",
    "image_aspect_enum",
    "image_catalog",
    "image_model_key",
    "normalize_count",
    "resolve_image_model",
    "resolve_video_model",
    "video_catalog",
    "video_durations",
    "video_model_key",
    "video_resolutions",
    "video_sub_modes_for",
]

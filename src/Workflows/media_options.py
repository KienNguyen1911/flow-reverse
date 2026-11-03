"""Video submit options — the single place that turns a request into a Flow submit.

A video submit needs eight values that must agree with each other: the aspect label, the model,
the sub-mode, the resolution the user asked for, the resolution Flow must actually be asked for
(1080p is an upsample of a 720p capture), the duration, the count, and the model key that encodes
all of them. Getting one of them out of step produces a key Flow rejects ("chưa capture") or,
worse, a key that uploads at the wrong setting.

That derivation used to be written out three times — in ``animate_frame``,
``generate_text_video`` and ``generate_video`` — with the copies drifting in small ways (one
validated the sub-mode, two did not; one computed the key before checking the prompt, others
after). It lives here once, and :func:`plan_video_submit` is the only way to produce it.

Two rules this module enforces:

* **The catalogue is the source of truth.** :data:`VIDEO_RESOLUTIONS` and
  :data:`VIDEO_DURATIONS_S` are *derived* from :mod:`src.Workflows.flow_catalog`, not restated.
  The old module-level tuples claimed to be "kept in sync" with the catalogue in a comment,
  which is not a mechanism.
* **Agent mode collapses before validation.** The composer's "Tác nhân" chip hides the config
  groups, so a request that supplies a resolution or duration in that mode must not fail — those
  values are discarded, not checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .flow_catalog import (
    VIDEO_ASPECT_ORDER,
    VIDEO_SUB_MODES,
    MediaModel,
    capture_resolution,
    normalize_count,
    resolve_video_model,
    video_durations,
    video_model_key,
    video_resolutions,
)


class UnsupportedOptionError(ValueError):
    """Raised for options the Flow protocol does not support."""


#: Free-form aliases accepted for image and video ratios.
RATIO_ALIASES: dict[str, str] = {
    "portrait": "9:16",
    "vertical": "9:16",
    "landscape": "16:9",
    "horizontal": "16:9",
    "wide": "16:9",
    "square": "1:1",
}


def normalize_ratio_label(value: str) -> str:
    """Fold spacing, ``x``/``/`` separators and aliases into a canonical ratio label."""
    s = str(value or "").strip().lower().replace(" ", "")
    s = s.replace("x", ":").replace("/", ":")
    return RATIO_ALIASES.get(s, s)


VIDEO_RATIOS: tuple[str, ...] = VIDEO_ASPECT_ORDER

#: Every resolution we can deliver, derived from the catalogue. The last entry is always our
#: upsampled 1080p; the catalogue decides which capture resolutions sit below it.
VIDEO_RESOLUTIONS: tuple[str, ...] = video_resolutions(None)

#: Durations the default model offers, derived from the catalogue.
VIDEO_DURATIONS_S: tuple[int, ...] = video_durations(None)

#: Legacy default duration, kept for callers that omit ``duration_s``.
VIDEO_DURATION_S: int = 8

#: Composer defaults applied when "Tác nhân" hides the config groups.
AGENT_DEFAULTS = {
    "aspect_ratio": "9:16",
    "resolution": "1080p",
    "count": 1,
}


def normalize_video_ratio(value: Optional[str]) -> str:
    label = normalize_ratio_label(value or "9:16")
    if label not in VIDEO_RATIOS:
        raise UnsupportedOptionError(
            f"Video chỉ hỗ trợ tỷ lệ {', '.join(VIDEO_RATIOS)} (nhận {value!r})."
        )
    return label


def normalize_video_resolution(value: Optional[str], *, model: Optional[str] = None) -> str:
    """Normalize a resolution label; with ``model`` also check Flow offers it."""
    v = str(value or "720p").strip().lower()
    if v in ("720", "720p", "hd"):
        label = "720p"
    elif v in ("1080", "1080p", "fullhd", "full-hd"):
        label = "1080p"
    elif v in ("360", "360p"):
        label = "360p"
    else:
        raise UnsupportedOptionError(
            f"Độ phân giải video chỉ hỗ trợ {'/'.join(VIDEO_RESOLUTIONS)} (nhận {value!r})."
        )
    if model:
        m = resolve_video_model(model)
        if label not in video_resolutions(m):
            raise UnsupportedOptionError(
                f"{m.label} không hỗ trợ {label}. Chọn: {', '.join(video_resolutions(m))}."
            )
    return label


def validate_video_duration(duration_s: int, *, model: Optional[str] = None) -> int:
    """Normalize a duration; with ``model`` also check Flow offers it."""
    d = int(duration_s)
    allowed = video_durations(model)
    if d not in allowed:
        hint = (
            f"{resolve_video_model(model).label} cố định {allowed[0]}s."
            if len(allowed) == 1
            else f"Chọn: {', '.join(f'{x}s' for x in allowed)}."
        )
        raise UnsupportedOptionError(f"Video không hỗ trợ {d}s. {hint}")
    return d


def validate_sub_mode(sub_mode: Optional[str]) -> str:
    sub = str(sub_mode or "frames").strip().lower()
    if sub not in VIDEO_SUB_MODES:
        raise UnsupportedOptionError(
            f"Sub-mode video {sub_mode!r} không hợp lệ. Chọn: {', '.join(VIDEO_SUB_MODES)}."
        )
    return sub


@dataclass(frozen=True)
class VideoSubmitPlan:
    """Everything one video submit needs, resolved and mutually consistent.

    Build it with :func:`plan_video_submit`; never assemble one by hand, or you reintroduce the
    derived-key drift this type exists to prevent.
    """

    #: User-facing aspect label, e.g. ``"9:16"``.
    ratio: str
    #: Resolved model from the catalogue.
    model: MediaModel
    #: ``"frames"`` (image→video) or ``"ingredients"`` (text→video).
    sub_mode: str
    #: User-facing resolution label, e.g. ``"1080p"``.
    resolution: str
    #: Resolution Flow must actually be asked for (1080p captures at 720p).
    capture_res: str
    duration_s: int
    count: int
    #: Captured model key encoding model + sub-mode + duration + resolution + aspect.
    model_key: str
    #: True when "Tác nhân" discarded the caller's config.
    agent_mode: bool = False

    @property
    def offers_resolution(self) -> bool:
        """Whether the composer shows a resolution group for this model."""
        return self.model.has_resolution

    @property
    def offers_duration(self) -> bool:
        """Whether the composer shows a duration group for this model."""
        return self.model.has_duration

    def describe(self) -> str:
        """Short, log-friendly summary of the submit."""
        return (
            f"{self.model.label} · {self.model_key} · {self.sub_mode} · "
            f"x{self.count} · {self.ratio} {self.resolution} {self.duration_s}s"
        )


def plan_video_submit(
    *,
    aspect_ratio: Optional[str] = None,
    model: Optional[str] = None,
    sub_mode: Optional[str] = "frames",
    resolution: Optional[str] = "1080p",
    duration_s: int = VIDEO_DURATION_S,
    count: int = 1,
    agent_mode: bool = False,
) -> VideoSubmitPlan:
    """Resolve a video request into a submit plan.

    Validation order is fixed and deliberate: ratio, model, sub-mode, resolution, duration,
    count, then the captured model key. An invalid combination therefore always names the
    shallowest thing that is wrong, not whichever check happened to run first.

    ``agent_mode`` discards the caller's model/ratio/resolution/duration/count *before* any of
    those are validated, mirroring the composer: when the chip is on, Flow hides those groups,
    so a stale value from the UI must not be able to fail the submit.
    """
    if agent_mode:
        model = None
        aspect_ratio = AGENT_DEFAULTS["aspect_ratio"]
        resolution = AGENT_DEFAULTS["resolution"]
        duration_s = VIDEO_DURATION_S
        count = AGENT_DEFAULTS["count"]

    ratio = normalize_video_ratio(aspect_ratio)
    model_info = resolve_video_model(model)
    sub = validate_sub_mode(sub_mode)
    res_label = normalize_video_resolution(resolution, model=model_info.id)
    duration = validate_video_duration(duration_s, model=model_info.id)
    n = normalize_count(count)
    capture_res = capture_resolution(model_info, res_label)
    key = video_model_key(
        model_info,
        sub_mode=sub,
        duration_s=duration,
        resolution=capture_res,
        aspect_ratio=ratio,
    )
    return VideoSubmitPlan(
        ratio=ratio,
        model=model_info,
        sub_mode=sub,
        resolution=res_label,
        capture_res=capture_res,
        duration_s=duration,
        count=n,
        model_key=key,
        agent_mode=agent_mode,
    )


__all__ = [
    "AGENT_DEFAULTS",
    "RATIO_ALIASES",
    "UnsupportedOptionError",
    "VIDEO_DURATIONS_S",
    "VIDEO_DURATION_S",
    "VIDEO_RATIOS",
    "VIDEO_RESOLUTIONS",
    "VideoSubmitPlan",
    "normalize_ratio_label",
    "normalize_video_ratio",
    "normalize_video_resolution",
    "plan_video_submit",
    "validate_sub_mode",
    "validate_video_duration",
]

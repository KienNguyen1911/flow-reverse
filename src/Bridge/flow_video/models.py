"""Video model keys and the composer rules that select them.

Everything here is **Observed Evidence** captured 0-credit from the live Flow composer
(the probes in ``discovery/`` block ``/data/batchexecute`` right before Generate). A key
that is guessed rather than captured spends credit and fails with an opaque status, so
the module refuses to invent one.

Which key a submit carries is decided by three independent facts about the request:

* **family** — Omni 1.2 (``macaron_cookie_*``), Omni 1.1 (``abra_*``), Veo 3.1, or the
  video-edit path (``abra_edit``).
* **shape** — how many frames are attached and whether references are images or a video.
  That is *not* the composer's sub-mode name: "Khung hình" with only a first frame is
  ``eb1hJf``, the same sub-mode with both frames is ``nprQif``, and an ingredients-mode
  request whose reference is a video leaves the Omni family entirely (``abra_edit``).
* **duration** — Omni 1.2 has no 4/6/8/10 radios any more; it has a 3..15s slider, and the
  duration is baked into the key for every value in that range. With both frame slots
  filled the slider stops at 10s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import (
    OMNI12_KEY_PREFIX,
    OMNI12_KIND_I2V,
    OMNI12_KIND_I2V_FL,
    OMNI12_KIND_R2V,
    OMNI12_KIND_T2V,
    OMNI12_MAX_DURATION_S,
    OMNI12_MAX_DURATION_S_WITH_LAST_FRAME,
    OMNI12_MIN_DURATION_S,
    VIDEO_EDIT_MODEL_KEY,
    VIDEO_EDIT_RPC,
    VIDEO_INGREDIENTS_SUBMIT_RPC,
    VIDEO_LAST_FRAME_SUBMIT_RPC,
    VIDEO_SUBMIT_RPC,
    VIDEO_TEXT_SUBMIT_RPC,
)


class VideoModelKeyError(ValueError):
    """Raised for a model/duration/frame combination that was never observed in Flow."""


#: The submit shapes, named after what the composer actually sends.
SHAPE_FIRST_FRAME = "first_frame"
SHAPE_FIRST_AND_LAST_FRAME = "first_and_last_frame"
SHAPE_TEXT = "text"
SHAPE_IMAGE_REFS = "image_refs"
SHAPE_VIDEO_REF = "video_ref"

#: shape → the RPC the app fires for it.
SHAPE_RPC: dict[str, str] = {
    SHAPE_FIRST_FRAME: VIDEO_SUBMIT_RPC,
    SHAPE_FIRST_AND_LAST_FRAME: VIDEO_LAST_FRAME_SUBMIT_RPC,
    SHAPE_TEXT: VIDEO_TEXT_SUBMIT_RPC,
    SHAPE_IMAGE_REFS: VIDEO_INGREDIENTS_SUBMIT_RPC,
    SHAPE_VIDEO_REF: VIDEO_EDIT_RPC,
}


def resolve_shape(
    *,
    sub_mode: str,
    has_first_frame: bool,
    has_last_frame: bool = False,
    reference_count: int = 0,
    has_video_reference: bool = False,
) -> str:
    """Which submit shape does this request have?

    Frames-mode requests are decided by *which slots are filled*, not by the sub-mode:
    the composer leaves the last-frame slot visible in both cases and swaps RPC when it
    is used.
    """
    sub = str(sub_mode or "frames").strip().lower()
    if sub == "frames":
        if has_last_frame:
            if not has_first_frame:
                raise VideoModelKeyError(
                    "Khung hình chỉ có khung 'Kết thúc' mà thiếu 'Bắt đầu' — Flow không nhận."
                )
            return SHAPE_FIRST_AND_LAST_FRAME
        if not has_first_frame:
            raise VideoModelKeyError("Khung hình (image→video) cần ảnh khung hình 'Bắt đầu'.")
        return SHAPE_FIRST_FRAME

    if has_video_reference:
        return SHAPE_VIDEO_REF
    if reference_count > 0:
        return SHAPE_IMAGE_REFS
    return SHAPE_TEXT


def submit_rpc_for(shape: str) -> str:
    """RPC the app fires for ``shape``; also the RPC we must fire ourselves."""
    try:
        return SHAPE_RPC[shape]
    except KeyError as exc:
        raise VideoModelKeyError(f"Shape video {shape!r} chưa capture.") from exc


@dataclass(frozen=True)
class Omni12Duration:
    """Omni 1.2's duration window and the slider arithmetic behind it.

    The composer's ``flow-duration-slider`` is an ``input[type=range]`` whose *value* is
    ``seconds - 3``: value 0..12 renders "3 giây".."15 giây". With a last frame attached
    the maximum drops from 12 to 7, i.e. 3..10s.
    """

    min_s: int = OMNI12_MIN_DURATION_S
    max_s: int = OMNI12_MAX_DURATION_S
    slider_offset_s: int = OMNI12_MIN_DURATION_S

    def clamp(self, seconds: int) -> int:
        return max(self.min_s, min(self.max_s, int(seconds)))

    def slider_value(self, seconds: int) -> int:
        """Value to write into the range input for ``seconds``."""
        return self.clamp(seconds) - self.slider_offset_s

    def seconds_from_slider(self, value: int) -> int:
        return int(value) + self.slider_offset_s


def omni12_duration(*, has_last_frame: bool = False) -> Omni12Duration:
    """Omni 1.2's duration window for the current composer state."""
    return Omni12Duration(
        max_s=OMNI12_MAX_DURATION_S_WITH_LAST_FRAME if has_last_frame else OMNI12_MAX_DURATION_S
    )


def omni12_model_key(*, shape: str, duration_s: int, resolution: str = "720p") -> str:
    """Model key Omni 1.2 sends for ``shape`` at ``duration_s``.

    Observed keys (2026-11-09):

        first_frame           macaron_cookie_i2v_<n>s
        first_and_last_frame  macaron_cookie_i2v_fl_<n>s
        text                  macaron_cookie_t2v_<n>s
        image_refs            macaron_cookie_r2v_<n>s

    360p appends ``_360p`` after the duration (``macaron_cookie_i2v_4s_360p``).
    """
    if shape == SHAPE_VIDEO_REF:
        # The reference-video path ignores the duration entirely: the app sent
        # `abra_edit` for a 7s request and put the clip length in spec[0] instead.
        return VIDEO_EDIT_MODEL_KEY

    kind = {
        SHAPE_FIRST_FRAME: OMNI12_KIND_I2V,
        SHAPE_FIRST_AND_LAST_FRAME: OMNI12_KIND_I2V_FL,
        SHAPE_TEXT: OMNI12_KIND_T2V,
        SHAPE_IMAGE_REFS: OMNI12_KIND_R2V,
    }.get(shape)
    if kind is None:
        raise VideoModelKeyError(f"Shape video {shape!r} chưa capture.")

    window = omni12_duration(has_last_frame=shape == SHAPE_FIRST_AND_LAST_FRAME)
    seconds = window.clamp(duration_s)
    key = f"{OMNI12_KEY_PREFIX}_{kind}_{seconds}s"
    if _is_360p(resolution):
        key = f"{key}_360p"
    return key


def _is_360p(resolution: Optional[str]) -> bool:
    return str(resolution or "").strip().lower().startswith("360")


__all__ = [
    "Omni12Duration",
    "SHAPE_FIRST_AND_LAST_FRAME",
    "SHAPE_FIRST_FRAME",
    "SHAPE_IMAGE_REFS",
    "SHAPE_RPC",
    "SHAPE_TEXT",
    "SHAPE_VIDEO_REF",
    "VideoModelKeyError",
    "omni12_duration",
    "omni12_model_key",
    "resolve_shape",
    "submit_rpc_for",
]

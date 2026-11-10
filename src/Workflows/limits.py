"""Operational limits — single source of truth for backend validation and the UI.

Why a module instead of a constant per call-site: the prompt cap used to be
hard-coded in three places (pydantic models, ``FlowClient.generate_image``, and
the React textarea) and they drifted (5000 / 5000 / 2000). Now every layer reads
this module, and the UI gets the numbers from ``GET /api/node/options`` so a
backend-only change is enough.

Resolution order (first hit wins):

1. environment: ``FLOWBENCH_MAX_PROMPT_CHARS``
2. ``configs/limits.json``: ``{"max_prompt_chars": 7200}``
3. the default below

Bad input never disables generation: non-numeric, empty, ≤0 or unset values fall
back to the default, and absurdly large ones are clamped to 200.000.

The result is cached per process: these are startup knobs, not per-request
behavior. Restart the server after editing the config.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
LIMITS_CONFIG = ROOT / "configs" / "limits.json"

#: Google Flow does not publish a hard prompt cap; 7.200 chars comfortably fits
#: a lookbook prompt with detailed garment descriptions and still leaves the
#: composer responsive.
DEFAULT_MAX_PROMPT_CHARS = 7200

_MIN = 1
_MAX = 200_000

_cached: Optional["Limits"] = None


@dataclass(frozen=True)
class Limits:
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS

    def as_dict(self) -> dict:
        return {
            "max_prompt_chars": self.max_prompt_chars,
        }


def _clamp(raw: object, default: int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    # ≤0 gần như chắc chắn là gõ nhầm (sẽ khoá luôn việc sinh ảnh) ⇒ dùng default
    # thay vì kẹp thành 1. Giá trị quá lớn thì kẹp về trần.
    if n < _MIN:
        return default
    if n > _MAX:
        return _MAX
    return n


def _read_config_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_limits(path: Optional[Path | str] = None) -> Limits:
    """Resolve limits from env → JSON file → defaults (cached after first call)."""
    global _cached
    if _cached is not None and path is None:
        return _cached

    cfg = _read_config_file(Path(path) if path else LIMITS_CONFIG)

    prompt = _clamp(
        os.environ.get("FLOWBENCH_MAX_PROMPT_CHARS") or cfg.get("max_prompt_chars"),
        DEFAULT_MAX_PROMPT_CHARS,
    )
    limits = Limits(max_prompt_chars=prompt)
    if path is None:
        _cached = limits
    return limits


def reset_cache() -> None:
    """Drop the cached limits (tests / hot reload)."""
    global _cached
    _cached = None

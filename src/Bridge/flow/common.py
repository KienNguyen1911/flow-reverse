"""Shared constants, tiny helpers and the exception hierarchy of the Flow bridge."""

from __future__ import annotations

import random
from typing import Callable, Optional
from urllib.parse import quote

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

FLOW_ORIGIN = "https://flow.google.com"
DEFAULT_CDP_URL = "http://127.0.0.1:4022"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)

# int32 signed upper bound — seeds must stay < 2^31 (observed [3] INVALID_ARGUMENT otherwise)
SEED_MAX = 2147483647

EventFn = Callable[[str, str, Optional[dict]], None]


def enc(s: str) -> str:
    """encodeURIComponent-compatible percent-encoding (byte-identical, E8 forensics)."""
    return quote(s, safe="!'()*-._~")


def jitter(mean: float, sigma: float, lo: float = 0.0) -> float:
    """Gaussian-paced sleep duration (Humanized Pacing, AGENTS.md §4)."""
    return max(lo, random.gauss(mean, sigma))


def new_seed() -> int:
    """Random int32 seed (the app's own seeds are always < 2^31)."""
    return random.randint(1, SEED_MAX)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class BridgeError(RuntimeError):
    """Base class for all bridge failures."""


class NoFlowTabError(BridgeError):
    pass


class PageInteractionError(BridgeError):
    pass


class CaptureTimeoutError(BridgeError):
    pass


class TokenParseError(BridgeError):
    pass


class FireTimeoutError(BridgeError):
    pass


class HttpStatusError(BridgeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status

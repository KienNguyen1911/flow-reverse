"""Regression tests: video decoy click must never switch the Flow composer to Image mode.

Bug (2026-10-29): `FlowBridge.click_generate` auto-switched the composer to Image mode whenever it
saw "Video" — including when called by `FlowVideoBridge`. The video node therefore clicked
Generate in Image mode -> the decoy request was `ogiZ0b` (image) instead of `eb1hJf`, its reCAPTCHA
token was minted for the image action, and our `eb1hJf` submit was rejected with
PUBLIC_ERROR_UNUSUAL_ACTIVITY.
"""

from __future__ import annotations

import json
import sys

import pytest

from src.Bridge.flow_bridge import FlowBridge
from src.Bridge.flow_video_bridge import parse_video_app_capture


VIDEO_TXT = "Video · 720p · 8s\ncrop_9_16\nx1"
IMAGE_TXT = "Nano Banana 2.1\ncrop_9_16\nx1"


class _FakeEl:
    def __init__(self, page: "_FakePage"):
        self._page = page

    def inner_text(self) -> str:
        return VIDEO_TXT if self._page.mode == "video" else IMAGE_TXT

    def inner_html(self) -> str:
        return "<i>videocam</i>" if self._page.mode == "video" else "<i>crop_9_16</i>"


class _FakeMouse:
    def __init__(self, page: "_FakePage"):
        self._page = page

    def click(self, x, y) -> None:
        self._page.clicks.append(self._page.mode)


class _FakePage:
    def __init__(self, mode: str):
        self.mode = mode
        self.clicks: list[str] = []
        self.mouse = _FakeMouse(self)

    def query_selector(self, sel: str):
        return _FakeEl(self) if "settings-trigger" in sel else None


def _bridge(mode: str, switch_works: bool = True) -> tuple[FlowBridge, _FakePage, list[str]]:
    br = FlowBridge.__new__(FlowBridge)
    page = _FakePage(mode)
    logs: list[str] = []
    br.page = page
    br._log = logs.append
    br.eval_json = lambda expr, retries=3: {"disabled": False, "x": 10, "y": 10}
    switched: list[str] = []

    def _ensure_image(target_aspect=None):
        switched.append("image")
        if switch_works:
            page.mode = "image"
        return True

    br.ensure_ui_image_mode = _ensure_image
    return br, page, switched


def _pie(br: FlowBridge) -> type:
    # Resolve from the live module: other tests may re-import src.* (class identity changes).
    return sys.modules[type(br).__module__].PageInteractionError


def test_video_click_in_video_mode_never_switches_to_image():
    br, page, switched = _bridge("video")
    br.click_generate(timeout_s=1.0, expected_mode="video")
    assert switched == []
    assert page.clicks == ["video"]


def test_video_click_refuses_when_composer_in_image_mode():
    br, page, switched = _bridge("image")
    with pytest.raises(_pie(br)):
        br.click_generate(timeout_s=1.0, expected_mode="video")
    assert page.clicks == []
    assert switched == []


def test_image_click_auto_switches_from_video():
    br, page, switched = _bridge("video")
    br.click_generate(timeout_s=1.0)
    assert switched == ["image"]
    assert page.clicks == ["image"]


def test_image_click_refuses_if_switch_failed():
    br, page, _ = _bridge("video", switch_works=False)
    with pytest.raises(_pie(br)):
        br.click_generate(timeout_s=1.0, expected_mode="image")
    assert page.clicks == []


def test_invalid_expected_mode():
    br, _, _ = _bridge("image")
    with pytest.raises(ValueError):
        br.click_generate(timeout_s=1.0, expected_mode="audio")


def test_parse_capture_reports_image_rpcid():
    """The video flow relies on the reported rpcid to reject non-eb1hJf decoys."""
    from urllib.parse import quote

    tok = "0c" + "A" * 500
    args = [None, [[None, None, None, None, None, None, None, [None] * 10 + [[tok]]]]]
    f_req = json.dumps([[["ogiZ0b", json.dumps(args), None, "generic"]]])
    body = "f.req=" + quote(f_req) + "&at=" + quote("AT:123") + "&"
    token, at_param, _, rpcid = parse_video_app_capture(body)
    assert rpcid == "ogiZ0b"
    assert token == tok
    assert at_param == "AT:123"

"""Video-as-reference for the "Thành phần" sub-mode (RPC ``jIps6``, model ``abra_edit``).

Observed 2026-11-09 (``traces/submit_bodies/omni12_ingvideo_jIps6_args.json``): when an
*ingredient* chip holds a video instead of an image, Flow leaves the Omni family entirely.
The submit becomes ``jIps6`` with ``spec[0] = [null, <video_media_id>, 0, <frames>]`` and
the model key is ``abra_edit`` — the duration is not part of the key.

Getting the chip mounted is the hard part. Pasting does not work for video (the paste
handler only accepts images), so the only path is the composer's ingredient picker:

1. press the "Thêm thành phần vào ô nhập câu lệnh" button in the composer toolbar,
2. switch to the picker's ``videocam Video`` tab,
3. pick a clip from the project (or upload one through "Tải nội dung nghe nhìn lên",
   which opens a native file chooser),
4. press "Thêm vào câu lệnh".

The mounted chip is ``flow-video-ingredient-chip``; an image reference mounts
``flow-image-ingredient-chip`` instead, so the two are distinguishable in the DOM and the
caller can tell which RPC the app will fire.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..flow_bridge import FlowBridge

#: Toolbar button that opens the ingredient picker (Vietnamese UI).
_ADD_INGREDIENT_LABEL = "Thêm thành phần vào ô nhập câu lệnh"

_COUNT_VIDEO_CHIPS_JS = r"""
() => {
  const bar = document.querySelector('flow-ingredient-bar');
  if (!bar) return 0;
  return bar.querySelectorAll('flow-video-ingredient-chip').length;
}
"""

_OPEN_INGREDIENT_PICKER_JS = r"""
(label) => {
  const b = [...document.querySelectorAll('button')]
    .find(x => ((x.getAttribute('aria-label') || '') + ' ' + (x.innerText || '')).includes(label));
  if (!b) return null;
  b.click();
  const r = b.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
}
"""

_SELECT_VIDEO_TAB_JS = r"""
() => {
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[0];
  if (!pane) return false;
  // "videocam Video" — must not match "Giọng nói" (voice) or "Hình ảnh" (image).
  const tab = [...pane.querySelectorAll('button, [role="tab"]')].find(b => {
    const s = (b.innerText || '').replace(/\s+/g, ' ').trim();
    return s.includes('Video') && !s.includes('Giọng') && !s.includes('Hình ảnh');
  });
  if (!tab) return false;
  tab.click();
  return true;
}
"""

_PICK_VIDEO_ROW_JS = r"""
(want) => {
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[0];
  if (!pane) return null;
  const rows = [...pane.querySelectorAll('button')].filter(b => {
    const s = (b.innerText || '').replace(/\s+/g, ' ').trim();
    if (!s) return false;
    if (s.includes('Tải nội dung')) return false;
    if (s.includes('Thêm vào câu lệnh')) return false;
    if (s.includes('play_arrow') || s.includes('no_sound')) return false;
    return want ? s.includes(want) : true;
  });
  const hit = rows[0];
  if (!hit) return null;
  const r = hit.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
          text: (hit.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
}
"""

_ADD_TO_PROMPT_JS = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const btn = [...document.querySelectorAll('button')]
    .find(b => n(b.innerText) === 'Thêm vào câu lệnh' && (b.offsetWidth || b.offsetHeight));
  if (!btn) return null;
  const r = btn.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
}
"""


class VideoReferenceMixin:
    """Attach a project video as a "Thành phần" reference chip."""

    _log: Any  # supplied by the concrete bridge

    def video_reference_count(self, bridge: FlowBridge) -> int:
        """How many video reference chips are mounted (0 = no ``jIps6`` path)."""
        count = bridge.page.evaluate(_COUNT_VIDEO_CHIPS_JS)
        return int(count or 0)

    def has_video_reference(self, bridge: FlowBridge) -> bool:
        return self.video_reference_count(bridge) > 0

    def attach_video_reference(
        self,
        bridge: FlowBridge,
        *,
        title_match: Optional[str] = None,
        timeout_s: float = 40.0,
    ) -> bool:
        """Mount a clip from the project's video list as an ingredient chip.

        ``title_match`` picks a row by substring; the first clip is taken when omitted.
        Returns True when ``flow-video-ingredient-chip`` is present afterwards, which is
        the observable signal that the app will submit ``jIps6``.
        """
        page = bridge.page
        assert page is not None

        if self.has_video_reference(bridge):
            self._log("info", "Đã có chip video tham chiếu — bỏ qua bước gắn.")
            return True

        opened = page.evaluate(_OPEN_INGREDIENT_PICKER_JS, _ADD_INGREDIENT_LABEL)
        if not opened:
            self._log(
                "warn",
                "Không thấy nút 'Thêm thành phần vào ô nhập câu lệnh' — composer chưa ở "
                "sub-mode 'Thành phần'.",
            )
            return False
        page.wait_for_timeout(2000)

        if not page.evaluate(_SELECT_VIDEO_TAB_JS):
            page.keyboard.press("Escape")
            self._log("warn", "Picker không có tab 'Video' — không gắn được tham chiếu video.")
            return False
        page.wait_for_timeout(2000)

        deadline = time.time() + timeout_s
        row = None
        while time.time() < deadline:
            row = page.evaluate(_PICK_VIDEO_ROW_JS, title_match or "")
            if row:
                break
            page.wait_for_timeout(700)
        if not row:
            page.keyboard.press("Escape")
            self._log(
                "warn",
                "Tab 'Video' không có clip nào"
                + (f" khớp {title_match!r}." if title_match else "."),
            )
            return False

        page.mouse.click(row["x"], row["y"])
        page.wait_for_timeout(2000)

        add = page.evaluate(_ADD_TO_PROMPT_JS)
        if add:
            page.mouse.click(add["x"], add["y"])
            page.wait_for_timeout(2500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)

        mounted = self.has_video_reference(bridge)
        if mounted:
            self._log("info", f"Đã gắn clip tham chiếu ({row.get('text')!r}) — submit sẽ đi jIps6.")
        else:
            self._log(
                "warn",
                "Chip video không mount được (có thể clip cũ/lỗi — Flow hiện '.chip-container-disabled').",
            )
        return mounted

    def clear_video_reference(self, bridge: FlowBridge) -> bool:
        """Remove mounted video reference chips."""
        page = bridge.page
        assert page is not None
        removed = page.evaluate(
            r"""() => {
            const bar = document.querySelector('flow-ingredient-bar');
            if (!bar) return 0;
            let n = 0;
            for (const holder of [...bar.querySelectorAll('flow-video-ingredient-chip')]) {
              const btn = holder.querySelector('.hover-icon-overlay')
                       || holder.querySelector('button.chip-container');
              if (btn) { btn.click(); n += 1; }
            }
            return n;
          }"""
        )
        if removed:
            page.wait_for_timeout(1200)
        return bool(removed)


__all__ = ["VideoReferenceMixin"]

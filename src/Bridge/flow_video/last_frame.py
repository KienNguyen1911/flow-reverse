"""Frame slots of the video composer: the "Bắt đầu" and "Kết thúc" chips.

Observed 2026-11-09: "Khung hình" always renders *two* slots (``flow-ingredient-bar``
with two ``.frame-trigger`` children labeled "Bắt đầu" and "Kết thúc", plus a
"Hoán đổi khung hình đầu tiên và cuối cùng" swap button). The first slot is required;
filling the second one switches the submit RPC from ``eb1hJf`` to ``nprQif`` and narrows
the duration window to 3..10s.

Filling a slot has two paths and they are not interchangeable:

* **Paste** (``ClipboardEvent`` → ``maseQ``) uploads a local file, but the app decides
  which slot receives the chip.
* **Picker** ("Chọn một hình ảnh khung") reuses a project asset. It is the only reliable
  way to target the second slot, so that is what :meth:`fill_last_frame_from_asset` does.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from ..flow_bridge import FlowBridge, PageInteractionError

SLOT_LABEL_FIRST = "Bắt đầu"
SLOT_LABEL_LAST = "Kết thúc"

_SLOTS_JS = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const bar = document.querySelector('flow-ingredient-bar');
  if (!bar) return [];
  return [...bar.querySelectorAll('.frame-trigger')].map((t, i) => {
    // A filled slot holds a flow-image-ingredient-chip; an empty one holds button.empty-chip.
    // Presence of the chip is what decides `filled` — the <img> inside it mounts a beat
    // later (and is replaced once the upload swaps to a signed CDN URL).
    const chip = t.querySelector('flow-image-ingredient-chip');
    const empty = t.querySelector('button.empty-chip');
    const img = t.querySelector('img');
    const src = img ? String(img.src || img.currentSrc || '') : '';
    const mediaId = (src.match(/image\/([0-9a-f-]{36})/) || [])[1] || null;
    return {
      index: i,
      label: empty ? n(empty.innerText) : '',
      filled: !!chip,
      mediaId: mediaId ? mediaId.toLowerCase() : null,
    };
  });
}
"""

_SLOT_BOX_JS = r"""
(label) => {
  const bar = document.querySelector('flow-ingredient-bar');
  if (!bar) return null;
  const triggers = [...bar.querySelectorAll('.frame-trigger')];
  const hit = triggers.find(t => {
    const empty = t.querySelector('button.empty-chip');
    return ((empty ? empty.innerText : '') || '').includes(label);
  });
  if (!hit) return null;
  const r = hit.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
}
"""

_PICKER_ROW_JS = r"""
(want) => {
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[0];
  if (!pane) return null;
  const rows = [...pane.querySelectorAll('button.asset-item')];
  const hit = want ? rows.find(r => (r.innerText || '').includes(want)) : rows[0];
  if (!hit) return null;
  const r = hit.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
          text: (hit.innerText || '').trim().slice(0, 40)};
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


class LastFrameMixin:
    """Read and fill the composer's ``Kết thúc`` (last frame) slot."""

    _log: Any  # supplied by the concrete bridge

    def frame_slots(self, bridge: FlowBridge) -> list[dict]:
        """Describe every frame slot: index, label, filled, media id."""
        slots = bridge.page.evaluate(_SLOTS_JS)
        return slots if isinstance(slots, list) else []

    def last_frame_media_id(self, bridge: FlowBridge) -> Optional[str]:
        """Media id currently in the ``Kết thúc`` slot, or None."""
        slots = self.frame_slots(bridge)
        if len(slots) < 2:
            return None
        return slots[1].get("mediaId") if slots[1].get("filled") else None

    def clear_last_frame(self, bridge: FlowBridge) -> bool:
        """Remove the ``Kết thúc`` chip so the submit falls back to single-frame."""
        slots = self.frame_slots(bridge)
        if len(slots) < 2 or not slots[1].get("filled"):
            return False
        clicked = bridge.page.evaluate(
            r"""() => {
            const bar = document.querySelector('flow-ingredient-bar');
            if (!bar) return false;
            const triggers = [...bar.querySelectorAll('.frame-trigger')];
            const last = triggers[triggers.length - 1];
            if (!last) return false;
            const btn = last.querySelector('.hover-icon-overlay')
                     || last.querySelector('button.chip-container');
            if (!btn) return false;
            btn.click();
            return true;
          }"""
        )
        if clicked:
            bridge.page.wait_for_timeout(1200)
        return bool(clicked)

    def fill_last_frame_from_asset(
        self,
        bridge: FlowBridge,
        *,
        asset_name: Optional[str] = None,
        timeout_s: float = 25.0,
    ) -> Optional[str]:
        """Pick an existing project asset into the ``Kết thúc`` slot; returns its media id.

        ``asset_name`` matches the picker row by substring; the first row is taken when it
        is omitted. Raises :class:`PageInteractionError` when the slot or the picker never
        appears, because silently continuing would submit a single-frame video while the
        caller believes a last frame is attached.
        """
        page = bridge.page
        assert page is not None

        box = page.evaluate(_SLOT_BOX_JS, SLOT_LABEL_LAST)
        if not box:
            raise PageInteractionError(
                f"Không thấy ô '{SLOT_LABEL_LAST}' trong composition bar — composer chưa ở Khung hình."
            )
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(1600)

        deadline = time.time() + timeout_s
        row = None
        while time.time() < deadline:
            row = page.evaluate(_PICKER_ROW_JS, asset_name or "")
            if row:
                break
            page.wait_for_timeout(600)
        if not row:
            raise PageInteractionError(
                "Picker 'Chọn một hình ảnh khung' không hiện asset nào"
                + (f" khớp {asset_name!r}." if asset_name else ".")
            )

        page.mouse.click(row["x"], row["y"])
        page.wait_for_timeout(2500)

        # The picker opens the asset's detail pane; the chip only lands after "Thêm vào câu lệnh".
        add = page.evaluate(_ADD_TO_PROMPT_JS)
        if add:
            page.mouse.click(add["x"], add["y"])
            page.wait_for_timeout(2500)

        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        media_id = self.last_frame_media_id(bridge)
        if not media_id:
            raise PageInteractionError(
                "Đã chọn asset nhưng ô 'Kết thúc' vẫn trống — chip không mount được."
            )
        self._log("info", f"Đã gắn khung 'Kết thúc' từ asset ({row.get('text')!r}) -> media_id={media_id}")
        return media_id

    def fill_last_frame_from_file(
        self,
        bridge: FlowBridge,
        frame_path: Path | str,
        *,
        timeout_s: float = 45.0,
    ) -> Optional[str]:
        """Upload a local file into the ``Kết thúc`` slot (best effort, verified).

        The paste path uploads through ``maseQ`` but the app decides which slot receives
        the chip, so this verifies the result and returns None when the file did not land
        in the last slot.
        """
        path = Path(frame_path)
        if not path.is_file():
            raise FileNotFoundError(f"Không thấy file khung 'Kết thúc': {path}")

        box = bridge.page.evaluate(_SLOT_BOX_JS, SLOT_LABEL_LAST)
        if box:
            bridge.page.mouse.click(box["x"], box["y"])
            bridge.page.wait_for_timeout(900)
            bridge.page.keyboard.press("Escape")
            bridge.page.wait_for_timeout(400)

        self.upload_starting_frame_via_paste(bridge, path, timeout_s=timeout_s)  # type: ignore[attr-defined]
        bridge.page.wait_for_timeout(1200)
        media_id = self.last_frame_media_id(bridge)
        if not media_id:
            self._log(
                "warn",
                "Upload khung 'Kết thúc' không vào đúng ô (app gắn vào ô khác) — "
                "dùng asset picker hoặc submit 1 khung.",
            )
        else:
            self._log("info", f"Đã gắn khung 'Kết thúc' từ file {path.name} -> media_id={media_id}")
        return media_id


__all__ = ["LastFrameMixin", "SLOT_LABEL_FIRST", "SLOT_LABEL_LAST"]

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

#: Press the picker's "Tải nội dung nghe nhìn lên" button, which opens a NATIVE file chooser
#: (no ``input[type=file]`` exists in the DOM — the page hands the click to the OS dialog).
_PICKER_UPLOAD_JS = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[0];
  if (!pane) return false;
  const btn = [...pane.querySelectorAll('button')]
    .find(b => n(b.innerText).includes('Tải nội dung nghe nhìn lên')
            || n(b.innerText).toLowerCase().includes('upload media'));
  if (!btn) return false;
  btn.click();
  return true;
}
"""

#: True while the picker still shows an in-flight upload ("Đang tải lên …").
_PICKER_UPLOADING_JS = r"""
() => {
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  if (!panes.length) return false;
  const t = panes[0].innerText || '';
  return t.includes('Đang tải lên') || /uploading/i.test(t);
}
"""

#: Locate the just-uploaded asset row by filename inside the open picker.
_PICKER_FILE_ROW_JS = r"""
(want) => {
  const panes = [...document.querySelectorAll('.cdk-overlay-pane')]
    .filter(p => p.offsetWidth || p.offsetHeight);
  const pane = panes[0];
  if (!pane) return null;
  const rows = [...pane.querySelectorAll('button.asset-item, [role="option"]')];
  const hit = rows.find(r => {
    const t = (r.innerText || '') + ' ' + (r.getAttribute('aria-label') || '');
    return want ? t.includes(want) : true;
  });
  if (!hit) return null;
  const r = hit.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
          text: (hit.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
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
        timeout_s: float = 60.0,
    ) -> Optional[str]:
        """Put a local file into the ``Kết thúc`` slot; returns its media id.

        Pasting a file does **not** work here: the synthetic ``ClipboardEvent`` goes through
        ``maseQ`` but the app always drops the chip into the first (``Bắt đầu``) slot, which
        would overwrite the starting frame. The only reliable path is the slot's own picker:

        1. click the empty chip labelled ``Kết thúc`` to open "Chọn một hình ảnh khung",
        2. press "Tải nội dung nghe nhìn lên" and push the file through the native file
           chooser (the dialog is an OS window — there is no ``input[type=file]`` in the DOM),
        3. wait for the upload to finish, click the new asset row,
        4. click "Thêm vào câu lệnh" to mount the chip.

        Returns ``None`` when the chip never lands, so the caller can abort instead of
        silently submitting a single-frame video.
        """
        path = Path(frame_path)
        if not path.is_file():
            raise FileNotFoundError(f"Không thấy file khung 'Kết thúc': {path}")
        page = bridge.page
        assert page is not None

        if self.last_frame_media_id(bridge):
            self._log("info", "Ô 'Kết thúc' đã có ảnh — bỏ qua bước gắn.")
            return self.last_frame_media_id(bridge)

        box = page.evaluate(_SLOT_BOX_JS, SLOT_LABEL_LAST)
        if not box:
            self._log("warn", f"Không thấy ô '{SLOT_LABEL_LAST}' để gắn khung cuối.")
            return None
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(1500)

        # Step 2: the picker's upload button hands the click to a native OS chooser, so the
        # click must happen INSIDE expect_file_chooser or the dialog never gets captured.
        try:
            with page.expect_file_chooser(timeout=timeout_s * 1000) as fc:
                clicked_upload = page.evaluate(_PICKER_UPLOAD_JS)
            if not clicked_upload:
                page.keyboard.press("Escape")
                self._log("warn", "Picker không có nút 'Tải nội dung nghe nhìn lên'.")
                return None
            fc.value.set_files(str(path))
        except Exception as exc:  # noqa: BLE001 - chooser is best-effort, verified below
            self._log("warn", f"Không mở được hộp chọn file: {exc}")
            page.keyboard.press("Escape")
            return None

        # Step 3: the row appears as "Đang tải lên <name>" and turns into "<name>" when the
        # upload finishes. Checking only for absence is wrong — right after set_files the
        # indicator has not rendered yet, so the loop would exit on the very first poll and
        # the subsequent click would hit a row that is still uploading (which does nothing).
        deadline = time.time() + timeout_s
        saw_uploading = False
        while time.time() < deadline:
            uploading = page.evaluate(_PICKER_UPLOADING_JS)
            if uploading:
                saw_uploading = True
            elif saw_uploading:
                break
            page.wait_for_timeout(700)
        if not saw_uploading:
            # Never saw the indicator: either the file uploaded instantly or the picker is
            # showing a stale asset list. Give the list a moment, then match by name.
            page.wait_for_timeout(1500)

        row = page.evaluate(_PICKER_FILE_ROW_JS, path.name)
        if row:
            page.mouse.click(row["x"], row["y"])
            page.wait_for_timeout(1800)
        else:
            self._log("warn", f"Không thấy asset {path.name!r} trong picker sau khi tải lên.")

        # Step 4: "Thêm vào câu lệnh" mounts the chip.
        add = page.evaluate(_ADD_TO_PROMPT_JS)
        if add:
            page.mouse.click(add["x"], add["y"])
            page.wait_for_timeout(2000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        media_id = self.last_frame_media_id(bridge)
        if media_id:
            self._log("info", f"Đã gắn khung 'Kết thúc' từ file {path.name} -> media_id={media_id}")
        else:
            self._log(
                "warn",
                "Upload khung 'Kết thúc' không vào đúng ô — dùng asset picker hoặc submit 1 khung.",
            )
        return media_id


__all__ = ["LastFrameMixin", "SLOT_LABEL_FIRST", "SLOT_LABEL_LAST"]

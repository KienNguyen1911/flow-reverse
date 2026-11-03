"""Video RPC side of :class:`FlowVideoBridge`: decoy hook/capture, `jwpduf` polling, `as29s`, 1080p upsample, download."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from ..flow_bridge import (
    BridgeError,
    CaptureTimeoutError,
    FlowBridge,
    build_rpc_url_from_template,
    extract_app_reqid,
    parse_batchexecute_text,
)
from .constants import (
    PROJECT_ITEMS_RPC,
    VIDEO_MEDIA_URL_RPC,
    VIDEO_POLL_RPC,
    VIDEO_SUBMIT_RPC,
    VIDEO_UPSAMPLE_RPC,
)
from .hook_js import VIDEO_HOOK_JS
from .parsing import (
    extract_media_records,
    extract_signed_video_url,
    parse_jwpduf_status,
    parse_video_app_capture,
)
from .payload import (
    build_as29s_args,
    build_jwpduf_args,
    build_video_upsample_1080p_args,
    encode_video_batchexecute_form,
)


class VideoRpcMixin:
    """Hook install/capture plus the 0-credit status/URL RPCs and the final MP4 download."""

    def install_video_hook(self, bridge: FlowBridge) -> None:
        """Install the idempotent VIDEO_HOOK_JS (`eb1hJf` block+capture + `maseQ` upload spy)."""
        res = bridge._eval(VIDEO_HOOK_JS)
        if not (isinstance(res, dict) and res.get("installed")):
            raise BridgeError(f"VIDEO_HOOK_JS install failed: {res!r}")
        self._log("info", "Đã gắn VIDEO_HOOK_JS (chặn eb1hJf mồi 0-credit + lắng nghe maseQ)")

    def disarm_video_hook(self, bridge: FlowBridge) -> None:
        """Disarm the eb1hJf request blocker."""
        try:
            bridge._eval("window.__blockVideoGen = false; true", retries=2)
        except Exception:
            pass

    def wait_video_capture(self, bridge: FlowBridge, timeout_s: float = 25.0, min_len: int = 100) -> dict[str, Any]:
        """Wait for the blocked app eb1hJf decoy capture (`window.__videoHook.cap`)."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            info = bridge.eval_json(
                """(() => {
                    const c = window.__videoHook && window.__videoHook.cap;
                    return (c && c.bodyReady) ? {url: c.url, ts: c.ts, via: c.via, len: (c.body || '').length} : null;
                })()"""
            )
            if info and int(info.get("len") or 0) > min_len:
                body = bridge._eval("(window.__videoHook && window.__videoHook.cap && window.__videoHook.cap.body) || ''")
                if body and len(body) > min_len:
                    return {
                        "url": info.get("url") or "",
                        "body": body,
                        "ts_ms": int(info.get("ts") or 0),
                        "via": info.get("via") or "",
                    }
            time.sleep(0.12)
        raise CaptureTimeoutError("Không bắt được request eb1hJf của app trong ~25s (hook timeout).")

    def poll_video_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        project_id: Optional[str] = None,
        timeout_s: float = 300.0,
        poll_interval_s: float = 4.0,
    ) -> dict[str, Any]:
        """Poll `jwpduf` (0 credit) for `video_media_id` until succeeded or failed."""
        ctx = bridge.session_ctx(timeout_s=10.0)
        t0 = time.time()
        deadline = t0 + timeout_s
        poll_seq = 0

        self._log("step", f"Poll trạng thái video qua RPC jwpduf (media_id={video_media_id[:8]}..., tối đa {timeout_s:.0f}s)...")
        while time.time() < deadline:
            time.sleep(poll_interval_s)
            poll_seq += 1
            elapsed = int(time.time() - t0)

            reqid = ctx.reqid + 100000 + (poll_seq * 1000)
            url = build_rpc_url_from_template(ctx.url_template, VIDEO_POLL_RPC, reqid)
            body = encode_video_batchexecute_form(VIDEO_POLL_RPC, build_jwpduf_args(video_media_id), ctx.at)

            try:
                fr = bridge.fire(url, body, timeout_s=25.0, poll_s=0.5)
                parsed = parse_batchexecute_text(fr.text)
            except Exception as e:
                self._log("warn", f"jwpduf poll #{poll_seq} lỗi mạng tạm thời ({e}), thử lại...")
                continue

            if not parsed.get("ok"):
                self._log("warn", f"jwpduf poll #{poll_seq} trả về not-ok: {parsed.get('reason')}")
                continue

            st = parse_jwpduf_status(parsed.get("data"), video_media_id=video_media_id)
            if st["state"] == "succeeded":
                self._log(
                    "info",
                    f"jwpduf báo video HOÀN TẤT sau {elapsed}s! (size={st.get('file_bytes') or '?'} bytes, seed={st.get('seed_echo')})",
                )
                return st

            if st["state"] == "failed":
                err_code = st.get("error_code") or "UNKNOWN_VIDEO_ERROR"
                cats = ", ".join(st.get("error_categories") or [])
                self._log(
                    "warn",
                    f"jwpduf phát hiện lỗi tức thì sau {elapsed}s: {err_code} (categories={cats})",
                )
                return st

            if poll_seq % 3 == 0:
                self._log("info", f"Đang render video trên server (jwpduf state=pending, đã qua {elapsed}s)...")

        raise BridgeError(f"Hết thời gian chờ render video qua jwpduf ({timeout_s:.0f}s) cho media_id={video_media_id}.")

    def fetch_signed_video_url_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        project_id: Optional[str] = None,
    ) -> str:
        """Call `as29s` (0 credit) to mint a 6-hour signed CDN URL for `video_media_id`."""
        ctx = bridge.session_ctx(timeout_s=10.0)
        url = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 250000)
        body = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(video_media_id), ctx.at)

        self._log("step", f"Gọi RPC as29s lấy signed CDN URL 6h cho video {video_media_id[:8]}...")
        fr = bridge.fire(url, body, timeout_s=25.0, poll_s=0.5)
        parsed = parse_batchexecute_text(fr.text)
        if parsed.get("ok"):
            signed = extract_signed_video_url(parsed.get("data"))
            if signed:
                self._log("info", f"Đã lấy signed URL từ as29s: {signed[:85]}...")
                return signed

        # Fallback: query Zzl0ze project items if as29s did not contain the URL
        if project_id:
            url_z = build_rpc_url_from_template(ctx.url_template, PROJECT_ITEMS_RPC, ctx.reqid + 260000)
            body_z = encode_video_batchexecute_form(
                PROJECT_ITEMS_RPC, [f"projects/{project_id.strip().lower()}", None, None, None, [1]], ctx.at
            )
            fr_z = bridge.fire(url_z, body_z, timeout_s=25.0, poll_s=0.5)
            parsed_z = parse_batchexecute_text(fr_z.text)
            if parsed_z.get("ok"):
                for rec in extract_media_records(parsed_z.get("data"), project_id=project_id):
                    if str(rec[0]).lower() == video_media_id.strip().lower():
                        signed_z = extract_signed_video_url(rec)
                        if signed_z:
                            return signed_z

        raise BridgeError(f"Không lấy được signed video URL qua as29s/Zzl0ze cho {video_media_id}.")

    def upsample_and_fetch_1080p_url_rpc(
        self,
        bridge: FlowBridge,
        video_media_id: str,
        item_id: Optional[str],
        project_id: str,
        aspect_ratio: str = "9:16",
        timeout_s: float = 120.0,
    ) -> Optional[str]:
        """Upsample a succeeded 720p video to 1080p via RPC `p0UkFb` (`veo_3_1_upsampler_1080p`) and return its 6h signed URL.

        Workflow (`docs/api_specs/flow_create_video.md` §2.5):
        1. Checks if `<video_media_id>_upsampled` is already available via `as29s`.
        2. Otherwise, resolves `item_id` (if missing) via `as29s([video_media_id])`, borrows a fresh
           0-credit reCAPTCHA token via `VIDEO_HOOK_JS` + `click_generate`, and fires `p0UkFb`.
        3. Polls `jwpduf` for `<video_media_id>_upsampled` until `rec[5][8] == [3]`.
        4. Calls `as29s([f"{video_media_id}_upsampled"])` to mint the 6h signed 1080p MP4 URL.
        """
        vid_norm = video_media_id.strip().lower()
        upsampled_id = vid_norm if vid_norm.endswith("_upsampled") else f"{vid_norm}_upsampled"
        ctx = bridge.session_ctx(timeout_s=10.0)

        # 1. Fast check: is `<video_media_id>_upsampled` already ready?
        try:
            url_check = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 270000)
            body_check = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(upsampled_id), ctx.at)
            fr_check = bridge.fire(url_check, body_check, timeout_s=20.0, poll_s=0.4)
            p_check = parse_batchexecute_text(fr_check.text)
            if p_check.get("ok"):
                st_check = parse_jwpduf_status(p_check.get("data"), video_media_id=upsampled_id)
                if st_check["state"] == "succeeded":
                    existing_url = extract_signed_video_url(p_check.get("data"))
                    if existing_url:
                        self._log("info", f"Bản 1080p ({upsampled_id[:12]}...) đã có sẵn! ({st_check.get('file_bytes') or '?'} bytes)")
                        return existing_url
        except Exception:
            pass

        # 2. Ensure we have item_id for p0UkFb
        resolved_item_id = item_id
        if not resolved_item_id:
            try:
                url_base = build_rpc_url_from_template(ctx.url_template, VIDEO_MEDIA_URL_RPC, ctx.reqid + 271000)
                body_base = encode_video_batchexecute_form(VIDEO_MEDIA_URL_RPC, build_as29s_args(vid_norm), ctx.at)
                fr_base = bridge.fire(url_base, body_base, timeout_s=20.0, poll_s=0.4)
                p_base = parse_batchexecute_text(fr_base.text)
                if p_base.get("ok"):
                    recs = extract_media_records(p_base.get("data"), project_id=project_id)
                    if recs and len(recs[0]) > 2 and recs[0][2]:
                        resolved_item_id = str(recs[0][2]).lower()
            except Exception:
                pass

        if not resolved_item_id:
            self._log("warn", f"Không tìm thấy item_id cho {vid_norm}, bỏ qua nâng cấp 1080p.")
            return None

        # 3. Borrow a 0-credit reCAPTCHA token via decoy click_generate and fire p0UkFb
        try:
            self._log("step", f"Nâng cấp video {vid_norm[:8]}... lên 1080p qua RPC {VIDEO_UPSAMPLE_RPC} (veo_3_1_upsampler_1080p)...")
            # Reload cleanly if the page composer state was dirtied by the earlier blocked eb1hJf
            if bridge._eval("Boolean(window.__videoHook && window.__videoHook.blocked)"):
                bridge.reload(settle_s=4.0)
            self._ensure_recaptcha_ready(bridge, project_id)
            self.install_video_hook(bridge)
            bridge._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
            cur_prompt = (
                bridge.prompt_value()
                if hasattr(bridge, "prompt_value")
                else str(
                    bridge._eval(
                        "(() => { try { const ed = document.querySelector('div.ProseMirror'); return ed ? String(ed.innerText || '').trim() : ''; } catch (e) { return ''; } })()"
                    )
                    or ""
                )
            )
            if not cur_prompt.strip():
                bridge.type_prompt("A fashion model smiling naturally, 8 seconds.")
                time.sleep(0.3)
            self._ensure_ui_video_frames_mode(bridge.page, aspect_ratio)
            bridge.click_generate(timeout_s=12.0, expected_mode="video")
            cap = self.wait_video_capture(bridge, timeout_s=20.0)
            self.disarm_video_hook(bridge)

            app_reqid = extract_app_reqid(cap["url"])
            tok, at_param, _, up_cap_rpcid = parse_video_app_capture(cap["body"])
            if up_cap_rpcid != VIDEO_SUBMIT_RPC:
                raise BridgeError(
                    f"Request mồi là {up_cap_rpcid} (không phải {VIDEO_SUBMIT_RPC}) — token reCAPTCHA sai action, hủy p0UkFb."
                )
            up_args = build_video_upsample_1080p_args(
                project_id=project_id,
                video_media_id=vid_norm,
                item_id=resolved_item_id,
                recaptcha_token=tok,
                aspect_ratio=aspect_ratio,
            )
            up_reqid = (app_reqid + 150000) if app_reqid is not None else (ctx.reqid + 275000)
            up_url = build_rpc_url_from_template(cap["url"], VIDEO_UPSAMPLE_RPC, up_reqid)
            up_body = encode_video_batchexecute_form(VIDEO_UPSAMPLE_RPC, up_args, at_param)

            fr_up = bridge.fire(up_url, up_body, timeout_s=45.0, poll_s=0.6)
            p_up = parse_batchexecute_text(fr_up.text)
            if not p_up.get("ok"):
                self._log("warn", f"RPC {VIDEO_UPSAMPLE_RPC} trả về not-ok ({p_up.get('reason')}), dùng bản 720p.")
                return None

            self._log("info", f"Đã kích hoạt nâng cấp 1080p ({upsampled_id})! Đang poll jwpduf...")
            st_up = self.poll_video_rpc(
                bridge,
                video_media_id=upsampled_id,
                project_id=project_id,
                timeout_s=timeout_s,
                poll_interval_s=3.5,
            )
            if st_up["state"] == "succeeded":
                return st_up.get("signed_url") or self.fetch_signed_video_url_rpc(
                    bridge, video_media_id=upsampled_id, project_id=project_id
                )
        except Exception as e:
            self.disarm_video_hook(bridge)
            self._log("warn", f"Nâng cấp 1080p gặp lỗi ({e}), tự động fallback về bản 720p gốc.")

        return None

    def download_video_verified(
        self,
        bridge: FlowBridge,
        video_url: str,
        dest_path: Path,
    ) -> Path:
        """Download video from signed CDN URL (or authenticated FIFE URL) with ftyp magic-byte verification."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try cookie-free signed CDN download via FlowBridge.download (validates ftyp magic bytes + backoff)
        if "flow-content.google/" in video_url or "storage.googleapis.com/" in video_url:
            ok, nbytes = bridge.download(video_url, dest_path)
            if ok and nbytes > 10000:
                self._log("info", f"Đã tải video gốc qua signed CDN ({nbytes / 1024:.1f} KB) -> {dest_path.name}")
                return dest_path

        # 2. Authenticated browser context download (required for lh3/flow.google.com/asb/...=mm,22,15 URLs)
        if bridge.context is not None:
            for attempt in range(3):
                try:
                    resp = bridge.context.request.get(video_url, timeout=60000)
                    data = resp.body()
                    is_mp4 = b"ftyp" in data[:32] or data[:4] == b"\x1a\x45\xdf\xa3"
                    if resp.status == 200 and is_mp4 and len(data) > 10000:
                        dest_path.write_bytes(data)
                        self._log("info", f"Đã tải video xác thực ({len(data) / 1024:.1f} KB) -> {dest_path.name}")
                        return dest_path
                except Exception as e:
                    self._log("warn", f"Tải video qua context.request lần {attempt + 1} lỗi: {e}")
                time.sleep(2.0 * (attempt + 1))

        # 3. Final fallback to FlowBridge.download
        ok, nbytes = bridge.download(video_url, dest_path)
        if ok and nbytes > 10000:
            return dest_path

        raise BridgeError(f"Tải file video thất bại hoặc không đúng định dạng MP4 từ URL: {video_url[:90]}")

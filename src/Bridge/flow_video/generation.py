"""End-to-end video generation flows for :class:`FlowVideoBridge` (image->video and text->video)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from ..flow_bridge import (
    BridgeError,
    CaptureTimeoutError,
    FlowBridge,
    TokenParseError,
    build_rpc_url_from_template,
    describe_reject,
    extract_app_reqid,
    jitter,
    new_seed,
    parse_batchexecute_text,
)
from .constants import (
    OMNI12_MAX_DURATION_S_WITH_LAST_FRAME,
    VIDEO_EDIT_RPC,
    VIDEO_LAST_FRAME_SUBMIT_RPC,
    VIDEO_SUBMIT_RPC,
    VIDEO_SUBMIT_RPCS,
)
from .media_tools import strip_video_audio
from .parsing import (
    extract_last_frame_from_args,
    extract_reference_media_ids,
    extract_reference_video_from_args,
    extract_starting_frame_from_eb1hjf_args,
    extract_video_submit_media_id,
    parse_video_app_capture,
)
from .models import (
    SHAPE_IMAGE_REFS,
    SHAPE_TEXT,
    SHAPE_VIDEO_REF,
    submit_rpc_for,
)
from .payload import (
    build_text_video_args,
    build_video_args,
    build_video_edit_args,
    encode_video_batchexecute_form,
)
from .prompt import sanitize_video_prompt


class VideoGenerationMixin:
    """Orchestrates composer driving, decoy capture, deterministic submit, polling and download."""

    def generate_video_flow(
        self,
        frame_path: Path | str,
        prompt_text: str,
        dest_path: Path | str,
        duration_s: int = 8,
        timeout_s: float = 300.0,
        project_id: Optional[str] = None,
        aspect_ratio: str = "9:16",
        aggressive_sanitize: bool = False,
        seed: Optional[int] = None,
        resolution: str = "1080p",
        *,
        last_frame_path: Path | str | None = None,
        model_key: Optional[str] = None,
        model_label: Optional[str] = None,
        count: int = 1,
        offer_resolution: bool = True,
        offer_duration: bool = True,
        capture_resolution: str = "720p",
    ) -> Path:
        """Protocol-level ("Bridge Mode") Video generation on Google Flow.

        Workflow:
        1. Connects to CloakBrowser over CDP (`FlowBridge`) and installs `VIDEO_HOOK_JS`.
        2. Uploads the starting frame via `maseQ` (synthetic paste on `div.ProseMirror`).
        3. Optionally fills the composer's "Kết thúc" slot — with ``last_frame_path`` (a
           local file) or, when that file is already a project asset, by name. Filling it
           switches the submit RPC to `nprQif` and narrows the duration window to 3..10s.
        4. Blocks the app's decoy submit request (0 credit) to borrow the freshly minted
           reCAPTCHA Enterprise token and the frame ids the composer actually used.
        5. Fires our deterministic payload with `x-harness-ours: 1`, then polls `jwpduf`
           every 4s. Policy rejections fail fast (~8s) and retry once with a fresh seed.
        6. Mints a 6-hour signed CDN URL via `as29s` (0 credit) and downloads the MP4.
        """
        frame_p = Path(frame_path).resolve()
        dest_p = Path(dest_path).resolve()
        dest_p.parent.mkdir(parents=True, exist_ok=True)

        if not frame_p.is_file():
            raise FileNotFoundError(f"Không tìm thấy file frame: {frame_p}")

        target_aspect = "9:16" if "9:16" in str(aspect_ratio) else "16:9"

        with FlowBridge(self.cdp_url, log=lambda m: self._log("info", m)) as br:
            page = br.page
            assert page is not None

            if project_id and f"/project/{project_id}" not in page.url:
                self._log("step", f"Điều hướng SPA tới dự án Flow: {project_id}")
                br.nav_project(project_id)

            # Extract active project_id from URL if not explicitly provided
            active_pid = project_id
            if not active_pid and "/project/" in page.url:
                active_pid = page.url.split("/project/")[1].split("/")[0].split("?")[0]
            if not active_pid:
                raise BridgeError("Không xác định được project_id trên trang Flow hiện tại.")
            active_pid = active_pid.strip().lower()

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self._cleanup_failed_tiles_in_dom(page)

            # Use the exact original starting frame untouched to preserve 100% character consistency
            max_protocol_attempts = 2
            current_frame_p = frame_p
            wants_last_frame = last_frame_path is not None

            for attempt in range(max_protocol_attempts):
                is_retry = attempt > 0
                use_aggressive = aggressive_sanitize or is_retry
                clean_prompt = sanitize_video_prompt(prompt_text, aggressive=use_aggressive)
                seed_to_use = new_seed() if (seed is None or is_retry) else int(seed)

                self._log(
                    "step",
                    f"[Bridge Mode {attempt + 1}/{max_protocol_attempts}] Tạo Video ({duration_s}s, {target_aspect}, seed={seed_to_use}"
                    f"{', có khung Kết thúc' if wants_last_frame else ''}) từ {current_frame_p.name}",
                )
                self._log("info", f"Prompt ({len(clean_prompt)} ký tự): '{clean_prompt[:85]}...'")

                # 1. Ensure reCAPTCHA Enterprise & clean page state, install VIDEO_HOOK_JS and drive
                #    the composer to Video → sub-mode → aspect → model → resolution → duration → count
                self._ensure_recaptcha_ready(br, active_pid)
                self.install_video_hook(br)
                self._ensure_ui_video_mode(
                    page,
                    sub_mode="frames",
                    target_aspect=target_aspect,
                    model_label=model_label,
                    duration_s=duration_s,
                    resolution=capture_resolution,
                    count=count,
                    offer_resolution=offer_resolution,
                    offer_duration=offer_duration,
                )

                # 2. Upload & attach starting frame via synthetic paste (`maseQ`) or UI fallback
                uploaded_media_id = self.upload_starting_frame_via_paste(
                    br, current_frame_p, project_id=active_pid, timeout_s=35.0
                )
                if not page.query_selector("flow-image-ingredient-chip"):
                    self._attach_starting_frame_ui_fallback(page, current_frame_p)

                if not page.query_selector("flow-image-ingredient-chip") and not uploaded_media_id:
                    raise BridgeError(
                        "Không thể gắn Starting Frame vào ô 'Bắt đầu' (cả qua maseQ paste lẫn UI fallback)."
                    )

                # 3. Fill the optional "Kết thúc" slot. A failed attach is an error when the
                #    caller asked for it: submitting anyway would silently drop the last frame.
                if wants_last_frame:
                    attached_last = self.fill_last_frame_from_file(br, last_frame_path, timeout_s=45.0)
                    if not attached_last:
                        raise BridgeError(
                            "Không gắn được khung 'Kết thúc' vào composer (Flow chỉ nhận asset có sẵn "
                            "hoặc upload vào đúng ô) — hủy submit thay vì tạo video 1 khung."
                        )
                    # Attaching the last frame lowers the slider's ceiling, so a longer
                    # duration must be re-applied (and will clamp to the lower ceiling).
                    if duration_s > OMNI12_MAX_DURATION_S_WITH_LAST_FRAME:
                        self._apply_duration(page, duration_s)

                # 4. Arm the submit blocker (0 credit on decoy), type prompt, click Generate
                br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
                br.type_prompt(clean_prompt)
                time.sleep(jitter(0.4, 0.1, 0.2))
                br.click_generate(timeout_s=15.0, expected_mode="video")

                try:
                    cap = self.wait_video_capture(br, timeout_s=25.0)
                    self.disarm_video_hook(br)
                    app_reqid = extract_app_reqid(cap["url"])
                    token, at_param, app_args, cap_rpcid = parse_video_app_capture(cap["body"])
                    expected_rpc = (
                        VIDEO_LAST_FRAME_SUBMIT_RPC if wants_last_frame else VIDEO_SUBMIT_RPC
                    )
                    if cap_rpcid != expected_rpc:
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            f"Request mồi là {cap_rpcid} thay vì {expected_rpc} "
                            f"({'có' if wants_last_frame else 'không có'} khung Kết thúc) — "
                            "composer không ở đúng trạng thái, hủy submit để tránh lỗi UNUSUAL_ACTIVITY."
                        )
                except (TokenParseError, CaptureTimeoutError) as cap_err:
                    self.disarm_video_hook(br)
                    if attempt + 1 < max_protocol_attempts:
                        self._log(
                            "warn",
                            f"Phiên reCAPTCHA trên trang chưa sẵn sàng ({cap_err}). "
                            f"Đang tự động reload trang dự án và thử lại lần {attempt + 2}...",
                        )
                        br.reload(settle_s=5.0)
                        continue
                    br.reload(settle_s=4.0)
                    raise

                cap_sf_id, cap_crop_box = extract_starting_frame_from_eb1hjf_args(app_args)
                cap_last_id, cap_last_crop = extract_last_frame_from_args(app_args)

                starting_frame_media_id = cap_sf_id or uploaded_media_id
                if not starting_frame_media_id:
                    raise BridgeError(
                        f"Request mồi ({cap_rpcid}) không chứa starting_frame_media_id — kiểm tra chế độ Khung hình."
                    )

                # 5. Build our deterministic submit payload
                u1 = str(uuid.uuid4()).upper()
                u2 = str(uuid.uuid4()).upper()
                gen_id = str(uuid.uuid4()).upper()

                our_args = build_video_args(
                    project_id=active_pid,
                    prompt=clean_prompt,
                    recaptcha_token=token,
                    starting_frame_media_id=starting_frame_media_id,
                    aspect_ratio=target_aspect,
                    seed=seed_to_use,
                    model_key=model_key or "",
                    crop_box=cap_crop_box,
                    last_frame_media_id=cap_last_id,
                    last_frame_crop=cap_last_crop,
                    u1=u1,
                    u2=u2,
                    gen_id=gen_id,
                    count=count,
                    resolution=capture_resolution,
                )
                our_body = encode_video_batchexecute_form(cap_rpcid, our_args, at_param)
                new_reqid = (app_reqid + 100000) if app_reqid is not None else 990001
                fire_url = build_rpc_url_from_template(cap["url"], cap_rpcid, new_reqid)
                gap_ms = int(time.time() * 1000) - int(cap["ts_ms"] or 0)

                self._log(
                    "step",
                    f"Fire {cap_rpcid} tất định (frame={starting_frame_media_id[:8]}..., seed={seed_to_use}, _reqid={new_reqid}, gap={gap_ms}ms)",
                )

                # 5. Fire our eb1hJf in-page with x-harness-ours: 1
                fr = br.fire(fire_url, our_body, timeout_s=60.0, poll_s=1.0)
                parsed_submit = parse_batchexecute_text(fr.text)

                if not parsed_submit.get("ok"):
                    kind, hint = describe_reject(parsed_submit.get("grpc_code"), parsed_submit.get("detail") or "")
                    raise BridgeError(f"eb1hJf bị từ chối ngay khi submit ({kind}, 0 credit): {hint}")

                video_media_id = extract_video_submit_media_id(
                    parsed_submit.get("data"),
                    project_id=active_pid,
                    exclude=[starting_frame_media_id, u1, u2, gen_id],
                )
                if not video_media_id:
                    raise BridgeError(
                        f"eb1hJf thành công nhưng không tìm thấy video_media_id trong response: {fr.text[:250]}"
                    )

                self._log("info", f"eb1hJf đã nhận job! video_media_id={video_media_id} (gen_id={gen_id[:8]}...)")

                # 6. Poll jwpduf (0 credit) for completion or policy error
                poll_res = self.poll_video_rpc(
                    br,
                    video_media_id=video_media_id,
                    project_id=active_pid,
                    timeout_s=timeout_s,
                    poll_interval_s=4.0,
                )

                if poll_res["state"] == "failed":
                    err_code = poll_res.get("error_code") or "PUBLIC_ERROR_VIDEO_GENERATION_FAILED"
                    cats = ", ".join(poll_res.get("error_categories") or [])
                    self._cleanup_failed_tiles_in_dom(page)

                    if "PROMINENT_PERSON" in cats or "PROMINENT_PEOPLE" in err_code:
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            f"Ảnh bắt đầu bị bộ lọc người nổi tiếng của Google Flow từ chối ({err_code} [{cats}]). "
                            "Hệ thống đã dừng ngay (không tự ý chỉnh sửa khuôn mặt để giữ đồng nhất nhân vật) — bạn vui lòng tự chỉnh hoặc đổi ảnh bắt đầu nhé."
                        )

                    if attempt + 1 < max_protocol_attempts:
                        self._log(
                            "warn",
                            f"Video bị từ chối bởi bộ lọc ({err_code} / {cats}). "
                            f"Đang tự động làm sạch prompt và thử lại lần {attempt + 2}...",
                        )
                        br.reload(settle_s=4.0)
                        continue

                    br.reload(settle_s=4.0)
                    raise BridgeError(
                        f"Flow từ chối tạo video qua giao thức jwpduf ({err_code} [{cats}]). "
                        "Hãy thử đổi ảnh mẫu / khung hình đầu khác hoặc chỉnh lại prompt."
                    )

                # 7. Video succeeded! If resolution == "1080p", upsample via p0UkFb (`veo_3_1_upsampler_1080p`) first
                signed_url: Optional[str] = None
                if "1080" in str(resolution):
                    signed_url = self.upsample_and_fetch_1080p_url_rpc(
                        br,
                        video_media_id=video_media_id,
                        item_id=poll_res.get("item_id"),
                        project_id=active_pid,
                        aspect_ratio=target_aspect,
                        timeout_s=120.0,
                    )

                if not signed_url:
                    signed_url = poll_res.get("signed_url") or self.fetch_signed_video_url_rpc(
                        br, video_media_id=video_media_id, project_id=active_pid
                    )
                downloaded = self.download_video_verified(br, signed_url, dest_p)
                strip_video_audio(downloaded, log=self._log)
                br.reload(settle_s=4.0)
                return downloaded

        raise BridgeError("Không thể hoàn tất tạo video qua FlowVideoBridge.")

    def generate_text_video_flow(
        self,
        prompt_text: str,
        dest_path: Path | str,
        duration_s: int = 8,
        timeout_s: float = 300.0,
        project_id: Optional[str] = None,
        aspect_ratio: str = "9:16",
        aggressive_sanitize: bool = False,
        seed: Optional[int] = None,
        resolution: str = "1080p",
        *,
        reference_paths: Optional[list[Path | str]] = None,
        model_key: Optional[str] = None,
        model_label: Optional[str] = None,
        count: int = 1,
        offer_resolution: bool = True,
        offer_duration: bool = True,
        capture_resolution: str = "720p",
        video_reference_title: Optional[str] = None,
    ) -> Path:
        """Text/ingredients→video via the composer's "Thành phần" sub-mode.

        Three submit shapes, all captured 0-credit:

        * prompt only → ``YhhmEf``, key ``macaron_cookie_t2v_<n>s``
        * ≥1 image reference chip → ``MZZa6b``, key ``macaron_cookie_r2v_<n>s``
        * a **video** reference chip → ``jIps6``, key ``abra_edit``; the duration lives in
          the clip, not in the key, so ``model_key`` is ignored on that path.

        ``video_reference_title`` mounts a clip already in the project (``None`` takes the
        first one). Supplying it implies the ``jIps6`` path; image references in
        ``reference_paths`` are ignored in that case because Flow fires one submit RPC.
        """
        dest_p = Path(dest_path).resolve()
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        target_aspect = "9:16" if "9:16" in str(aspect_ratio) else "16:9"

        actual_ref_paths: list[Path] = []
        if reference_paths:
            for p in reference_paths:
                resolved = Path(p).resolve()
                if resolved.is_file() and resolved not in actual_ref_paths:
                    actual_ref_paths.append(resolved)

        with FlowBridge(self.cdp_url, log=lambda m: self._log("info", m)) as br:
            page = br.page
            assert page is not None

            if project_id and f"/project/{project_id}" not in page.url:
                self._log("step", f"Điều hướng SPA tới dự án Flow: {project_id}")
                br.nav_project(project_id)

            active_pid = project_id
            if not active_pid and "/project/" in page.url:
                active_pid = page.url.split("/project/")[1].split("/")[0].split("?")[0]
            if not active_pid:
                raise BridgeError("Không xác định được project_id trên trang Flow hiện tại.")
            active_pid = active_pid.strip().lower()

            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self._cleanup_failed_tiles_in_dom(page)

            max_protocol_attempts = 2
            for attempt in range(max_protocol_attempts):
                is_retry = attempt > 0
                clean_prompt = sanitize_video_prompt(prompt_text, aggressive=aggressive_sanitize or is_retry)
                seed_to_use = new_seed() if (seed is None or is_retry) else int(seed)

                ref_log = f" ({len(actual_ref_paths)} refs)" if actual_ref_paths else ""
                self._log(
                    "step",
                    f"[Text→Video {attempt + 1}/{max_protocol_attempts}] {duration_s}s {target_aspect} "
                    f"seed={seed_to_use} model={model_label or 'app'} x{count}{ref_log}",
                )

                self._ensure_recaptcha_ready(br, active_pid)
                self.install_video_hook(br)
                self._ensure_ui_video_mode(
                    page,
                    sub_mode="ingredients",
                    target_aspect=target_aspect,
                    model_label=model_label,
                    duration_s=duration_s,
                    resolution=capture_resolution,
                    count=count,
                    offer_resolution=offer_resolution,
                    offer_duration=offer_duration,
                )

                # 1. Clear previous reference chips
                br.clear_reference_chips()

                # 2. Type prompt into composer first (before chips, so selectAll never touches chips)
                br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
                br.type_prompt(clean_prompt)
                time.sleep(jitter(0.4, 0.1, 0.2))

                # 3. Attach the reference. A video reference and image references are
                #    mutually exclusive: the app fires exactly one submit RPC, and mounting a
                #    video chip takes precedence (it is what the caller asked for).
                if video_reference_title is not None:
                    if not self.attach_video_reference(br, title_match=video_reference_title):
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            "Không gắn được clip tham chiếu vào 'Thành phần' — Flow chỉ nhận "
                            "clip có sẵn trong dự án (tab Video của picker). Hủy submit thay vì "
                            "tạo video không tham chiếu."
                        )
                elif actual_ref_paths:
                    self.attach_video_ingredients(br, actual_ref_paths, settle_s=3.0)

                time.sleep(jitter(0.4, 0.1, 0.2))
                br.click_generate(timeout_s=15.0, expected_mode="video")

                try:
                    cap = self.wait_video_capture(br, timeout_s=25.0)
                    self.disarm_video_hook(br)
                    app_reqid = extract_app_reqid(cap["url"])
                    token, at_param, app_args, cap_rpcid = parse_video_app_capture(cap["body"])
                    if cap_rpcid not in VIDEO_SUBMIT_RPCS:
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            f"Request mồi là {cap_rpcid}, không thuộc nhóm submit đã capture "
                            f"({', '.join(VIDEO_SUBMIT_RPCS)}) "
                            "(composer không ở sub-mode 'Thành phần') — hủy submit."
                        )
                except (TokenParseError, CaptureTimeoutError) as cap_err:
                    self.disarm_video_hook(br)
                    if attempt + 1 < max_protocol_attempts:
                        self._log("warn", f"reCAPTCHA chưa sẵn sàng ({cap_err}) — reload và thử lại...")
                        br.reload(settle_s=5.0)
                        continue
                    br.reload(settle_s=4.0)
                    raise

                u1 = str(uuid.uuid4()).upper()
                u2 = str(uuid.uuid4()).upper()
                gen_id = str(uuid.uuid4()).upper()

                cap_ref_ids = extract_reference_media_ids(app_args)
                cap_video_ref, cap_video_frames = extract_reference_video_from_args(app_args)

                if not model_key:
                    raise BridgeError(
                        "generate_text_video_flow needs the captured model_key "
                        "(macaron_cookie_t2v_*_ / macaron_cookie_r2v_*_), because the duration "
                        "is part of the key."
                    )

                if cap_rpcid == VIDEO_EDIT_RPC or cap_video_ref:
                    our_args = build_video_edit_args(
                        project_id=active_pid,
                        prompt=clean_prompt,
                        recaptcha_token=token,
                        reference_video_media_id=cap_video_ref or "",
                        aspect_ratio=target_aspect,
                        reference_video_frame_count=cap_video_frames or 192,
                        u1=u1,
                        u2=u2,
                        gen_id=gen_id,
                        count=count,
                    )
                else:
                    our_args = build_text_video_args(
                        project_id=active_pid,
                        prompt=clean_prompt,
                        recaptcha_token=token,
                        aspect_ratio=target_aspect,
                        seed=seed_to_use,
                        model_key=model_key,
                        reference_image_media_ids=cap_ref_ids or None,
                        u1=u1,
                        u2=u2,
                        gen_id=gen_id,
                        count=count,
                        resolution=capture_resolution,
                    )

                submit_rpc = cap_rpcid if cap_rpcid in VIDEO_SUBMIT_RPCS else submit_rpc_for(
                    SHAPE_VIDEO_REF if cap_video_ref else (SHAPE_IMAGE_REFS if cap_ref_ids else SHAPE_TEXT)
                )
                our_body = encode_video_batchexecute_form(submit_rpc, our_args, at_param)
                new_reqid = (app_reqid + 100000) if app_reqid is not None else 990001
                fire_url = build_rpc_url_from_template(cap["url"], submit_rpc, new_reqid)

                fr = br.fire(fire_url, our_body, timeout_s=60.0, poll_s=1.0)
                parsed_submit = parse_batchexecute_text(fr.text)
                if not parsed_submit.get("ok"):
                    kind, hint = describe_reject(parsed_submit.get("grpc_code"), parsed_submit.get("detail") or "")
                    raise BridgeError(f"{submit_rpc} bị từ chối ({kind}, 0 credit): {hint}")

                video_media_id = extract_video_submit_media_id(
                    parsed_submit.get("data"),
                    project_id=active_pid,
                    exclude=[u1, u2, gen_id],
                )
                if not video_media_id:
                    raise BridgeError(
                        f"{submit_rpc} thành công nhưng không thấy video_media_id: {fr.text[:250]}"
                    )
                self._log("info", f"{submit_rpc} nhận job: video_media_id={video_media_id}")

                poll_res = self.poll_video_rpc(
                    br,
                    video_media_id=video_media_id,
                    project_id=active_pid,
                    timeout_s=timeout_s,
                    poll_interval_s=4.0,
                )
                if poll_res["state"] == "failed":
                    err_code = poll_res.get("error_code") or "PUBLIC_ERROR_VIDEO_GENERATION_FAILED"
                    cats = ", ".join(poll_res.get("error_categories") or [])
                    self._cleanup_failed_tiles_in_dom(page)
                    if attempt + 1 < max_protocol_attempts and "PROMINENT_PEOPLE" not in err_code:
                        self._log("warn", f"Video bị từ chối ({err_code} / {cats}) — làm sạch prompt và thử lại...")
                        br.reload(settle_s=4.0)
                        continue
                    br.reload(settle_s=4.0)
                    raise BridgeError(f"Flow từ chối tạo video ({err_code} [{cats}]).")

                signed_url: Optional[str] = None
                if "1080" in str(resolution):
                    signed_url = self.upsample_and_fetch_1080p_url_rpc(
                        br,
                        video_media_id=video_media_id,
                        item_id=poll_res.get("item_id"),
                        project_id=active_pid,
                        aspect_ratio=target_aspect,
                        timeout_s=120.0,
                    )
                if not signed_url:
                    signed_url = poll_res.get("signed_url") or self.fetch_signed_video_url_rpc(
                        br, video_media_id=video_media_id, project_id=active_pid
                    )
                downloaded = self.download_video_verified(br, signed_url, dest_p)
                strip_video_audio(downloaded, log=self._log)
                br.reload(settle_s=4.0)
                return downloaded

        raise BridgeError("Không thể hoàn tất tạo video text→video qua FlowVideoBridge.")

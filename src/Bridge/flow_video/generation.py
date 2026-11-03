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
from .constants import VIDEO_MODEL_KEY, VIDEO_SUBMIT_RPC, VIDEO_TEXT_SUBMIT_RPC
from .media_tools import strip_video_audio
from .parsing import (
    extract_starting_frame_from_eb1hjf_args,
    extract_video_submit_media_id,
    parse_video_app_capture,
)
from .payload import build_text_video_args, build_video_args, encode_video_batchexecute_form
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
        model_key: Optional[str] = None,
        model_label: Optional[str] = None,
        count: int = 1,
        offer_resolution: bool = True,
        offer_duration: bool = True,
        capture_resolution: str = "720p",
    ) -> Path:
        """Protocol-level ("Bridge Mode") Video generation on Google Flow (`eb1hJf` + `jwpduf` + `as29s`).

        Workflow:
        1. Connects to CloakBrowser over CDP (`FlowBridge`) and installs `VIDEO_HOOK_JS`.
        2. Uploads starting frame via `maseQ` (synthetic paste on `div.ProseMirror`, with UI fallback).
        3. Intercepts & blocks the app's decoy `eb1hJf` request (0 credit spent on decoy) to borrow
           the freshly minted reCAPTCHA Enterprise token (`0cAFcWeA...`) and starting frame slot.
        4. Builds our deterministic `eb1hJf` payload (`build_video_args`: sanitized prompt, int32 seed,
           aspect enum `1`/`2`, uppercase UUIDs, `_reqid + 100000`) and fires in-page (`x-harness-ours: 1`).
        5. Polls `jwpduf` (0 credit) every 4s for deterministic JSON status:
           - On `PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED`: fails fast in ~8s (no 300s blind wait)
             and automatically performs 1 protocol-level recovery retry with a conditioned starting frame
             (`condition_frame_for_policy_retry`), aggressive prompt sanitization, and a fresh int32 seed.
           - On `succeeded`: mints a 6-hour signed CDN URL via `as29s` (0 credit) and downloads the
             full-bitrate `ftypisom` MP4.
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

            for attempt in range(max_protocol_attempts):
                is_retry = attempt > 0
                use_aggressive = aggressive_sanitize or is_retry
                clean_prompt = sanitize_video_prompt(prompt_text, aggressive=use_aggressive)
                seed_to_use = new_seed() if (seed is None or is_retry) else int(seed)

                self._log(
                    "step",
                    f"[Bridge Mode {attempt + 1}/{max_protocol_attempts}] Tạo Video ({duration_s}s, {target_aspect}, seed={seed_to_use}) từ {current_frame_p.name}",
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

                # 3. Arm eb1hJf blocker (0 credit on decoy), type prompt, click Generate
                br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
                br.type_prompt(clean_prompt)
                time.sleep(jitter(0.4, 0.1, 0.2))
                br.click_generate(timeout_s=15.0, expected_mode="video")

                try:
                    cap = self.wait_video_capture(br, timeout_s=25.0)
                    self.disarm_video_hook(br)
                    app_reqid = extract_app_reqid(cap["url"])
                    token, at_param, app_args, cap_rpcid = parse_video_app_capture(cap["body"])
                    if cap_rpcid != VIDEO_SUBMIT_RPC:
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            f"Request mồi là {cap_rpcid} thay vì {VIDEO_SUBMIT_RPC} (composer không ở chế độ Video) — "
                            "hủy submit để tránh lỗi PUBLIC_ERROR_UNUSUAL_ACTIVITY / tạo nhầm ảnh."
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

                starting_frame_media_id = cap_sf_id or uploaded_media_id
                if not starting_frame_media_id:
                    raise BridgeError(
                        f"Request mồi ({cap_rpcid}) không chứa starting_frame_media_id — kiểm tra chế độ Khung hình."
                    )

                # 4. Build our deterministic eb1hJf request payload
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
                    model_key=model_key or VIDEO_MODEL_KEY,
                    crop_box=cap_crop_box,
                    u1=u1,
                    u2=u2,
                    gen_id=gen_id,
                    count=count,
                    resolution=capture_resolution,
                )
                our_body = encode_video_batchexecute_form(VIDEO_SUBMIT_RPC, our_args, at_param)
                new_reqid = (app_reqid + 100000) if app_reqid is not None else 990001
                fire_url = build_rpc_url_from_template(cap["url"], VIDEO_SUBMIT_RPC, new_reqid)
                gap_ms = int(time.time() * 1000) - int(cap["ts_ms"] or 0)

                self._log(
                    "step",
                    f"Fire {VIDEO_SUBMIT_RPC} tất định (frame={starting_frame_media_id[:8]}..., seed={seed_to_use}, _reqid={new_reqid}, gap={gap_ms}ms)",
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
    ) -> Path:
        """Text/ingredients→video via the composer's "Thành phần" sub-mode (``YhhmEf``).

        Supports prompt-only generation as well as attaching reference images as ingredient
        chips (flow-image-ingredient-chip) via synthetic paste into div.ProseMirror.
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

                # Attach ingredient reference images if provided
                if actual_ref_paths:
                    self.attach_video_ingredients(br, actual_ref_paths, settle_s=3.0)
                else:
                    br.clear_reference_chips()

                br._eval("window.__videoHook.cap = null; window.__blockVideoGen = true;")
                br.type_prompt(clean_prompt)
                time.sleep(jitter(0.4, 0.1, 0.2))
                br.click_generate(timeout_s=15.0, expected_mode="video")

                try:
                    cap = self.wait_video_capture(br, timeout_s=25.0)
                    self.disarm_video_hook(br)
                    app_reqid = extract_app_reqid(cap["url"])
                    token, at_param, app_args, cap_rpcid = parse_video_app_capture(cap["body"])
                    if cap_rpcid not in (VIDEO_TEXT_SUBMIT_RPC, VIDEO_SUBMIT_RPC):
                        br.reload(settle_s=4.0)
                        raise BridgeError(
                            f"Request mồi là {cap_rpcid} thay vì {VIDEO_TEXT_SUBMIT_RPC} "
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

                if actual_ref_paths and isinstance(app_args, list) and app_args and isinstance(app_args[0], list) and app_args[0]:
                    try:
                        import copy
                        base_spec = copy.deepcopy(app_args[0][0])
                        specs = []
                        eff_model_key = model_key or (base_spec[1] if len(base_spec) > 1 and isinstance(base_spec[1], str) else "abra_t2v_8s")
                        is_360 = str(capture_resolution or "").strip().lower().startswith("360")
                        if eff_model_key and is_360 and not eff_model_key.endswith("_360p"):
                            eff_model_key = f"{eff_model_key}_360p"

                        aspect_val = 1 if "9:16" in target_aspect else 2
                        for i in range(max(1, int(count))):
                            s = copy.deepcopy(base_spec)
                            if len(s) > 0 and isinstance(s[0], list):
                                s[0] = [None, None, [[[clean_prompt]]]]
                            if len(s) > 1:
                                s[1] = eff_model_key
                            if len(s) > 2:
                                s[2] = int(aspect_val)
                            if len(s) > 3:
                                s[3] = int(seed_to_use) if i == 0 else new_seed()
                            uuid_idx = None
                            for idx in range(len(s) - 1, 3, -1):
                                slot = s[idx]
                                if isinstance(slot, list) and len(slot) >= 6:
                                    if slot[0] is None and slot[1] is None and slot[2] is None and slot[3] is None:
                                        uuid_idx = idx
                                        break
                            if uuid_idx is None and len(s) > 4 and isinstance(s[4], list) and len(s[4]) >= 6:
                                uuid_idx = 4
                            if uuid_idx is not None:
                                s[uuid_idx][4] = u1 if i == 0 else str(uuid.uuid4()).upper()
                                s[uuid_idx][5] = u2 if i == 0 else str(uuid.uuid4()).upper()
                            specs.append(s)

                        our_args = copy.deepcopy(app_args)
                        our_args[0] = specs
                        if len(our_args) > 1 and isinstance(our_args[1], list):
                            ref = our_args[1]
                            if len(ref) > 10 and isinstance(ref[10], list) and ref[10]:
                                ref[10][0] = token
                        if len(our_args) > 2 and isinstance(our_args[2], list) and our_args[2]:
                            our_args[2][0] = gen_id
                        self._log("info", f"ingredients live capture: đính kèm {len(actual_ref_paths)} ảnh, seed={seed_to_use}, model={eff_model_key}, x{count}")
                    except Exception as exc:
                        self._log("warn", f"Không đọc được spec từ app_args ({exc}) — dùng fallback build_text_video_args")
                        our_args = build_text_video_args(
                            project_id=active_pid,
                            prompt=clean_prompt,
                            recaptcha_token=token,
                            aspect_ratio=target_aspect,
                            seed=seed_to_use,
                            model_key=model_key or "abra_t2v_8s",
                            u1=u1,
                            u2=u2,
                            gen_id=gen_id,
                            count=count,
                            resolution=capture_resolution,
                        )
                else:
                    our_args = build_text_video_args(
                        project_id=active_pid,
                        prompt=clean_prompt,
                        recaptcha_token=token,
                        aspect_ratio=target_aspect,
                        seed=seed_to_use,
                        model_key=model_key or "abra_t2v_8s",
                        u1=u1,
                        u2=u2,
                        gen_id=gen_id,
                        count=count,
                        resolution=capture_resolution,
                    )

                submit_rpc = cap_rpcid if cap_rpcid in (VIDEO_TEXT_SUBMIT_RPC, VIDEO_SUBMIT_RPC) else VIDEO_TEXT_SUBMIT_RPC
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

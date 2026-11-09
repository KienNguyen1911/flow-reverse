"""Canvas node media (image / video / last frame), independent of the try-on pipeline."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...Bridge.flow_video.constants import VIDEO_EDIT_MODEL_KEY
from ...Workflows.flow_catalog import (
    VIDEO_SUB_MODES,
    CatalogError,
    capture_resolution,
    image_model_key,
    normalize_count,
    resolve_image_model,
    resolve_video_model,
    video_model_key,
)
from ...Workflows.media_service import (
    AspectNotVerifiedError,
    UnsupportedOptionError,
    node_options,
    normalize_video_ratio,
    normalize_video_resolution,
    resolve_image_aspect,
    resolve_input_path,
    validate_video_duration,
)
from ..context import AppContext
from ..settings import MAX_PROMPT_CHARS

class NodeImageBody(BaseModel):
    """One canvas image node: prompt + ratio + optional attached reference image(s)."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect_ratio: Optional[str] = None      # one of the 5 captured ratios (see /api/node/options)
    aspect: Optional[int] = None            # raw enum escape hatch (wins over aspect_ratio)
    seed: Optional[int] = None
    #: Composer model id or label (`nano_banana_pro` / `Nano Banana Pro`).
    #: See `src/Workflows/flow_catalog.py` — never guess a key.
    model: Optional[str] = None
    #: Batch size, mirroring the composer's x1..x4.
    count: int = 1
    #: When true the Flow composer is in "Tác nhân" (Agent) mode: it hides every
    #: model/aspect/count control, so user values are not applied.
    agent_mode: bool = False
    reference_image_path: Optional[str] = None   # path or /api/uploads|references|assets URL
    reference_image_paths: Optional[list[str]] = None
    project_id: Optional[str] = None
    workspace_project_id: Optional[str] = None
    preferred_account_id: Optional[str] = None
    #: Đánh dấu ảnh này là **ảnh sản phẩm** ⇒ chép vào `out/items/<project_id>/` sau khi
    #: sinh xong. Độc lập với kịch bản: người bán có nhiều món, dùng lại cho nhiều bộ phim.
    is_item: bool = False
    #: Tên món để đặt tên file trong thư viện (`Áo Kiểu Nữ Donna` → `ao_kieu_nu_donna.png`).
    item_name: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeVideoBody(BaseModel):
    """One canvas video node: prompt + sub-mode + model + aspect/resolution/duration/count.

    Mirrors the Flow composer: sub-mode "Khung hình" (image→video, needs a frame) or
    "Thành phần" (text→video, no frame). Model choice decides whether resolution and
    duration are selectable at all (Veo fixes both).
    """

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect_ratio: str = "9:16"
    #: ``frames`` = Khung hình (image→video) | ``ingredients`` = Thành phần (text→video).
    sub_mode: str = "frames"
    #: Composer model id or label (`omni_1_2_flash` / `Omni 1.2 Flash`).
    model: Optional[str] = None
    #: Batch size, mirroring the composer's x1..x4.
    count: int = 1
    #: When true the Flow composer is in "Tác nhân" (Agent) mode: it hides every
    #: model/aspect/resolution/duration/count control, so user values are not applied.
    agent_mode: bool = False
    frame_path: Optional[str] = None        # attached image (path or /api/... URL)
    #: Last frame for the "Kết thúc" slot ("Khung hình" only). Adding it switches the submit
    #: to `nprQif` and caps the duration at 10s.
    last_frame_path: Optional[str] = None
    #: Title (substring) of a project clip to mount as a "Thành phần" video reference. Set it
    #: to take the `jIps6` path (model key `abra_edit`, duration not in the key).
    video_reference_title: Optional[str] = None
    reference_image_path: Optional[str] = None
    reference_image_paths: Optional[list[str]] = None
    image_prompt: Optional[str] = None      # used only when auto_image generates the frame
    image_aspect_ratio: str = "16:9"        # frame image ratio
    auto_image: bool = True
    seed: Optional[int] = None
    resolution: str = "1080p"
    duration_s: int = 8
    project_id: Optional[str] = None
    workspace_project_id: Optional[str] = None
    preferred_account_id: Optional[str] = None
    dry_run: bool = False
    remove_watermark: bool = True
    confirm: bool = False


class NodeLastFrameBody(BaseModel):
    """Extract last frame of a video for chaining to next video/image node (0 credit)."""

    video_path: str
    remove_watermark: bool = True
    workspace_project_id: Optional[str] = None


def build_router(ctx: AppContext) -> APIRouter:
    pool = ctx.pool
    manager = ctx.manager
    router = APIRouter()

    @router.get("/api/node/options")
    def api_node_options():
        return node_options()

    @router.post("/api/node/image")
    def api_node_image(body: NodeImageBody):
        try:
            ratio, enum = resolve_image_aspect(body.aspect_ratio, body.aspect)
            model_info = resolve_image_model(body.model)
            count = normalize_count(body.count)
        except (AspectNotVerifiedError, UnsupportedOptionError, CatalogError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        if body.seed is not None and not (1 <= int(body.seed) <= 2147483647):
            raise HTTPException(status_code=400, detail="seed phải nằm trong int32: 1..2147483647")

        # Collect & validate all reference image paths
        all_refs: list[str] = []
        if body.reference_image_paths:
            for rp in body.reference_image_paths:
                if rp and rp not in all_refs:
                    all_refs.append(rp)
        if body.reference_image_path and body.reference_image_path not in all_refs:
            all_refs.insert(0, body.reference_image_path)

        for ref_p in all_refs:
            if not resolve_input_path(ref_p).is_file():
                raise HTTPException(status_code=400, detail=f"Không tìm thấy ảnh đính kèm: {ref_p}")

        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Chạy thật cần confirm=true. Mỗi ảnh ~1 credit nếu Google nhận (reject = 0).")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        job = manager.submit("node_image", {
            "prompt": body.prompt.strip(),
            "aspect_ratio": ratio,
            "aspect": enum,
            "seed": body.seed,
            "model": model_info.id,
            "count": count,
            "agent_mode": body.agent_mode,
            "reference_image_path": all_refs[0] if all_refs else None,
            "reference_image_paths": all_refs if all_refs else None,
            "project_id": body.project_id,
            "workspace_project_id": body.workspace_project_id,
            "preferred_account_id": body.preferred_account_id,
            "is_item": body.is_item,
            "item_name": body.item_name,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        return {
            "job_id": job.id, "kind": "image", "aspect_ratio": ratio, "aspect": enum,
            "model": model_info.id, "model_label": model_info.label,
            "model_key": image_model_key(model_info), "count": count,
        }

    @router.post("/api/node/video")
    def api_node_video(body: NodeVideoBody):
        sub_mode = str(body.sub_mode or "frames").strip().lower()
        # A video reference only exists in "Thành phần", and it changes the whole submit
        # (jIps6 / abra_edit) — so it decides the sub-mode rather than being ignored.
        if body.video_reference_title is not None:
            sub_mode = "ingredients"
        # A last frame only exists in "Khung hình"; it also narrows the duration window, so it
        # must be known BEFORE the duration is validated (3..10s instead of 3..15s).
        has_last_frame = bool(body.last_frame_path) and sub_mode == "frames"
        try:
            ratio = normalize_video_ratio(body.aspect_ratio)
            model_info = resolve_video_model(body.model)
            resolution = normalize_video_resolution(body.resolution, model=model_info.id)
            duration = validate_video_duration(
                body.duration_s, model=model_info.id, has_last_frame=has_last_frame
            )
            if sub_mode not in VIDEO_SUB_MODES:
                raise UnsupportedOptionError(
                    f"Sub-mode video {body.sub_mode!r} không hợp lệ. Chọn: {', '.join(VIDEO_SUB_MODES)}."
                )
            count = normalize_count(body.count)
            model_key = (
                # A video reference leaves the Omni family: `abra_edit`, duration in the clip.
                VIDEO_EDIT_MODEL_KEY
                if body.video_reference_title is not None
                else video_model_key(
                    model_info, sub_mode=sub_mode, duration_s=duration,
                    resolution=capture_resolution(model_info, resolution), aspect_ratio=ratio,
                    has_last_frame=has_last_frame,
                )
            )
            image_ratio, _image_enum = resolve_image_aspect(body.image_aspect_ratio)
        except (AspectNotVerifiedError, UnsupportedOptionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        # Collect & validate all reference image paths
        all_refs: list[str] = []
        if body.reference_image_paths:
            for rp in body.reference_image_paths:
                if rp and rp not in all_refs:
                    all_refs.append(rp)
        if body.reference_image_path and body.reference_image_path not in all_refs:
            all_refs.insert(0, body.reference_image_path)
        if sub_mode == "ingredients" and body.frame_path and body.frame_path not in all_refs:
            all_refs.append(body.frame_path)

        for ref_p in all_refs:
            if not resolve_input_path(ref_p).is_file():
                raise HTTPException(status_code=400, detail=f"Không tìm thấy ảnh đính kèm: {ref_p}")

        if sub_mode == "frames" and not body.frame_path and not body.auto_image:
            raise HTTPException(
                status_code=400,
                detail="Sub-mode 'Khung hình' (image→video) cần ảnh đính kèm (frame_path) hoặc "
                       "bật auto_image=true để tạo ảnh khung hình trước. Dùng sub_mode='ingredients' "
                       "nếu chỉ muốn text→video từ câu lệnh.",
            )
        if sub_mode == "frames" and body.frame_path and not resolve_input_path(body.frame_path).is_file():
            raise HTTPException(status_code=400, detail=f"Không tìm thấy ảnh đính kèm: {body.frame_path}")
        if has_last_frame and not resolve_input_path(body.last_frame_path).is_file():
            raise HTTPException(
                status_code=400,
                detail=f"Không tìm thấy ảnh khung 'Kết thúc': {body.last_frame_path}",
            )
        if not body.dry_run:
            if not body.confirm:
                raise HTTPException(status_code=400,
                                    detail="Chạy thật cần confirm=true. Mỗi video ~1 credit nếu Google nhận (reject = 0).")
            if not pool.available_accounts():
                raise HTTPException(status_code=423,
                                    detail="Tất cả account đang cooldown/disabled — chờ hết cooldown hoặc reset trong tab Pool.")
        job = manager.submit("node_video", {
            "prompt": body.prompt.strip(),
            "frame_path": body.frame_path,
            "last_frame_path": body.last_frame_path if has_last_frame else None,
            "video_reference_title": body.video_reference_title,
            "reference_image_path": all_refs[0] if all_refs else None,
            "reference_image_paths": all_refs if all_refs else None,
            "image_prompt": body.image_prompt,
            "image_aspect_ratio": image_ratio,
            "auto_image": body.auto_image,
            "aspect_ratio": ratio,
            "seed": body.seed,
            "resolution": resolution,
            "duration_s": duration,
            "model": model_info.id,
            "sub_mode": sub_mode,
            "count": count,
            "agent_mode": body.agent_mode,
            "project_id": body.project_id,
            "workspace_project_id": body.workspace_project_id,
            "preferred_account_id": body.preferred_account_id,
            "dry_run": body.dry_run,
            "remove_watermark": body.remove_watermark,
        })
        frame_source = (
            ("provided" if (body.frame_path or all_refs) else "none") if sub_mode == "ingredients"
            else ("provided" if body.frame_path else "generated")
        )
        return {
            "job_id": job.id, "kind": "video", "aspect_ratio": ratio,
            "resolution": resolution, "duration_s": duration,
            "model": model_info.id, "model_label": model_info.label,
            "model_key": model_key, "sub_mode": sub_mode, "count": count,
            "frame_source": frame_source, "has_last_frame": has_last_frame,
        }

    @router.post("/api/node/last_frame")
    def api_node_last_frame(body: NodeLastFrameBody):
        resolved = resolve_input_path(body.video_path)
        if not resolved.is_file():
            raise HTTPException(status_code=400, detail=f"Không tìm thấy file video: {body.video_path}")
        job = manager.submit("node_last_frame", {
            "video_path": str(resolved),
            "remove_watermark": body.remove_watermark,
            "workspace_project_id": body.workspace_project_id,
        })
        return {"job_id": job.id, "kind": "last_frame"}

    @router.get("/api/node/files/{file_path:path}")
    def api_node_file(file_path: str):
        base = manager.node_out.resolve()
        p = (base / file_path).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            raise HTTPException(status_code=404, detail="không tìm thấy file node")
        return FileResponse(p)

    return router

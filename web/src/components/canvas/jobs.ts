import type { GenerateNodePromptRequest, Job } from "../../types";
import { SCRIPT_PATH } from "./constants";
import type { CanvasNode, NodeStatus } from "./types";

/** Map a backend job snapshot onto the node fields it determines. */
export function jobPatch(n: CanvasNode, j: Job): Partial<CanvasNode> {
  const patch: Partial<CanvasNode> = { status: j.state as NodeStatus };
  const r = j.result as Record<string, unknown> | undefined;
  if (r) {
    const errDetail = r.hint
      ? `${r.reason ? `[${r.reason}] ` : ""}${r.hint}`
      : ((r.reason as string) ?? (r.detail as string) ?? null);
    if (n.type === "image" || n.type === "last_frame") {
      patch.fileUrl = (r.file_url as string) ?? null;
      patch.reason = errDetail;
    } else {
      patch.videoUrl = (r.video_url as string) ?? null;
      patch.frameUrl = (r.frame_url as string) ?? null;
      patch.reason = errDetail;
    }
    patch.elapsedS = (r.elapsed_s as number) ?? null;
    // run_id là thứ duy nhất nối được node → thư mục file thật khi xuất bộ dựng phim.
    if (typeof r.run_id === "string" && r.run_id) patch.runId = r.run_id;
    // Ảnh sản phẩm đã được server chép vào thư viện: tên file thật (đã slugify) có thể
    // khác chữ người dùng gõ, nên ghi lại để lần xuất sau không đẻ ra file thứ hai.
    if (typeof r.item_name === "string" && r.item_name) patch.itemName = r.item_name;
  }
  if (!patch.reason && j.error) patch.reason = j.error;
  return patch;
}

/**
 * Request body for the local AI prompt agent (manual "AI Prompt" button and the
 * JIT step of a workflow run share it).
 */
export function buildPromptRequest(
  target: CanvasNode,
  upstreamUrls: string[],
  isVideoContinuation: boolean,
  clipRoleOf: (clipId?: string | null) => string | undefined,
): GenerateNodePromptRequest {
  return {
    node_id: target.id,
    node_type: target.type as "image" | "video",
    upstream_media_urls: upstreamUrls,
    skill_id: target.agentSkillId || undefined,
    custom_hint: target.agentCustomHint || undefined,
    is_video_continuation: isVideoContinuation,
    // Thiếu `clip_id` thì agent không đọc được role/shots/chain_from/beats và mọi node video
    // sinh ra cùng một prompt. `script_path` để backend đọc đúng kịch bản đang dùng.
    clip_id: target.type === "video" ? target.clipId || undefined : undefined,
    clip_role: target.type === "video" ? clipRoleOf(target.clipId) : undefined,
    script_path: target.type === "video" ? SCRIPT_PATH : undefined,
    // Ảnh sản phẩm ⇒ agent chọn skill cutout, và tên món là ngữ cảnh duy nhất khi
    // node chưa gắn ảnh tham chiếu. Thiếu 2 trường này thì JIT chọn skill lookbook
    // thay vì skill cutout, và prompt sinh ra lại đi vẽ người mẫu cho node ảnh sản phẩm.
    is_item: !!target.isItem,
    item_name: target.isItem ? target.itemName || undefined : undefined,
  };
}

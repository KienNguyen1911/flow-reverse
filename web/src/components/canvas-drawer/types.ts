/**
 * The live canvas node shape — the single declaration.
 *
 * `web/src/types.ts` derives the persisted `CanvasNodeState` from this one instead of restating
 * it, so a field added here cannot silently go unsaved. That is not hypothetical: `runId` used to
 * exist here and not there, and because `canvasStateToGraph` rebuilds nodes field by field, the
 * delivery export lost every clip id after a reload.
 */
export interface CanvasDrawerNode {
  id: string;
  type: "ref" | "image" | "video" | "last_frame";
  x: number;
  y: number;
  label?: string | null;
  prompt: string;
  fileName?: string | null;
  aspectRatio: string;
  seed: number | null;
  sourceImageId: string | null;
  sourceImageIds?: string[];
  videoRatio: string;
  resolution: string;
  imageAspectRatio: string;
  /** Model ảnh đã chọn (`nano_banana_pro` …) — danh sách đọc từ `/api/node/options`. */
  imageModel?: string | null;
  /** Số ảnh mỗi lần chạy (x1..x4 như composer Flow). */
  imageCount?: number;
  /** Model video đã chọn (`omni_1_2_flash` …). */
  videoModel?: string | null;
  /** Sub-mode video: `frames` (Khung hình) | `ingredients` (Thành phần). */
  videoSubMode?: string;
  /** Số video mỗi lần chạy (x1..x4). */
  videoCount?: number;
  /** Thời lượng video yêu cầu (3..15s cho Omni 1.2; Veo khoá 8s). Danh sách đọc từ `durations_s`. */
  videoDurationS?: number;
  /**
   * Ảnh khung "Kết thúc" (chỉ sub-mode `frames`). Gắn vào thì Flow đổi RPC sang `nprQif`
   * và hạ trần thời lượng xuống 10s — slider nhận `maxAllowed` để phản ánh trần đó.
   * Trỏ tới node nguồn (ref/image/last_frame) giống `sourceImageId`, không phải URL thô.
   */
  videoLastFrameSourceId?: string | null;
  /**
   * Tiêu đề clip trong dự án để gắn làm tham chiếu video (chỉ sub-mode `ingredients`).
   * Có giá trị thì Flow bỏ họ Omni: RPC `jIps6`, model key `abra_edit`, duration nằm ở clip.
   */
  videoReferenceTitle?: string | null;
  /**
   * Flow composer đang ở chế độ "Tác nhân" (Agent). Khi bật, Flow ẩn toàn bộ
   * model/tỷ lệ/độ phân giải/thời lượng/số lượng ⇒ node không cho chọn và chỉ gửi prompt.
   */
  agentMode?: boolean;
  autoImagePrompt: string;
  removeWatermark?: boolean;
  jobId: string | null;
  /** `run_id` của lần sinh thành công gần nhất — delivery export cần nó để nối clip → file. */
  runId?: string | null;
  status: "idle" | "queued" | "running" | "succeeded" | "failed" | "rejected" | "skipped";
  fileUrl?: string | null;
  videoUrl?: string | null;
  frameUrl?: string | null;
  reason?: string | null;
  elapsedS?: number | null;
  agentSkillId?: string | null;
  agentCustomHint?: string | null;
  /**
   * Clip trong kịch bản Lookbook mà node video này đang sinh (`clip1`, `clip2`, …).
   * Bắt buộc với node video nhiều clip: thiếu nó thì agent không đọc được `role`, shots,
   * `chain_from` hay beats, và mọi node video sinh ra cùng một prompt.
   */
  clipId?: string | null;
  /** Ảnh node này sinh ra là **coordinate sheet** ⇒ chép vào thư viện `items/` của project. */
  isItem?: boolean;
  /** Tên bộ phối, dùng để đặt tên file trong thư viện. */
  itemName?: string | null;
}

/** Tab / vùng cần focus khi mở từ node body (pill, chip, nút Expand). */
export type DrawerSection = "config" | "prompt" | "sources" | "preview" | "logs" | "error";

export type DrawerTab = "error" | "logs" | "config" | "preview";

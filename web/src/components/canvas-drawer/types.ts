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
  /** Model ảnh đã chọn (`nano_banana_pro` …) — danh sách từ `/api/node/options`. */
  imageModel?: string | null;
  /** Số ảnh mỗi lần chạy (x1..x4 như composer Flow). */
  imageCount?: number;
  /** Model video đã chọn (`omni_1_1_flash` …). */
  videoModel?: string | null;
  /** Sub-mode video: `frames` (Khung hình) | `ingredients` (Thành phần). */
  videoSubMode?: string;
  /** Số video mỗi lần chạy (x1..x4). */
  videoCount?: number;
  /** Thời lượng yêu cầu (4/6/8/10s; Veo khoá 8s). */
  videoDurationS?: number;
  /** Flow composer đang bật "Tác nhân" ⇒ ẩn model/tỷ lệ/độ phân giải/thời lượng/số lượng. */
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
  /** Clip trong kịch bản Lookbook (`clip1`, `clip2`, …) mà node video này sinh. */
  clipId?: string | null;
  /** Ảnh node này sinh ra là **ảnh sản phẩm** ⇒ chép vào thư viện `items/` của project. */
  isItem?: boolean;
  /** Tên món, dùng để đặt tên file trong thư viện. */
  itemName?: string | null;
  /** Phạm vi cắt món: `top` (áo) | `bottom` (quần/váy) | `full_set` (cả bộ). */
  itemScope?: "top" | "bottom" | "full_set" | null;
}

/** Tab / vùng cần focus khi mở từ node body (pill, chip, nút Expand). */
export type DrawerSection = "config" | "prompt" | "sources" | "preview" | "logs" | "error";

export type DrawerTab = "error" | "logs" | "config" | "preview";

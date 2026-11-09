import type { CanvasDrawerNode, ItemScope } from "./components/canvas-drawer/types";

export type { ItemScope };

export interface BreakerInfo {
  cooldown_remaining_s: number;
  cooldown_reason: string | null;
  total_accepted: number;
  total_rejected: number;
  consecutive_anti_abuse: number;
}

export interface Status {
  cdp_url: string;
  cdp_ok: boolean;
  browser?: string | null;
  flow_tab_url?: string | null;
  flow_project_id?: string | null;
  page_targets: number;
  cooldown_until_ms: number;
  cooldown_reason?: string | null;
  error?: string | null;
  queue_depth: number;
  current_job_id?: string | null;
  breaker: BreakerInfo;
}

export interface PoolAccount {
  id: string;
  profile_id: string;
  cdp_port: number;
  cdp_url: string;
  enabled: boolean;
  note?: string | null;
  /** Credential-free proxy label, e.g. "http://user@host:8080". */
  proxy?: string | null;
  has_proxy?: boolean;
  running: boolean;
  managed: boolean;
  status: "ready" | "cooldown" | "disabled" | "error" | string;
  role: "active" | "standby" | string;
  cooldown_remaining_s: number;
  cooldown_reason?: string | null;
  total_completed: number;
  total_rejected: number;
  total_failed: number;
  last_used_at_ms?: number | null;
  last_error?: string | null;
}

export interface AddAccountPayload {
  id: string;
  profile_id?: string;
  cdp_port?: number;
  enabled?: boolean;
  note?: string;
  create_profile?: boolean;
  /** Per-browser proxy: http/https/socks5, "host:port" or "user:pass@host:port". Empty ⇒ direct IP. */
  proxy?: string | null;
  proxy_bypass?: string | null;
}

export interface UpdateAccountPayload {
  enabled?: boolean;
  note?: string;
  cdp_port?: number;
  proxy?: string | null;
  proxy_bypass?: string | null;
  /** Drop the proxy and go back to the direct IP. */
  clear_proxy?: boolean;
}

export interface AccountDetail {
  account: {
    id: string;
    profile_id: string;
    cdp_port: number;
    cdp_url: string;
    enabled: boolean;
    note?: string | null;
    proxy?: string | null;
    has_proxy?: boolean;
    running: boolean;
    managed: boolean;
    status: string;
    total_completed: number;
    total_rejected: number;
    total_failed: number;
  };
  flow: {
    cdp_ok?: boolean;
    flow_tab_url?: string | null;
    flow_project_id?: string | null;
    browser?: string | null;
    error?: string | null;
  } | null;
}

export interface PoolBatchInfo {
  job_id: string;
  j: number;
  n_alloc: number;
  accounts: string[];
  ts_ms: number;
}

export interface PoolInfo {
  n_total: number;
  n_available: number;
  target_jobs_per_account: number;
  max_active_browsers: number;
  working_set: string[];
  current_batch: PoolBatchInfo | null;
  last_batch: PoolBatchInfo | null;
  accounts: PoolAccount[];
  reference_cache: { accounts: number; entries: number };
}

export interface Project {
  id: string;
  title?: string | null;
  source: string;
  last_used_ts?: number | null;
}

export type JobState = "queued" | "running" | "succeeded" | "failed" | "rejected";

export interface JobEvent {
  i: number;
  ts_ms: number;
  kind: string;
  message: string;
  data: Record<string, unknown>;
}

export interface GeneratedImage {
  media_id?: string | null;
  item_id?: string | null;
  generation_id?: string | null;
  generation_id_echo?: string | null;
  seed?: number | null;
  seed_echo?: number | null;
  prompt?: string | null;
  title?: string | null;
  resolution?: number[] | null;
  signed_url?: string | null;
  project_id?: string | null;
  file_path?: string | null;
  file_bytes?: number | null;
}

export interface JobResult {
  status?: string;
  image?: GeneratedImage | null;
  image_url?: string;
  reason?: string | null;
  hint?: string | null;
  detail?: string | null;
  grpc_code?: number | null;
  elapsed_s?: number | null;
  run_dir?: string | null;
  seed_used?: number | null;
  anti_abuse?: boolean;
  credit_note?: string;
  count?: number;
  id?: string;
  title?: string | null;
  account_id?: string | null;
  // -- batch fields (kind === "batch_generate") ---------------------------- //
  batch?: boolean;
  total?: number;
  ok?: number;
  dry_run?: number;
  rejected?: number;
  failed?: number;
  skipped?: number;
  pending?: number;
  n_alloc?: number;
  accounts?: string[];
  output_dir?: string;
  items?: BatchItemResult[];
}

export interface BatchItemResult {
  idx: number;
  shot_id?: string | null;
  prompt: string;
  mode: string;
  status: "pending" | "running" | "ok" | "dry_run" | "rejected" | "failed" | "skipped" | string;
  account_id?: string | null;
  attempts: number;
  error?: string | null;
  output_path?: string | null;
  result?: JobResult | null;
}

export interface BatchItemRequest {
  prompt: string;
  seed?: number | null;
  mode?: "t2i" | "i2i";
  reference_image_path?: string | null;
  depends_on_shot_id?: string | null;
  id?: string | null;
  filename?: string | null;
}

export interface Job {
  id: string;
  kind: "generate" | "dry_run" | "create_project" | "list_projects" | "batch_generate" | string;
  params: {
    project_id?: string;
    prompt?: string;
    aspect?: number;
    seed?: number | null;
    title?: string;
    items?: BatchItemRequest[];
    dry_run?: boolean;
    remove_watermark?: boolean;
  };
  state: JobState;
  created_ms: number;
  started_ms?: number | null;
  finished_ms?: number | null;
  result?: JobResult | null;
  error?: string | null;
  event_count: number;
  events?: JobEvent[];
}

export interface GalleryRun {
  run: string;
  file: string;
  url: string;
  prompt?: string | null;
  title?: string | null;
  project_id?: string | null;
  workspace_project_id?: string | null;
  is_pinned?: boolean;
  seed?: number | null;
  seed_echo?: number | null;
  resolution?: number[] | null;
  media_id?: string | null;
  created_ts?: string | null;
  elapsed_s?: number | null;
  file_bytes?: number | null;
  status?: string | null;
}

export interface TryOnStepInfo {
  id: number;
  key: string;
  label: string;
  desc?: string;
  status: "pending" | "running" | "succeeded" | "failed" | string;
  error?: string | null;
}

export interface TryOnRunManifest {
  run_id: string;
  status: "succeeded" | "failed" | "running" | string;
  product_title?: string;
  dest_dir?: string;
  shopee_images?: string[];
  model_image_path?: string;
  garment_image_path?: string;
  image_prompt?: string;
  first_frame_path?: string | null;
  video_prompt_1?: string;
  video_prompt_2?: string;
  video_1_path?: string | null;
  last_frame_path?: string | null;
  video_2_path?: string | null;
  final_video_path?: string | null;
  elapsed_s?: number;
  dry_run?: boolean;
  single_video?: boolean;
  aspect_ratio?: string;
  current_step?: number;
  failed_step?: number | null;
  failed_step_label?: string | null;
  steps?: TryOnStepInfo[];
  error?: string | null;
  account_id?: string | null;
  first_frame_url?: string | null;
  video_1_url?: string | null;
  last_frame_url?: string | null;
  video_2_url?: string | null;
  final_video_url?: string | null;
}

// --------------------------------------------------------------------------- //
// Canvas node media (images / videos) — /api/node/*
// --------------------------------------------------------------------------- //

/** Một clip trong kịch bản Lookbook, dùng cho ô chọn clip trên node video. */
export interface ScriptClipOption {
  id: string;
  role: "hook" | "showcase" | "detail";
  duration_s: number;
  camera?: string | null;
  chain_from?: string | null;
  goal?: string;
  has_beats?: boolean;
}

/** Một model trong composer Flow (nguồn: `src/Workflows/flow_catalog.py`). */
export interface NodeImageModelOption {
  id: string;
  label: string;
  /** Model key THẬT đã capture (`GEM_PIX_2` / `HARBOR_SEAL` / `BELUGA`) — chỉ để hiển thị. */
  model_key?: string | null;
}

/**
 * Một model video. `has_resolution` / `has_duration` là bằng chứng quan sát được: chọn model
 * Veo thì composer Flow **biến mất** nhóm độ phân giải + thời lượng (cố định 720p / 8s).
 * UI phải disable hoặc ẩn hai nhóm đó theo cờ này, không được cho chọn rồi fail.
 */
export interface NodeVideoModelOption {
  id: string;
  label: string;
  aspect_ratios: string[];
  resolutions: string[];
  durations_s: number[];
  has_resolution: boolean;
  has_duration: boolean;
  model_keys?: Record<string, Record<string, string>>;
}

/** Agent ("Tác nhân") khoá toàn bộ cấu hình — Flow ẩn hết khỏi composer. */
export interface NodeAgentModeOptions {
  supported: boolean;
  /** True ⇒ bật agent thì model/tỷ lệ/độ phân giải/thời lượng/số lượng không do user chọn. */
  locks_config: boolean;
  note?: string;
  locked_fields: string[];
  extra_buttons?: { id: string; label: string; purpose?: string }[];
}

export interface NodeMediaOptions {
  /** Validation caps enforced by the API; the UI mirrors them (xem `src/Workflows/limits.py`). */
  limits: {
    max_prompt_chars: number;
    max_batch_items: number;
  };
  /**
   * Kịch bản Lookbook mặc định. Node video cần `clips[].id` để agent biết đang viết clip nào
   * (`role`, shots, `chain_from`, beats). Trước đây FE không có nguồn nào để chọn nên mọi node video
   * nhận context rỗng và sinh ra cùng một prompt.
   */
  script?: {
    path: string | null;
    slug?: string;
    title?: string;
    duration_s?: number;
    clips: ScriptClipOption[];
  };
  /** Toàn bộ danh sách dưới đây do backend trả về — FE KHÔNG được hard-code. */
  image: {
    modes: string[];
    mode_labels: Record<string, string>;
    aspect_ratios: string[];
    aspect_enums: Record<string, number>;
    default_aspect_ratio: string;
    models: NodeImageModelOption[];
    default_model: string;
    counts: number[];
    default_count: number;
    supports_reference_image: boolean;
    supports_seed: boolean;
    supports_watermark_removal: boolean;
  };
  video: {
    modes: string[];
    sub_modes: string[];
    sub_mode_labels: Record<string, string>;
    sub_mode_descriptions?: Record<string, string>;
    default_sub_mode: string;
    aspect_ratios: string[];
    aspect_enums: Record<string, number>;
    default_aspect_ratio: string;
    models: NodeVideoModelOption[];
    default_model: string;
    counts: number[];
    default_count: number;
    supports_starting_frame: boolean;
    supports_text_to_video: boolean;
    auto_image_chain: boolean;
    supports_seed: boolean;
    supports_watermark_removal: boolean;
  };
  agent?: NodeAgentModeOptions;
}

export interface NodeImageRequest {
  prompt: string;
  aspect_ratio?: string;
  aspect?: number;
  seed?: number | null;
  /** Model id hoặc label (`nano_banana_pro` / `Nano Banana Pro`). */
  model?: string | null;
  /** Số ảnh mỗi lần chạy (x1..x4 như composer). */
  count?: number;
  /** Flow đang ở chế độ "Tác nhân": bỏ qua model/tỷ lệ/count do user chọn. */
  agent_mode?: boolean;
  reference_image_path?: string | null;
  reference_image_paths?: string[];
  project_id?: string | null;
  workspace_project_id?: string | null;
  preferred_account_id?: string | null;
  /** Ảnh này là ảnh sản phẩm ⇒ chép vào thư viện `items/` của project sau khi sinh. */
  is_item?: boolean;
  /** Tên món để đặt tên file (bỏ dấu, thường hoá). */
  item_name?: string | null;
  dry_run?: boolean;
  remove_watermark?: boolean;
  confirm?: boolean;
}

export interface NodeVideoRequest {
  prompt: string;
  aspect_ratio?: string;
  /** `frames` = Khung hình (image→video) | `ingredients` = Thành phần (text→video). */
  sub_mode?: string;
  /** Model id hoặc label (`omni_1_1_flash` / `Omni 1.1 Flash`). */
  model?: string | null;
  /** Số video mỗi lần chạy (x1..x4 như composer). */
  count?: number;
  /** Flow đang ở chế độ "Tác nhân": bỏ qua cấu hình do user chọn. */
  agent_mode?: boolean;
  frame_path?: string | null;
  /** Ảnh khung "Kết thúc" (`frames` only) — bật RPC `nprQif`, trần thời lượng hạ xuống 10s. */
  last_frame_path?: string | null;
  /** Tiêu đề (substring) clip trong dự án để gắn làm tham chiếu video — bật `jIps6`/`abra_edit`. */
  video_reference_title?: string | null;
  reference_image_path?: string | null;
  reference_image_paths?: string[];
  image_prompt?: string | null;
  image_aspect_ratio?: string;
  auto_image?: boolean;
  seed?: number | null;
  resolution?: string;
  duration_s?: number;
  project_id?: string | null;
  workspace_project_id?: string | null;
  preferred_account_id?: string | null;
  dry_run?: boolean;
  remove_watermark?: boolean;
  confirm?: boolean;
}

export interface NodeLastFrameRequest {
  video_path: string;
  remove_watermark?: boolean;
  workspace_project_id?: string | null;
}

export interface NodeImageResult {
  status: "ok" | "ok_no_download" | "rejected" | "dry_run" | "failed" | string;
  prompt: string;
  aspect_ratio: string;
  aspect_enum: number;
  project_id: string;
  seed_used?: number | null;
  run_id: string;
  run_dir: string;
  file_path?: string | null;
  file_url?: string | null;
  file_bytes?: number | null;
  width?: number | null;
  height?: number | null;
  resolution?: number[] | null;
  signed_url?: string | null;
  media_id?: string | null;
  reference_sha256?: string | null;
  reference_media_id?: string | null;
  /** Composer model that actually ran (catalog id) + its label. */
  model?: string;
  model_label?: string;
  /** Số ảnh đã yêu cầu (x1..x4). */
  count?: number;
  /** True ⇒ composer ở chế độ "Tác nhân", cấu hình do Flow quyết định. */
  agent_mode?: boolean;
  dry_run?: boolean;
  elapsed_s?: number;
  reason?: string | null;
  hint?: string | null;
  account_id?: string | null;
}

export interface NodeVideoResult {
  status: "ok" | "dry_run" | string;
  prompt: string;
  aspect_ratio: string;
  run_id: string;
  run_dir: string;
  project_id: string;
  seed_used?: number | null;
  video_path?: string | null;
  video_url?: string | null;
  video_bytes?: number | null;
  resolution: string;
  duration_s: number;
  /** Composer config that actually ran (xem `src/Workflows/flow_catalog.py`). */
  model?: string;
  model_label?: string;
  model_key?: string | null;
  sub_mode?: string;
  count?: number;
  agent_mode?: boolean;
  frame_path?: string | null;
  frame_url?: string | null;
  frame_source?: "provided" | "generated" | "none" | null;
  image_prompt?: string | null;
  watermark_removed?: boolean;
  dry_run?: boolean;
  elapsed_s?: number;
  reason?: string | null;
  hint?: string | null;
  account_id?: string | null;
}

// --------------------------------------------------------------------------- //
// AI Prompt Agent types (Local agy / pi CLI)
// --------------------------------------------------------------------------- //

export interface AgentSkillInfo {
  id: string;
  name: string;
  description: string;
  file_path: string;
}

export interface LocalAgentConfig {
  preferred_agent: "agy" | "pi" | string;
  agy_model: string;
  pi_model: string;
  timeout_s: number;
}

export interface GenerateNodePromptRequest {
  node_id: string;
  node_type: "image" | "video";
  upstream_media_urls?: string[];
  skill_id?: string;
  custom_hint?: string;
  is_video_continuation?: boolean;
  agent?: string;
  model?: string;
  /** Ngữ cảnh kịch bản — nếu bỏ trống, server tự đọc configs/lookbook_script.json. */
  clip_id?: string;
  clip_role?: string;
  item_id?: string;
  /** Node ảnh là ảnh sản phẩm ⇒ agent dùng skill cutout thay vì skill lookbook. */
  is_item?: boolean;
  /** Tên món — ngữ cảnh duy nhất khi node không gắn ảnh tham chiếu. */
  item_name?: string;
  /** Phạm vi cắt món: `top` | `bottom` | `full_set` | `coordinate_sheet`. Bỏ trống ⇒ skill tự chọn. */
  item_scope?: ItemScope;
  script_path?: string;
}

export interface PromptLintWarning {
  code: string;
  level: "error" | "warn";
  message: string;
  match?: string;
}

export interface GenerateNodePromptResponse {
  ok: boolean;
  node_id: string;
  prompt: string;
  skill_id: string;
  agent: string;
  upstream_files: string[];
  elapsed_s: number;
  lint?: {
    ok: boolean;
    word_count: number;
    warnings: PromptLintWarning[];
  } | null;
}

/** Một run đã sinh file, nối vào một clip trong script. */
export interface DeliveryRunRef {
  clip_id: string;
  run_id?: string;
  run_dir?: string;
  take?: number;
  prompt?: string;
  seed?: number | null;
  model?: string;
  policy_retries?: number;
  video_path?: string | null;
  plate_path?: string | null;
}

/**
 * Ảnh sản phẩm sinh từ node ảnh có cờ `is_item`.
 *
 * Không bắt buộc thuộc kịch bản: có `item_id` thì delivery dùng đúng tên `cutout` script
 * khai; chỉ có `name` thì đặt tên file theo slug của tên món (`aó kiểu nữ donna.png`
 * → `ao_kieu_nu_donna.png`).
 */
export interface DeliveryItemRef {
  name?: string;
  item_id?: string | null;
  run_id?: string;
  run_dir?: string;
  file_path?: string | null;
}

/** Một ảnh trong thư viện món đồ của project (`out/items/<project_id>/`). */
export interface LibraryItem {
  name: string;
  file: string;
  path: string;
  size_bytes: number;
}

export interface DeliveryBuildRequest {
  script_path?: string;
  script?: Record<string, unknown>;
  run_refs: DeliveryRunRef[];
  item_refs?: DeliveryItemRef[];
  dest_dir?: string;
  overwrite?: boolean;
}

export interface DeliveryListItem {
  slug: string;
  title: string | null;
  dest_dir: string;
  manifest_path: string;
  created_ts: string | null;
  canvas: { width: number; height: number; fps: number; duration_s: number; aspect: string } | null;
  summary: {
    clips_expected: number;
    clips_measured: number;
    clips_missing: string[];
    measured_total_s: number;
    has_audio: boolean;
    source_fps: number | null;
  } | null;
  warnings: number;
  missing: number;
}

export interface TestAgentResponse {
  ok: boolean;
  agent: string;
  latency_ms: number;
  message: string;
  sample_response?: string;
}



export interface AssetUploadedItem {
  id: string;
  key?: string;
  name: string;
  url: string;
  category: "image" | "video";
  created_ts: number | string;
  size_bytes?: number;
  projectId?: string | null;
  projectName?: string | null;
  isPinned?: boolean;
}

export interface AssetOutputItem {
  id: string;
  key?: string;
  name: string;
  category: "image" | "video";
  url: string;
  thumbnail_url?: string | null;
  prompt?: string;
  created_ts: number | string;
  seed?: number | null;
  resolution?: string | [number, number] | null;
  aspect_ratio?: string | null;
  duration_s?: number | null;
  size_bytes?: number;
  source?: string;
  run_id?: string | null;
  projectId?: string | null;
  projectName?: string | null;
  isPinned?: boolean;
}

// --------------------------------------------------------------------------- //
// Workspace projects (local canvas groups) — /api/workspace/*
// --------------------------------------------------------------------------- //

export interface WorkspaceViewport {
  x: number;
  y: number;
  zoom: number;
}

export interface WorkspaceEdgeState {
  id: string;
  source: string;
  target: string;
}

/**
 * The persisted canvas node, derived from the live declaration instead of restated.
 *
 * Keeping it an alias means a field added to `CanvasDrawerNode` cannot silently go unsaved — which
 * is exactly how `runId` used to be lost on reload, taking the delivery export's clip ids with it.
 */
export type CanvasNodeState = CanvasDrawerNode;

export interface CanvasGroupState {
  id: string;
  name: string;
  nodeIds: string[];
  color?: string | null;
  x?: number | null;
  y?: number | null;
  w?: number | null;
  h?: number | null;
}

export interface WorkspaceCanvasState {
  viewport: WorkspaceViewport;
  nodes: CanvasNodeState[];
  edges: WorkspaceEdgeState[];
  groups: CanvasGroupState[];
}

export interface WorkspaceProject {
  id: string;
  name: string;
  description: string;
  thumbnailUrl?: string | null;
  /** True once the user picked the preview manually (auto thumbnail disabled). */
  thumbnailManual?: boolean;
  createdAt: number;
  updatedAt: number;
  canvasState: WorkspaceCanvasState;
  flowProjects?: Record<string, string>;
  nodeCount?: number;
  assetCount?: number;
}

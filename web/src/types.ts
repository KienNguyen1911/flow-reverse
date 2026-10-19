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
}

export interface UpdateAccountPayload {
  enabled?: boolean;
  note?: string;
  cdp_port?: number;
}

export interface AccountDetail {
  account: {
    id: string;
    profile_id: string;
    cdp_port: number;
    cdp_url: string;
    enabled: boolean;
    note?: string | null;
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
  seed?: number | null;
  seed_echo?: number | null;
  resolution?: number[] | null;
  media_id?: string | null;
  created_ts?: string | null;
  elapsed_s?: number | null;
  file_bytes?: number | null;
  status?: string | null;
}

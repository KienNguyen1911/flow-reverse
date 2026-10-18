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
}

export interface Job {
  id: string;
  kind: "generate" | "dry_run" | "create_project" | "list_projects" | string;
  params: {
    project_id?: string;
    prompt?: string;
    aspect?: number;
    seed?: number | null;
    title?: string;
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

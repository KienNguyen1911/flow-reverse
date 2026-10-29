import type {
  AccountDetail,
  AddAccountPayload,
  BatchItemRequest,
  GalleryRun,
  Job,
  NodeImageRequest,
  NodeLastFrameRequest,
  NodeMediaOptions,
  NodeVideoRequest,
  PoolAccount,
  PoolInfo,
  Project,
  Status,
  TryOnRunManifest,
  UpdateAccountPayload,
  AgentSkillInfo,
  LocalAgentConfig,
  GenerateNodePromptRequest,
  GenerateNodePromptResponse,
  TestAgentResponse,
} from "./types";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = "";
    try {
      const body = await r.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail
          .map((x: any) => {
            const loc = Array.isArray(x?.loc) ? x.loc.filter((k: any) => k !== "body").join(".") : "";
            const m = x?.msg || (typeof x === "object" ? JSON.stringify(x) : String(x));
            return loc ? `${loc}: ${m}` : m;
          })
          .join("; ");
      } else if (body?.detail && typeof body.detail === "object") {
        detail = JSON.stringify(body.detail);
      } else if (body?.message) {
        detail = String(body.message);
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  return (await r.json()) as T;
}

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const api = {
  status: () => fetch("/api/status").then(j<Status>),

  projects: () => fetch("/api/projects").then(j<{ projects: Project[] }>),

  addProject: (ref: string, title?: string) =>
    post("/api/projects", { ref, title }).then(j<{ ok: boolean; id: string }>),

  removeProject: (id: string) =>
    fetch(`/api/projects/${id}`, { method: "DELETE" }).then(j<{ ok: boolean }>),

  refreshProjects: () => post("/api/projects/refresh", {}).then(j<{ job_id: string }>),

  createProject: (title: string) =>
    post("/api/projects/create", { title, confirm: true }).then(j<{ job_id: string }>),

  generate: (p: {
    project_id: string;
    prompt: string;
    aspect?: number;
    seed?: number | null;
    dry_run?: boolean;
    remove_watermark?: boolean;
    confirm?: boolean;
  }) => post("/api/generate", p).then(j<{ job_id: string }>),

  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),

  jobs: (limit = 50) => fetch(`/api/jobs?limit=${limit}`).then(j<{ jobs: Job[] }>),

  gallery: () => fetch("/api/gallery").then(j<{ runs: GalleryRun[] }>),

  clearCircuit: () => fetch("/api/circuit/clear").then(j<{ ok: boolean }>),

  // -- N-account pool (plan Task 4) ---------------------------------------- //

  pool: () => fetch("/api/pool").then(j<PoolInfo>),

  poolConfig: (p: { target_jobs_per_account?: number; max_active_browsers?: number }) =>
    post("/api/pool/config", p).then(j<{ ok: boolean; target_jobs_per_account: number; max_active_browsers: number }>),

  poolAccount: (id: string, action: "wake" | "hibernate" | "reset") =>
    post(`/api/pool/accounts/${id}/${action}`, {}).then(j<{ ok?: boolean; reason?: string; errors?: unknown[] }>),

  addPoolAccount: (p: AddAccountPayload) =>
    post("/api/pool/accounts", p).then(j<{ ok: boolean; account: PoolAccount }>),

  updatePoolAccount: (id: string, p: UpdateAccountPayload) =>
    fetch(`/api/pool/accounts/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(p),
    }).then(j<{ ok: boolean; account: PoolAccount }>),

  removePoolAccount: (id: string, deleteVault: boolean = false) =>
    fetch(`/api/pool/accounts/${id}?delete_vault=${deleteVault}`, { method: "DELETE" }).then(
      j<{ ok: boolean; removed: string }>,
    ),

  poolAccountDetail: (id: string) => fetch(`/api/pool/accounts/${id}/detail`).then(j<AccountDetail>),

  cancelJob: (id: string) =>
    post(`/api/jobs/${id}/cancel`, {}).then(j<{ ok: boolean; state?: string; cancelled?: boolean }>),

  nextPoolPort: () => fetch("/api/pool/next_port").then(j<{ next_port: number }>),

  batch: (p: {
    project_id?: string;
    items?: BatchItemRequest[];
    storyboard_path?: string;
    aspect?: number;
    dry_run?: boolean;
    remove_watermark?: boolean;
    confirm?: boolean;
    dest_dir?: string;
  }) => post("/api/batch", p).then(j<{ job_id: string }>),

  uploadReference: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/upload_reference", { method: "POST", body: fd });
    return j<{ ok: boolean; path: string; filename: string; url: string; size: number }>(r);
  },

  upload: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    return j<{ ok: boolean; path: string; filename: string; url: string; size: number }>(r);
  },

  tryonStart: (p: {
    first_frame_path?: string;
    garment_path?: string;
    transfer_image?: string;
    extra_images?: string[];
    shopee_url?: string;
    product_dir?: string;
    model_path?: string;
    project_id?: string;
    dry_run?: boolean;
    confirm?: boolean;
    auto_stitch?: boolean;
    image_prompt?: string;
    video_prompt_1?: string;
    video_prompt_2?: string;
    aspect_ratio?: string;
    remove_watermark?: boolean;
    single_video?: boolean;
    resume_run_id?: string;
    start_from_step?: number;
  }) => post("/api/tryon/start", p).then(j<{ job_id: string }>),

  tryonRuns: () => fetch("/api/tryon/runs").then(j<{ runs: TryOnRunManifest[] }>),

  // -- canvas nodes (image / video) -----------------------------------------
  nodeOptions: () => fetch("/api/node/options").then(j<NodeMediaOptions>),

  nodeImage: (p: NodeImageRequest) =>
    post("/api/node/image", p).then(
      j<{ job_id: string; kind: "image"; aspect_ratio: string; aspect: number }>,
    ),

  nodeVideo: (p: NodeVideoRequest) =>
    post("/api/node/video", p).then(
      j<{
        job_id: string;
        kind: "video";
        aspect_ratio: string;
        resolution: string;
        duration_s: number;
        frame_source: "provided" | "generated";
      }>,
    ),

  nodeLastFrame: (p: NodeLastFrameRequest) =>
    post("/api/node/last_frame", p).then(j<{ job_id: string; kind: "last_frame" }>),

  nodeFileUrl: (runId: string, filename: string) =>
    `/api/node/files/${encodeURIComponent(runId)}/${filename.split("/").map(encodeURIComponent).join("/")}`,

  // -- AI Prompt Agent (Local agy / pi) -------------------------------------
  agentSkills: () => fetch("/api/agent/skills").then(j<{ skills: AgentSkillInfo[] }>),

  agentConfig: () => fetch("/api/agent/config").then(j<LocalAgentConfig>),

  setAgentConfig: (cfg: Partial<LocalAgentConfig>) =>
    post("/api/agent/config", cfg).then(j<{ ok: boolean; config: LocalAgentConfig }>),

  testAgent: (agent?: string) =>
    post("/api/agent/test", { agent }).then(j<TestAgentResponse>),

  generateNodePrompt: (p: GenerateNodePromptRequest) =>
    post("/api/agent/generate-node-prompt", p).then(j<GenerateNodePromptResponse>),
};

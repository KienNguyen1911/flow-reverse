import type {
  AccountDetail,
  AddAccountPayload,
  GalleryRun,
  Job,
  NodeImageRequest,
  NodeLastFrameRequest,
  NodeMediaOptions,
  NodeVideoRequest,
  PoolAccount,
  PoolInfo,
  Status,
  UpdateAccountPayload,
  AgentSkillInfo,
  LocalAgentConfig,
  GenerateNodePromptRequest,
  GenerateNodePromptResponse,
  TestAgentResponse,
  AssetUploadedItem,
  AssetOutputItem,
  DeliveryBuildRequest,
  DeliveryListItem,
  LibraryItem,
  WorkspaceCanvasState,
  WorkspaceProject,
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

const patch = (url: string, body: unknown) =>
  fetch(url, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

function assetScopeQuery(projectId?: string | null, scope?: "project" | "all") {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  if (scope) params.set("scope", scope);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  status: () => fetch("/api/status").then(j<Status>),

  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),

  jobs: (limit = 50) => fetch(`/api/jobs?limit=${limit}`).then(j<{ jobs: Job[] }>),

  gallery: () => fetch("/api/gallery").then(j<{ runs: GalleryRun[] }>),

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

  upload: async (file: File, projectId?: string | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (projectId) fd.append("project_id", projectId);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    return j<{
      ok: boolean;
      path: string;
      filename: string;
      url: string;
      size: number;
      projectId?: string | null;
    }>(r);
  },

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
        frame_source: "none" | "provided" | "generated";
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

  // -- Assets Drawer --------------------------------------------------------
  assetsUploaded: (projectId?: string | null, scope: "project" | "all" = "all") =>
    fetch(`/api/assets/uploaded${assetScopeQuery(projectId, scope)}`).then(
      j<{ items: AssetUploadedItem[] }>,
    ),

  deleteUploadedAsset: (name: string) =>
    fetch(`/api/assets/uploaded/${encodeURIComponent(name)}`, { method: "DELETE" }).then(j<{ ok: boolean }>),

  assetsOutputs: (projectId?: string | null, scope: "project" | "all" = "all") =>
    fetch(`/api/assets/output${assetScopeQuery(projectId, scope)}`).then(
      j<{ items: AssetOutputItem[] }>,
    ),

  pinAsset: (p: { key: string; kind?: string; isPinned: boolean }) =>
    post("/api/assets/pin", p).then(j<{ ok: boolean; key: string; isPinned: boolean }>),

  /** Thư viện ảnh sản phẩm của project (`out/items/<project_id>/`) — không phụ thuộc script. */
  itemLibrary: (projectId?: string | null) =>
    fetch(`/api/items/library${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`).then(
      j<{ project_id: string | null; dir: string; items: LibraryItem[] }>,
    ),

  // -- Deliveries (bộ nguyên liệu cho HyperFrames desktop) -------------------
  createDelivery: (p: DeliveryBuildRequest) =>
    post("/api/deliveries", p).then(
      j<{ job_id: string; kind: "delivery_build"; slug: string; dest_dir: string }>,
    ),

  deliveries: () => fetch("/api/deliveries").then(j<{ deliveries: DeliveryListItem[] }>),

  deliveryFileUrl: (slug: string, relPath: string) =>
    `/api/deliveries/${encodeURIComponent(slug)}/${relPath
      .split("/")
      .map(encodeURIComponent)
      .join("/")}`,

  // -- Workspace projects (local canvas groups) ------------------------------
  workspaceProjects: () =>
    fetch("/api/workspace/projects").then(
      j<{ projects: WorkspaceProject[]; legacyMigrated?: boolean }>,
    ),

  createWorkspaceProject: (p: {
    name: string;
    description?: string;
    canvasState?: WorkspaceCanvasState;
  }) =>
    post("/api/workspace/projects", p).then(
      j<{ ok: boolean; project: WorkspaceProject }>,
    ),

  updateWorkspaceProject: (
    id: string,
    p: {
      name?: string;
      description?: string;
      thumbnailUrl?: string | null;
      canvasState?: WorkspaceCanvasState;
    },
  ) =>
    patch(`/api/workspace/projects/${encodeURIComponent(id)}`, p).then(
      j<{ ok: boolean; project: WorkspaceProject | null }>,
    ),

  deleteWorkspaceProject: (id: string) =>
    fetch(`/api/workspace/projects/${encodeURIComponent(id)}`, { method: "DELETE" }).then(
      j<{ ok: boolean; removed: string }>,
    ),

  duplicateWorkspaceProject: (id: string, name?: string) =>
    post(`/api/workspace/projects/${encodeURIComponent(id)}/duplicate`, { name }).then(
      j<{ ok: boolean; project: WorkspaceProject }>,
    ),

  setWorkspaceThumbnail: (id: string, thumbnailUrl: string | null) =>
    fetch(`/api/workspace/projects/${encodeURIComponent(id)}/thumbnail`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ thumbnailUrl }),
    }).then(
      j<{ ok: boolean; project: WorkspaceProject; thumbnailUrl: string | null; thumbnailManual: boolean }>,
    ),

  saveWorkspaceCanvas: (id: string, canvasState: WorkspaceCanvasState) =>
    fetch(`/api/workspace/projects/${encodeURIComponent(id)}/canvas`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(canvasState),
    }).then(j<{ ok: boolean; projectId: string; updatedAt: number | null }>),

  /** Fire-and-forget save used on pagehide/unload so no edits are lost. */
  saveWorkspaceCanvasBeacon: (id: string, canvasState: WorkspaceCanvasState) => {
    try {
      const body = JSON.stringify(canvasState);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon(`/api/workspace/projects/${encodeURIComponent(id)}/canvas`, blob);
        return;
      }
      void fetch(`/api/workspace/projects/${encodeURIComponent(id)}/canvas`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body,
        keepalive: true,
      });
    } catch {
      /* best effort */
    }
  },

  migrateWorkspace: (p: {
    name?: string;
    canvasState?: WorkspaceCanvasState | null;
    pinnedIds?: string[];
  }) =>
    post("/api/workspace/migrate", p).then(
      j<{
        ok: boolean;
        created: boolean;
        canvasImported?: boolean;
        claimed: number;
        project: WorkspaceProject;
      }>,
    ),
};

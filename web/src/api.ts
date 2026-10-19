import type {
  AccountDetail,
  AddAccountPayload,
  BatchItemRequest,
  GalleryRun,
  Job,
  PoolAccount,
  PoolInfo,
  Project,
  Status,
  UpdateAccountPayload,
} from "./types";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = "";
    try {
      const body = await r.json();
      detail = String(body?.detail ?? "");
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
    confirm?: boolean;
  }) => post("/api/generate", p).then(j<{ job_id: string }>),

  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),

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

  nextPoolPort: () => fetch("/api/pool/next_port").then(j<{ next_port: number }>),

  batch: (p: {
    project_id?: string;
    items?: BatchItemRequest[];
    storyboard_path?: string;
    aspect?: number;
    dry_run?: boolean;
    confirm?: boolean;
    dest_dir?: string;
  }) => post("/api/batch", p).then(j<{ job_id: string }>),

  uploadReference: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/upload_reference", { method: "POST", body: fd });
    return j<{ ok: boolean; path: string; filename: string; url: string; size: number }>(r);
  },
};

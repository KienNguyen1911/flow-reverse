import type { GalleryRun, Job, Project, Status } from "./types";

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
};

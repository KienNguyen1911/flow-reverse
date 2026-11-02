import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type {
  GalleryRun,
  Job,
  NodeMediaOptions,
  PoolInfo,
  Project,
  ScriptClipOption,
  Status,
  TryOnRunManifest,
  AssetUploadedItem,
  AssetOutputItem,
  WorkspaceProject,
} from "./types";

const TERMINAL: ReadonlySet<string> = new Set(["succeeded", "failed", "rejected"]);

/** Fallback khi chưa gọi được `/api/node/options` — khớp default trong
 *  `src/Workflows/limits.py`. Chỉ là lưới an toàn cho UI, không phải nguồn chân lý. */
export const FALLBACK_LIMITS = { max_prompt_chars: 7200, max_batch_items: 300 } as const;

export interface Limits {
  max_prompt_chars: number;
  max_batch_items: number;
}

// Nhiều component cùng cần limits ⇒ giữ một promise dùng chung, chỉ fetch 1 lần.
let limitsPromise: Promise<Limits> | null = null;
//: Cache riêng cho danh sách clip của kịch bản: cùng endpoint, nhưng component khác tiêu thụ.
let nodeOptionsPromise: Promise<NodeMediaOptions | null> | null = null;

function fetchNodeOptions(): Promise<NodeMediaOptions | null> {
  if (!nodeOptionsPromise) {
    nodeOptionsPromise = api
      .nodeOptions()
      .catch(() => {
        nodeOptionsPromise = null;
        return null;
      });
  }
  return nodeOptionsPromise;
}

/**
 * Clip của kịch bản Lookbook, cho ô chọn trên node video.
 *
 * Trả `[]` khi chưa tải xong hoặc backend không có script — node ảnh và project chưa gắn kịch bản
 * vẫn dùng component này nên UI phải chịu được cả hai.
 */
export function useScriptClips(): ScriptClipOption[] {
  const [clips, setClips] = useState<ScriptClipOption[]>([]);
  useEffect(() => {
    let stop = false;
    fetchNodeOptions()
      .then((o) => {
        if (!stop && o?.script?.clips) setClips(o.script.clips);
      })
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, []);
  return clips;
}

/**
 * Toàn bộ option của composer Flow (ảnh + video + agent) do backend công bố.
 *
 * Nguồn duy nhất là `GET /api/node/options` → `src/Workflows/flow_catalog.py`.
 * UI **không được** hard-code tỷ lệ/model/số lượng: mỗi khoá là một giá trị đã capture
 * 0-credit từ composer thật, đoán sai là mất credit.
 */
export function useNodeOptions(): NodeMediaOptions | null {
  const [opts, setOpts] = useState<NodeMediaOptions | null>(null);
  useEffect(() => {
    let stop = false;
    fetchNodeOptions()
      .then((o) => {
        if (!stop) setOpts(o);
      })
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, []);
  return opts;
}

function fetchLimits(): Promise<Limits> {
  if (!limitsPromise) {
    limitsPromise = api
      .nodeOptions()
      .then((o) => ({
        max_prompt_chars: o.limits?.max_prompt_chars ?? FALLBACK_LIMITS.max_prompt_chars,
        max_batch_items: o.limits?.max_batch_items ?? FALLBACK_LIMITS.max_batch_items,
      }))
      .catch(() => {
        // Cho phép thử lại ở lần mount sau (server có thể chưa lên).
        limitsPromise = null;
        return { ...FALLBACK_LIMITS };
      });
  }
  return limitsPromise;
}

/** Validation caps do backend công bố (nguồn duy nhất: `src/Workflows/limits.py`). */
export function useLimits(): Limits {
  const [limits, setLimits] = useState<Limits>({ ...FALLBACK_LIMITS });
  useEffect(() => {
    let stop = false;
    fetchLimits()
      .then((l) => {
        if (!stop) setLimits(l);
      })
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, []);
  return limits;
}


/** Poll bridge status every `intervalMs`. */
export function useStatus(intervalMs = 5000) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tick = async () => {
    try {
      setStatus(await api.status());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    let stop = false;
    const run = async () => {
      if (stop) return;
      await tick();
    };
    run();
    const t = window.setInterval(run, intervalMs);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);

  return { status, error, refresh: tick };
}

/** Poll the N-account pool (active working set vs standby) every `intervalMs`. */
export function usePool(intervalMs = 4000) {
  const [pool, setPool] = useState<PoolInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tick = async () => {
    try {
      setPool(await api.pool());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    let stop = false;
    const run = async () => {
      if (stop) return;
      await tick();
    };
    run();
    const t = window.setInterval(run, intervalMs);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);

  return { pool, error, refresh: tick };
}

/** Poll one job until it reaches a terminal state. */
export function useJob(activeJobId: string | null, onTerminal?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  useEffect(() => {
    if (!activeJobId) return;
    let stop = false;
    let timer: number | undefined;
    let fired = false;

    const tick = async () => {
      try {
        const j = await api.job(activeJobId);
        if (stop) return;
        setJob(j);
        if (TERMINAL.has(j.state)) {
          if (timer) window.clearInterval(timer);
          if (!fired) {
            fired = true;
            onTerminalRef.current?.(j);
          }
        }
      } catch {
        /* transient fetch error; keep polling */
      }
    };

    setJob(null);
    tick();
    timer = window.setInterval(tick, 800);
    return () => {
      stop = true;
      if (timer) window.clearInterval(timer);
    };
  }, [activeJobId]);

  return job;
}

/** Poll list of jobs periodically. */
export function useJobs(intervalMs = 3000) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const res = await api.jobs(50);
      setJobs(res.jobs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let stop = false;
    const run = async () => {
      if (stop) return;
      await refresh();
    };
    run();
    const t = window.setInterval(run, intervalMs);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
  }, [intervalMs]);

  return { jobs, loading, error, refresh };
}

/** Project registry. */
export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.projects();
      setProjects(r.projects);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { projects, loading, error, refresh };
}

/** Workspace projects: local canvas groups with their persisted state. */
export function useWorkspaceProjects() {
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await api.workspaceProjects();
      setProjects(r.projects);
      setError(null);
      return r.projects;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { projects, setProjects, loading, error, refresh };
}

/** Gallery of finished runs. */
export function useGallery() {
  const [runs, setRuns] = useState<GalleryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const r = await api.gallery();
      setRuns(r.runs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { runs, loading, error, refresh };
}

/** History of try-on video runs. */
export function useTryOnRuns() {
  const [runs, setRuns] = useState<TryOnRunManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const r = await api.tryonRuns();
      setRuns(r.runs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  return { runs, loading, error, refresh };
}


/** Assets hook: fetches uploaded and output assets scoped to a workspace project. */
export function useAssets(
  projectId: string | null = null,
  scope: "project" | "all" = "project",
) {
  const [uploaded, setUploaded] = useState<AssetUploadedItem[]>([]);
  const [outputs, setOutputs] = useState<AssetOutputItem[]>([]);
  const [loadingUploaded, setLoadingUploaded] = useState(false);
  const [loadingOutputs, setLoadingOutputs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scopeRef = useRef({ projectId, scope });
  scopeRef.current = { projectId, scope };

  const refreshUploaded = useCallback(async () => {
    const { projectId: pid, scope: sc } = scopeRef.current;
    setLoadingUploaded(true);
    try {
      const res = await api.assetsUploaded(pid, sc);
      setUploaded(res.items || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingUploaded(false);
    }
  }, []);

  const refreshOutputs = useCallback(async () => {
    const { projectId: pid, scope: sc } = scopeRef.current;
    setLoadingOutputs(true);
    try {
      const res = await api.assetsOutputs(pid, sc);
      setOutputs(res.items || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingOutputs(false);
    }
  }, []);

  const refreshAll = useCallback(() => {
    void refreshUploaded();
    void refreshOutputs();
  }, [refreshUploaded, refreshOutputs]);

  useEffect(() => {
    refreshAll();
  }, [projectId, scope, refreshAll]);

  /** Optimistically toggle a pin and persist it server-side. */
  const setPinned = useCallback(
    async (item: AssetUploadedItem | AssetOutputItem, pinned: boolean, kind?: string) => {
      const resolvedKind: string =
        kind ||
        (item.key?.startsWith("gallery:")
          ? "gallery"
          : item.key?.startsWith("output:") || (item as AssetOutputItem).run_id
            ? "output"
            : "upload");
      const runId = (item as AssetOutputItem).run_id;
      const key =
        item.key ||
        (resolvedKind === "output" && runId
          ? `output:${runId}`
          : resolvedKind === "gallery" && runId
            ? `gallery:${runId}`
            : `${resolvedKind}:${item.id}`);
      const matches = (it: AssetUploadedItem | AssetOutputItem) =>
        it.key === key || it.id === item.id;
      setUploaded((list) => list.map((it) => (matches(it) ? { ...it, isPinned: pinned } : it)));
      setOutputs((list) => list.map((it) => (matches(it) ? { ...it, isPinned: pinned } : it)));
      try {
        await api.pinAsset({ key, kind: resolvedKind, isPinned: pinned });
        // Pinned items stay visible across projects; refresh so scope filters agree.
        if (scopeRef.current.scope === "project") refreshAll();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        refreshAll();
      }
    },
    [refreshAll],
  );

  return {
    uploaded,
    outputs,
    loadingUploaded,
    loadingOutputs,
    error,
    refreshUploaded,
    refreshOutputs,
    refreshAll,
    setPinned,
  };
}

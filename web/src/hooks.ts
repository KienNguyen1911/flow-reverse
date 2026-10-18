import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { GalleryRun, Job, Project, Status } from "./types";

const TERMINAL: ReadonlySet<string> = new Set(["succeeded", "failed", "rejected"]);

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

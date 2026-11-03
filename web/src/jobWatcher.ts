import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { isTerminal, JOB_POLL_MS, sleep, waitForJob as waitForJobPure } from "./jobLifecycle";
import type { WaitForJobOptions } from "./jobLifecycle";
import type { Job } from "./types";

/**
 * React bindings for the job lifecycle. The lifecycle itself (terminal states, `waitForJob`) lives
 * in `jobLifecycle.ts`; this file only adapts it to the API client and to hooks.
 */

export { JOB_POLL_MS, JOB_TIMEOUT_MS, TERMINAL_STATES, isTerminal, sleep } from "./jobLifecycle";

/**
 * Wait for a job to finish. Wraps `jobLifecycle.waitForJob` with the real API call.
 *
 * Returns the terminal job; a `failed`/`rejected` job is returned, not thrown — callers that care
 * check `job.state`.
 */
export function waitForJob(
  jobId: string,
  opts: Omit<WaitForJobOptions<Job>, "fetchJob"> = {},
): Promise<Job> {
  return waitForJobPure<Job>({ ...opts, fetchJob: () => api.job(jobId) });
}

/**
 * Poll one job until it reaches a terminal state, for rendering.
 *
 * `onTerminal` fires at most once per `activeJobId`. Transient fetch errors are swallowed and the
 * poll continues — a dropped request is not evidence that the job died.
 */
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
        if (isTerminal(j.state)) {
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
    timer = window.setInterval(tick, JOB_POLL_MS);
    return () => {
      stop = true;
      if (timer) window.clearInterval(timer);
    };
  }, [activeJobId]);

  return job;
}

/** Poll a list of jobs periodically. */
export function useJobs(intervalMs = 3000) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshRef = useRef<() => Promise<void>>(undefined);
  if (!refreshRef.current) {
    refreshRef.current = async () => {
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
  }
  const refresh = refreshRef.current;

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
  }, [intervalMs, refresh]);

  return { jobs, loading, error, refresh };
}

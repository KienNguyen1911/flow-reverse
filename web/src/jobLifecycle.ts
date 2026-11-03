/**
 * The job lifecycle, pure and dependency-free.
 *
 * This module is the single place that knows what "finished" means and how to wait for it.
 * Everything else — the node runner, the drawer, the delivery modal, the job lists — imports from
 * here, because a second copy of `["succeeded","failed","rejected"]` is a second thing to forget.
 *
 * It has no runtime imports at all: the transport is injected as `fetchJob`. That keeps it
 * testable with `node --test` (see `jobLifecycle.test.mjs`) and stops the React tree and the network
 * from being a prerequisite for checking a lifecycle rule.
 */

/** States after which a job will not change again. */
export const TERMINAL_STATES: readonly string[] = ["succeeded", "failed", "rejected"];

const TERMINAL_SET: ReadonlySet<string> = new Set(TERMINAL_STATES);

/** True once the job has reached a state it cannot leave. */
export function isTerminal(state: string | undefined | null): boolean {
  return state != null && TERMINAL_SET.has(state);
}

/** Default cadence for a single job: live enough to feel responsive, slow enough not to spam. */
export const JOB_POLL_MS = 800;

/** Default ceiling for `waitForJob`. A job still running after this is treated as stuck. */
export const JOB_TIMEOUT_MS = 10 * 60 * 1000;

/** The smallest thing `waitForJob` needs from a job: a state, and maybe a reason. */
export interface JobLike {
  state: string;
  error?: string | null;
}

export interface WaitForJobOptions<T extends JobLike> {
  /** How to ask for the job. Injected so this module never imports the API client. */
  fetchJob: () => Promise<T>;
  /** How often to re-ask. */
  intervalMs?: number;
  /** Give up after this long. `0` disables the limit (not recommended in a UI path). */
  timeoutMs?: number;
  /** Checked before every poll and before sleeping; aborting stops the wait. */
  signal?: AbortSignal;
  /** Called on every observed state, including the terminal one. */
  onState?: (job: T) => void;
  /** Injectable sleep, so tests do not wait in real time. */
  sleepFn?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Injectable clock, for the timeout test. */
  nowFn?: () => number;
}

/**
 * Resolve once the job reaches a terminal state, returning that final job.
 *
 * A job that ends `failed` or `rejected` is a *result*, not an exception — the caller usually wants
 * to render the reason. So this only rejects on timeout or abort; callers that treat failure as an
 * error check `job.state` themselves.
 *
 * This replaces the `for (;;) { ...; await sleep(n) }` that used to live in click handlers: that
 * pattern pinned the handler open for the whole job and could not be cancelled.
 */
export async function waitForJob<T extends JobLike>(
  opts: WaitForJobOptions<T>,
): Promise<T> {
  const {
    fetchJob,
    intervalMs = JOB_POLL_MS,
    timeoutMs = JOB_TIMEOUT_MS,
    signal,
    onState,
    sleepFn = sleep,
    nowFn = Date.now,
  } = opts;
  const started = nowFn();
  let lastError: unknown = null;

  for (;;) {
    if (signal?.aborted) throw abortError();

    try {
      const job = await fetchJob();
      lastError = null;
      onState?.(job);
      if (isTerminal(job.state)) return job;
    } catch (e) {
      // A failed fetch is not a failed job: the job may still be running, so remember the error
      // and keep polling. Only the timeout below ends the wait.
      lastError = e;
    }

    if (timeoutMs > 0 && nowFn() - started > timeoutMs) {
      const reason = lastError instanceof Error ? ` (last error: ${lastError.message})` : "";
      throw new Error(`job chưa xong sau ${Math.round(timeoutMs / 1000)}s${reason}`);
    }

    await sleepFn(intervalMs, signal);
  }
}

/** Abortable delay. Rejects with a `DOMException` named `AbortError`. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function abortError(): DOMException {
  return new DOMException("aborted", "AbortError");
}

/**
 * Behaviour tests for the job lifecycle.
 *
 * These are the frontend's first tests. `jobLifecycle.ts` has no runtime imports and takes the
 * transport as `fetchJob`, so a 10-minute poll loop is exercised here in milliseconds.
 *
 * Run with:  node --test web/src/jobLifecycle.test.mjs
 * (after `cd web && npx tsc -p tsconfig.test.json`, which emits `.test-dist/jobLifecycle.js`)
 */
import assert from "node:assert/strict";
import test from "node:test";

import { isTerminal, JOB_POLL_MS, sleep, TERMINAL_STATES, waitForJob } from "../../.test-dist/jobLifecycle.js";

const job = (state) => ({ id: "j1", state });

/** Build a fake fetch that walks a script of states, repeating the last one. */
function scripted(states, { onCall } = {}) {
  let i = 0;
  return {
    calls: () => i,
    fetchJob: async () => {
      const state = states[Math.min(i, states.length - 1)];
      i += 1;
      onCall?.(state, i);
      return job(state);
    },
  };
}

const noSleep = async () => {};

test("terminal states are the three that cannot change again", () => {
  assert.deepEqual([...TERMINAL_STATES], ["succeeded", "failed", "rejected"]);
  for (const s of TERMINAL_STATES) assert.equal(isTerminal(s), true, s);
});

test("non-terminal states are not terminal", () => {
  for (const s of ["queued", "running"]) assert.equal(isTerminal(s), false, s);
});

test("null and undefined are not terminal", () => {
  assert.equal(isTerminal(null), false);
  assert.equal(isTerminal(undefined), false);
});

test("default cadence is the documented 800ms", () => {
  assert.equal(JOB_POLL_MS, 800);
});

test("resolves with the job once it succeeds", async () => {
  const fake = scripted(["queued", "running", "succeeded"]);
  const final = await waitForJob({ fetchJob: fake.fetchJob, sleepFn: noSleep });
  assert.equal(final.state, "succeeded");
  assert.equal(fake.calls(), 3);
});

test("returns a failed job instead of throwing", async () => {
  // The caller needs the reason to render it, so failure is a result, not an exception.
  const fake = scripted(["running", "failed"]);
  const final = await waitForJob({ fetchJob: fake.fetchJob, sleepFn: noSleep });
  assert.equal(final.state, "failed");
});

test("stops polling right after a terminal state", async () => {
  const fake = scripted(["succeeded", "running"]);
  await waitForJob({ fetchJob: fake.fetchJob, sleepFn: noSleep });
  assert.equal(fake.calls(), 1, "must not poll again after terminal");
});

test("reports every state it observes", async () => {
  const seen = [];
  const fake = scripted(["queued", "running", "succeeded"]);
  await waitForJob({
    fetchJob: fake.fetchJob,
    sleepFn: noSleep,
    onState: (j) => seen.push(j.state),
  });
  assert.deepEqual(seen, ["queued", "running", "succeeded"]);
});

test("a dropped request does not end the wait", async () => {
  let call = 0;
  const fetchJob = async () => {
    call += 1;
    if (call === 1) throw new Error("network down");
    return job("succeeded");
  };
  const final = await waitForJob({ fetchJob, sleepFn: noSleep });
  assert.equal(final.state, "succeeded");
  assert.equal(call, 2);
});

test("rejects on timeout and says why", async () => {
  const fetchJob = async () => job("running");
  let clock = 0;
  await assert.rejects(
    () =>
      waitForJob({
        fetchJob,
        sleepFn: noSleep,
        timeoutMs: 1000,
        nowFn: () => (clock += 60_000),
      }),
    /chưa xong sau 1s/,
  );
});

test("rejects immediately when the signal is already aborted", async () => {
  const ctrl = new AbortController();
  ctrl.abort();
  await assert.rejects(() => waitForJob({ fetchJob: async () => job("succeeded"), signal: ctrl.signal }), {
    name: "AbortError",
  });
});

test("aborting mid-wait stops the loop", async () => {
  const ctrl = new AbortController();
  const fetchJob = async () => {
    ctrl.abort();
    return job("running");
  };
  await assert.rejects(() => waitForJob({ fetchJob, signal: ctrl.signal }), {
    name: "AbortError",
  });
});

test("sleep rejects with AbortError when aborted", async () => {
  const ctrl = new AbortController();
  const p = sleep(10_000, ctrl.signal);
  ctrl.abort();
  await assert.rejects(() => p, { name: "AbortError" });
});

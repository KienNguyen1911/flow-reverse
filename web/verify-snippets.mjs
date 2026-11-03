/**
 * Guard against the API docs drifting from the code they document.
 *
 * The catalogue used to hardcode the base URL, the terminal job states and the poll cadence.
 * They are now interpolated from `jobLifecycle.ts` and `api-docs/base.ts`, and this asserts that
 * interpolation still renders exactly the text that was hardcoded before the refactor — so a
 * change to a state name or the port shows up here instead of being quietly published.
 *
 * Run from `web/`:  node verify-snippets.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const LIFECYCLE = readFileSync(join(here, "src/jobLifecycle.ts"), "utf8");
const TERMINAL_STATES = [
  ...LIFECYCLE.match(/TERMINAL_STATES[^=]*=\s*\[([^\]]*)\]/)[1].matchAll(/"([a-z]+)"/g),
].map((m) => m[1]);
const JOB_POLL_MS = Number(LIFECYCLE.match(/JOB_POLL_MS = (\d+)/)[1]);
const BASE = readFileSync(join(here, "src/components/api-docs/base.ts"), "utf8").match(
  /export const BASE = "([^"]+)"/,
)[1];

// The text the docs must show. These are the literals the panel hardcoded before the split, kept
// here as the contract: the modules now interpolate them, and this proves the output is unchanged.
const EXPECTED = {
  baseLine: 'BASE = "http://127.0.0.1:4000"',
  stateNote: "state nhận các giá trị: queued, running, succeeded, failed, rejected.",
  pollNote: "Frontend poll mỗi 800ms, script bên ngoài nên poll cách 1 đến 2 giây.",
};

console.log("TERMINAL_STATES:", TERMINAL_STATES, "JOB_POLL_MS:", JOB_POLL_MS, "BASE:", BASE);

const checks = [
  {
    name: "python quickstart BASE line",
    original: EXPECTED.baseLine,
    rendered: `BASE = "${BASE}"`,
  },
  {
    name: "catalog state note",
    original: EXPECTED.stateNote,
    rendered: `state nhận các giá trị: queued, running, ${TERMINAL_STATES.join(", ")}.`,
  },
  {
    name: "catalog poll note",
    original: EXPECTED.pollNote,
    rendered: `Frontend poll mỗi ${JOB_POLL_MS}ms, script bên ngoài nên poll cách 1 đến 2 giây.`,
  },
];

let ok = true;
for (const c of checks) {
  const same = c.original === c.rendered;
  ok &&= same;
  console.log(`${same ? "OK  " : "DIFF"} ${c.name}`);
  if (!same) {
    console.log("  original:", JSON.stringify(c.original));
    console.log("  rendered:", JSON.stringify(c.rendered));
  }
}
process.exit(ok ? 0 : 1);

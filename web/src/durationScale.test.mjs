/**
 * Duration-slider arithmetic tests.
 *
 * Run with:  cd web && npx tsc -p tsconfig.test.json && node --test src/durationScale.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import { LAST_FRAME_MAX_DURATION_S, durationScale } from "../../.test-dist/durationScale.js";

const OMNI12 = Array.from({ length: 13 }, (_, i) => i + 3); // 3..15

test("uncapped scale exposes the whole 3..15 range", () => {
  const s = durationScale(OMNI12, 8);
  assert.deepEqual(s.stops, OMNI12);
  assert.equal(s.current, 8);
  assert.equal(s.index, 5); // stop 5 of 13
  assert.equal(s.capped, false);
});

test("last frame caps the scale at 10s and reports the cap", () => {
  const s = durationScale(OMNI12, 8, LAST_FRAME_MAX_DURATION_S);
  assert.deepEqual(s.stops, [3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(s.current, 8);
  assert.equal(s.capped, true, "UI needs to know a ceiling was applied");
});

test("a value above the cap clamps to the cap instead of erroring", () => {
  // The composer clamps; a stale 15s node must not break the control.
  const s = durationScale(OMNI12, 15, LAST_FRAME_MAX_DURATION_S);
  assert.equal(s.current, LAST_FRAME_MAX_DURATION_S);
  assert.equal(s.stops[s.index], LAST_FRAME_MAX_DURATION_S);
});

test("values snap to the nearest stop, so the thumb is never between two", () => {
  // Veo offers a single 8s stop; anything else must land on it.
  assert.equal(durationScale([8], 5).current, 8);
  assert.equal(durationScale([8], 12).current, 8);
  // Non-contiguous lists pick the closer neighbour (4 is equidistant -> first wins).
  assert.equal(durationScale([4, 6, 8, 10], 9).current, 8);
  assert.equal(durationScale([4, 6, 8, 10], 7).current, 6); // nearer to 6 than 8
});

test("an empty option list still yields one usable stop", () => {
  const s = durationScale([], 7, LAST_FRAME_MAX_DURATION_S);
  assert.deepEqual(s.stops, [7]);
  assert.equal(s.current, 7);
  assert.equal(s.index, 0);
});

test("stops are sorted, so option order cannot scramble the slider", () => {
  const s = durationScale([15, 3, 10, 5], 5);
  assert.deepEqual(s.stops, [3, 5, 10, 15]);
  assert.equal(s.current, 5);
  assert.equal(s.index, 1);
});

test("LAST_FRAME_MAX_DURATION_S mirrors the bridge constant", () => {
  // src/Bridge/flow_video/constants.py: OMNI12_MAX_DURATION_S_WITH_LAST_FRAME = 10
  assert.equal(LAST_FRAME_MAX_DURATION_S, 10);
});

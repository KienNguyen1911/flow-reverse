/**
 * Duration-slider arithmetic, pure and dependency-free.
 *
 * Flow's own `flow-duration-slider` has a continuous 3..15s range, and it silently lowers its
 * maximum to 10s once both frame slots are filled. The UI has to reproduce both facts, and
 * getting either wrong either misrepresents the composer or offers a length the server will
 * reject. Keeping the arithmetic here (rather than inline in the component) means the cap and
 * the snap-to-stop rules can be tested without rendering React — same reason
 * `jobLifecycle.ts` exists.
 */

/** Ceiling Flow applies when a last frame ("Kết thúc") is attached. */
export const LAST_FRAME_MAX_DURATION_S = 10;

export interface DurationScale {
  /** Selectable seconds, ascending, already capped. */
  stops: number[];
  /** Index of the selected stop. */
  index: number;
  /** The selected seconds (snapped to a stop). */
  current: number;
  /** True when a cap actually removed values the model otherwise offers. */
  capped: boolean;
}

/**
 * Resolve a requested duration against the model's options and the current cap.
 *
 * `value` is snapped to the nearest stop so a stale node value (e.g. 15s left over from
 * before a last frame was attached) cannot leave the thumb between two stops. A value above
 * the cap clamps to the cap instead of being rejected, which is what the composer does.
 */
export function durationScale(
  options: readonly number[],
  value: number,
  maxAllowed: number = Infinity,
): DurationScale {
  const all = options.length ? [...options].sort((a, b) => a - b) : [value];
  const stops = all.filter((d) => d <= maxAllowed);
  const usable = stops.length ? stops : [Math.min(value, maxAllowed)];

  const capped = all.some((d) => d > maxAllowed);
  const target = Math.min(value, maxAllowed);

  let index = 0;
  for (let i = 0; i < usable.length; i += 1) {
    if (Math.abs(usable[i] - target) < Math.abs(usable[index] - target)) index = i;
  }
  return { stops: usable, index, current: usable[index], capped };
}

import { useId } from "react";
import { durationScale } from "../durationScale";

interface Props {
  /** Values the current model offers, ascending. */
  options: number[];
  /** Currently selected seconds. */
  value: number;
  /**
   * Highest value the composer will accept right now (Flow lowers it to 10s when both
   * frame slots are filled). Values above this are shown as unavailable rather than hidden,
   * so the user can see the cap instead of wondering where 15s went.
   */
  maxAllowed?: number;
  /** False when the model fixes the duration (Veo) — the control is then a read-out. */
  enabled?: boolean;
  /**
   * True when a video reference is attached. `jIps6` / `abra_edit` takes the clip's own
   * length, so the selected value is not sent; the control stays usable but says so.
   */
  clipLengthOverrides?: boolean;
  onChange: (seconds: number) => void;
  label?: string;
}

/**
 * Duration as a slider, mirroring Flow's own `flow-duration-slider`.
 *
 * The real composer exposes a continuous 3..15s range whose value is `seconds - 3`, so a
 * slider is the honest control: a dropdown would suggest discrete 4/6/8/10 chips that
 * Omni 1.2 no longer has. The index maps position in `options`, which keeps the control
 * correct even if the catalog's list is not contiguous.
 */
export function DurationSlider({
  options,
  value,
  maxAllowed,
  enabled = true,
  clipLengthOverrides = false,
  onChange,
  label = "Thời lượng",
}: Props) {
  const id = useId();
  const { stops, index, current, capped } = durationScale(options, value, maxAllowed);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-[10px] text-mut">
          {label}
        </label>
        <output
          htmlFor={id}
          className="font-mono text-[11.5px] font-semibold text-fg tabular-nums"
        >
          {current}s
        </output>
      </div>

      <input
        id={id}
        type="range"
        min={0}
        max={Math.max(0, stops.length - 1)}
        step={1}
        value={index}
        disabled={!enabled || stops.length < 2}
        onChange={(e) => {
          const next = stops[Number(e.target.value)];
          if (next !== undefined) onChange(next);
        }}
        aria-valuetext={`${current} giây`}
        title={
          enabled
            ? capped
              ? `Trần hiện tại là ${stops[stops.length - 1]}s`
              : "Kéo để chọn độ dài video"
            : `${label} do model quyết định (${current}s)`
        }
        className="duration-range h-1.5 w-full cursor-pointer disabled:cursor-not-allowed disabled:opacity-45"
      />

      <div className="flex justify-between font-mono text-[9.5px] text-mut tabular-nums">
        <span>{stops[0] ?? current}s</span>
        <span>{stops[stops.length - 1] ?? current}s</span>
      </div>

      {capped ? (
        <p className="text-[10px] leading-snug text-warn">
          Trần {stops[stops.length - 1]}s: Flow hạ max slider khi đã có khung “Kết thúc”.
        </p>
      ) : null}
      {clipLengthOverrides ? (
        <p className="text-[10px] leading-snug text-mut">
          Có clip tham chiếu: độ dài thật lấy từ clip (RPC <code>jIps6</code>), giá trị này bị bỏ
          qua.
        </p>
      ) : null}
    </div>
  );
}

export default DurationSlider;

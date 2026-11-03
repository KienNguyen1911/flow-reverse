import type { CanvasNode } from "../types";
import { sourceLabel, type NodeSources } from "./nodeSources";

/** Last-frame node: pick the source video and whether to strip the Flow watermark. */
export function LastFrameNodeBody({
  n,
  sources,
  onSourceChange,
  onFieldChange,
}: {
  n: CanvasNode;
  sources: NodeSources;
  onSourceChange: (sid: string) => void;
  onFieldChange: (patch: Partial<CanvasNode>) => void;
}) {
  const { sourceOptions, upstream, sourceBlocked } = sources;
  return (
    <>
      <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-mut">Video nguồn (input)</span>
          <select
            value={n.sourceImageId ?? ""}
            onChange={(e) => onSourceChange(e.target.value)}
            className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
          >
            <option value="">Chưa chọn (bấm chấm hoặc chọn)</option>
            {sourceOptions.map((i) => (
              <option key={i.id} value={i.id}>
                {sourceLabel(i)}
              </option>
            ))}
          </select>
        </label>

        {upstream && (
          <div className="rounded-ctl border border-line2 bg-panel2 p-2 flex items-center justify-between text-[10px]">
            <span className="text-dim truncate">
              {upstream.videoUrl ? "✓ Video nguồn sẵn sàng" : "Video nguồn chưa hoàn tất"}
            </span>
            <span className="font-mono text-mut">{upstream.id}</span>
          </div>
        )}

        {sourceBlocked && (
          <p className="text-[10px] text-warn leading-snug">
            Node video nguồn chưa có video hoàn tất — hãy chạy video nguồn trước.
          </p>
        )}
      </div>

      <label className="flex items-center gap-1.5 cursor-pointer text-[10.5px] text-dim hover:text-fg pt-1">
        <input
          type="checkbox"
          checked={n.removeWatermark ?? true}
          onChange={(e) => onFieldChange({ removeWatermark: e.target.checked })}
          className="rounded border-line2 text-acc focus:ring-0"
        />
        <span>Tự động xóa watermark Flow</span>
      </label>
    </>
  );
}

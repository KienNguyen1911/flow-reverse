import type { NodeMediaOptions } from "../../types";
import { LAST_FRAME_MAX_DURATION_S } from "../../durationScale";
import { DurationSlider } from "../DurationSlider";
import type { CanvasDrawerNode } from "./types";

/**
 * Giữ giá trị hiện tại của node kể cả khi danh sách option chưa tải xong.
 *
 * Danh sách thật LUÔN đến từ `GET /api/node/options` (`src/Workflows/flow_catalog.py`);
 * `base` ở đây chỉ là fallback hiển thị để select không trỏ vào option không tồn tại.
 */
function withCurrent(base: readonly string[], current: string): string[] {
  if (!current) return [...base];
  return base.includes(current) ? [...base] : [current, ...base];
}

/** Model video đang chọn; khi chưa tải xong options thì trả model đầu tiên. */
function selectedVideoModel(opts: NodeMediaOptions | null, id?: string | null) {
  const models = opts?.video.models ?? [];
  if (!models.length) return null;
  return models.find((m) => m.id === (id ?? "")) ?? models[0];
}

interface ParamsProps {
  node: CanvasDrawerNode;
  opts: NodeMediaOptions | null;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** Image node composer params: aspect ratio, model, count and seed. */
export function ImageParams({ node, opts, onUpdateNode }: ParamsProps) {
  const imageModels = opts?.image.models ?? [];
  const imageCounts = opts?.image.counts ?? [1, 2, 3, 4];

  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
        <span className="text-[10px] text-mut block">Tỷ lệ khung hình</span>
        <select
          value={node.aspectRatio}
          onChange={(e) => onUpdateNode?.(node.id, { aspectRatio: e.target.value })}
          className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
        >
          {withCurrent(opts?.image.aspect_ratios ?? ["16:9", "4:3", "1:1", "3:4", "9:16"], node.aspectRatio).map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
        <span className="text-[10px] text-mut block">Model</span>
        <select
          value={node.imageModel ?? opts?.image.default_model ?? imageModels[0]?.id ?? ""}
          onChange={(e) => onUpdateNode?.(node.id, { imageModel: e.target.value })}
          className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
        >
          {imageModels.length === 0 && <option value="">(chưa tải options)</option>}
          {imageModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
        <span className="text-[10px] text-mut block">Số lượng</span>
        <select
          value={node.imageCount ?? 1}
          onChange={(e) => onUpdateNode?.(node.id, { imageCount: Number(e.target.value) })}
          className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
        >
          {imageCounts.map((c) => (
            <option key={c} value={c}>
              x{c}
            </option>
          ))}
        </select>
      </label>
      <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
        <span className="text-[10px] text-mut block">Seed (trống = ngẫu nhiên)</span>
        <input
          type="number"
          min={1}
          max={2147483647}
          value={node.seed ?? ""}
          onChange={(e) =>
            onUpdateNode?.(node.id, {
              seed: e.target.value === "" ? null : Number(e.target.value),
            })
          }
          placeholder="random"
          className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] font-mono text-fg outline-none focus:border-acc"
        />
      </label>
    </div>
  );
}

/** Video node composer params: sub-mode, model, ratio, resolution, duration, count and seed. */
export function VideoParams({ node, opts, onUpdateNode }: ParamsProps) {
  const videoModels = opts?.video.models ?? [];
  const videoCounts = opts?.video.counts ?? [1, 2, 3, 4];
  const videoSubModes = opts?.video.sub_modes ?? ["frames", "ingredients"];
  const videoSubModeLabels = opts?.video.sub_mode_labels ?? {};
  const videoSubModeHints = opts?.video.sub_mode_descriptions ?? {};

  /** Model video đang chọn quyết định nhóm nào còn tồn tại trong composer. */
  const activeVideoModel = selectedVideoModel(opts, node?.videoModel);
  const videoResolutions = activeVideoModel?.resolutions ?? ["360p", "720p", "1080p"];
  const videoDurations = activeVideoModel?.durations_s ?? [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
  // Flow lowers the ceiling to 10s once both frame slots are filled (slider max 12 → 7).
  const videoHasLastFrame =
    !!node?.videoLastFrameSourceId && (node?.videoSubMode ?? "frames") === "frames";
  // A video reference leaves the Omni family entirely: `jIps6` / `abra_edit` takes its length
  // from the clip, so whatever the slider says is ignored.
  const videoUsesClipLength =
    (node?.videoSubMode ?? "frames") === "ingredients" && !!node?.videoReferenceTitle;
  const videoHasResolution = activeVideoModel?.has_resolution ?? true;
  const videoHasDuration = activeVideoModel?.has_duration ?? true;
  const videoAspects = activeVideoModel?.aspect_ratios ?? opts?.video.aspect_ratios ?? ["16:9", "9:16"];

  return (
    <div className="flex flex-col gap-2">
      {/* Sub-mode: "Khung hình" (eb1hJf, cần frame) vs "Thành phần"
          (YhhmEf, text→video thật). Bằng chứng: traces/submit_bodies/t2v_* */}
      <div className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1.5">
        <span className="text-[10px] text-mut block">Chế độ</span>
        <div className="flex items-center gap-1">
          {videoSubModes.map((sm) => {
            const active = (node.videoSubMode ?? "frames") === sm;
            return (
              <button
                key={sm}
                type="button"
                onClick={() => onUpdateNode?.(node.id, { videoSubMode: sm })}
                title={videoSubModeHints[sm] ?? ""}
                className={`flex-1 h-7 rounded-[5px] text-[11px] font-semibold border transition-colors cursor-pointer ${
                  active
                    ? "border-acc bg-acc/15 text-acc"
                    : "border-line2 bg-panel text-dim hover:text-fg"
                }`}
              >
                {videoSubModeLabels[sm] ?? sm}
              </button>
            );
          })}
        </div>
        {videoSubModeHints[node.videoSubMode ?? "frames"] && (
          <p className="text-[10px] text-mut leading-snug">
            {videoSubModeHints[node.videoSubMode ?? "frames"]}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
          <span className="text-[10px] text-mut block">Model</span>
          <select
            value={node.videoModel ?? opts?.video.default_model ?? videoModels[0]?.id ?? ""}
            onChange={(e) => {
              const nextId = e.target.value;
              const nextModel = videoModels.find((m) => m.id === nextId);
              // Giữ cấu hình hợp lệ: Veo cố định 720p/8s và chỉ có 2 tỷ lệ.
              const patch: Partial<CanvasDrawerNode> = { videoModel: nextId };
              if (nextModel) {
                if (!nextModel.has_resolution) {
                  patch.resolution = nextModel.resolutions[1] ?? nextModel.resolutions[0] ?? "720p";
                } else if (!nextModel.resolutions.includes(node.resolution)) {
                  patch.resolution = nextModel.resolutions[0];
                }
                if (!nextModel.has_duration) {
                  patch.videoDurationS = nextModel.durations_s[0] ?? 8;
                } else if (!nextModel.durations_s.includes(node.videoDurationS ?? 8)) {
                  patch.videoDurationS = nextModel.durations_s[0];
                }
                if (!nextModel.aspect_ratios.includes(node.videoRatio)) {
                  patch.videoRatio = nextModel.aspect_ratios[0];
                }
              }
              onUpdateNode?.(node.id, patch);
            }}
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
          >
            {videoModels.length === 0 && <option value="">(chưa tải options)</option>}
            {videoModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
          <span className="text-[10px] text-mut block">Tỷ lệ video</span>
          <select
            value={node.videoRatio}
            onChange={(e) => onUpdateNode?.(node.id, { videoRatio: e.target.value })}
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
          >
            {withCurrent(videoAspects, node.videoRatio).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label
          className={`rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1 ${
            videoHasResolution ? "" : "opacity-50"
          }`}
          title={
            videoHasResolution
              ? "360p là lựa chọn của Flow; 1080p là bước upsample p0UkFb của app sau khi render 720p"
              : `${activeVideoModel?.label ?? "Model này"} cố định ${videoResolutions[0] ?? "720p"} — composer Flow ẩn nhóm độ phân giải`
          }
        >
          <span className="text-[10px] text-mut block">Độ phân giải</span>
          <select
            value={node.resolution}
            disabled={!videoHasResolution}
            onChange={(e) => onUpdateNode?.(node.id, { resolution: e.target.value })}
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer disabled:cursor-not-allowed disabled:text-mut"
          >
            {withCurrent(videoResolutions, node.resolution).map((r) => (
              <option key={r} value={r}>
                {r}
                {r === "1080p" ? " (upscale)" : ""}
              </option>
            ))}
          </select>
        </label>
        <div
          className={`rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1 ${
            videoHasDuration ? "" : "opacity-50"
          }`}
          title={
            videoHasDuration
              ? "Thời lượng Flow cho chọn theo model"
              : `${activeVideoModel?.label ?? "Model này"} cố định ${videoDurations[0] ?? 8}s — composer Flow ẩn nhóm thời lượng`
          }
        >
          {/* Slider, not a select: Omni 1.2 exposes a continuous 3..15s range, so discrete
              chips would misrepresent what Flow actually offers. */}
          <DurationSlider
            options={videoDurations}
            value={node.videoDurationS ?? videoDurations[0] ?? 8}
            maxAllowed={videoHasLastFrame ? LAST_FRAME_MAX_DURATION_S : undefined}
            enabled={videoHasDuration}
            onChange={(seconds) => onUpdateNode?.(node.id, { videoDurationS: seconds })}
            clipLengthOverrides={videoUsesClipLength}
          />
        </div>
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
          <span className="text-[10px] text-mut block">Số lượng</span>
          <select
            value={node.videoCount ?? 1}
            onChange={(e) => onUpdateNode?.(node.id, { videoCount: Number(e.target.value) })}
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc cursor-pointer"
          >
            {videoCounts.map((c) => (
              <option key={c} value={c}>
                x{c}
              </option>
            ))}
          </select>
        </label>
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1">
          <span className="text-[10px] text-mut block">Seed (trống = ngẫu nhiên)</span>
          <input
            type="number"
            min={1}
            max={2147483647}
            value={node.seed ?? ""}
            onChange={(e) =>
              onUpdateNode?.(node.id, {
                seed: e.target.value === "" ? null : Number(e.target.value),
              })
            }
            placeholder="random"
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] font-mono text-fg outline-none focus:border-acc"
          />
        </label>
      </div>
    </div>
  );
}

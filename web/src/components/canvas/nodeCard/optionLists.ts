import type {
  NodeImageModelOption,
  NodeMediaOptions,
  NodeVideoModelOption,
} from "../../../types";

/** Option lists (from `/api/node/options`, with fallbacks) that feed a node's dropdowns. */
export interface NodeOptionLists {
  imageRatios: string[];
  verifiedRatios: Set<string>;
  videoRatios: string[];
  resolutions: string[];
  imageModels: NodeImageModelOption[];
  imageCounts: number[];
  imageDefaultModel: string;
  videoModels: NodeVideoModelOption[];
  videoCounts: number[];
  videoDefaultModel: string;
  videoSubModes: string[];
  videoSubModeLabels: Record<string, string>;
  agentLocked: boolean;
}

export function deriveNodeOptionLists(opts: NodeMediaOptions | null): NodeOptionLists {
  const imageRatios = opts?.image.aspect_ratios ?? ["16:9", "4:3", "1:1", "3:4", "9:16"];
  // Aspect enum của ảnh là bằng chứng capture được ⇒ mọi tỷ lệ backend trả về đều dùng được.
  const verifiedRatios = new Set(opts?.image.aspect_ratios ?? imageRatios);
  const videoRatios = opts?.video.aspect_ratios ?? ["16:9", "9:16"];
  // Độ phân giải phụ thuộc model (Veo không có 360p): lấy danh sách lớn nhất, NodeCard
  // tự lọc lại theo `has_resolution` của model đang chọn.
  const resolutions = Array.from(
    new Set((opts?.video.models ?? []).flatMap((m) => m.resolutions ?? [])),
  );
  return {
    imageRatios,
    verifiedRatios,
    videoRatios,
    resolutions: resolutions.length ? resolutions : ["720p", "1080p"],
    imageModels: opts?.image.models ?? [],
    imageCounts: opts?.image.counts ?? [1, 2, 3, 4],
    imageDefaultModel: opts?.image.default_model ?? "",
    videoModels: opts?.video.models ?? [],
    videoCounts: opts?.video.counts ?? [1, 2, 3, 4],
    videoDefaultModel: opts?.video.default_model ?? "",
    videoSubModes: opts?.video.sub_modes ?? ["frames", "ingredients"],
    videoSubModeLabels: opts?.video.sub_mode_labels ?? {},
    agentLocked: !!opts?.agent?.locks_config,
  };
}

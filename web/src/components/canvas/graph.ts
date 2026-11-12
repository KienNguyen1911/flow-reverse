import type { NodeMediaOptions } from "../../types";
import type { CanvasNode, NodeType } from "./types";

// Pure queries over the node graph: who feeds whom, what a node resolves its
// upstream media to, and whether a new link would form a loop.

//: Duration a new video node starts at when the catalog is not loaded yet. Once the card
//: mounts it adopts the selected model's own `durations_s`, so this only covers the first
//: render. Matches the backend default `VIDEO_DURATION_S` in `src/Workflows/media_options.py`.
const DEFAULT_VIDEO_DURATION_S = 8;

export type SourceResult =
  | { ok: true; url: string | null; urls: string[] }
  | { ok: false; reason: string };

export function getNodeSourceIds(n: CanvasNode): string[] {
  if (n.type === "image") {
    if (Array.isArray(n.sourceImageIds) && n.sourceImageIds.length > 0) {
      return n.sourceImageIds;
    }
    if (n.sourceImageId) {
      return [n.sourceImageId];
    }
    return [];
  }
  return n.sourceImageId ? [n.sourceImageId] : [];
}

/** Resolve the upstream media a node should use as reference(s) / start frame / extraction source. */
export function resolveSource(nodes: CanvasNode[], n: CanvasNode, dry: boolean): SourceResult {
  const sids = getNodeSourceIds(n);
  if (sids.length === 0) {
    if (n.type === "last_frame") return { ok: false, reason: "Chưa chọn node video nguồn." };
    return { ok: true, url: null, urls: [] };
  }

  const urls: string[] = [];
  for (const sid of sids) {
    const src = nodes.find((x) => x.id === sid);
    if (!src) continue;

    if (n.type === "last_frame") {
      if (src.type !== "video") return { ok: false, reason: "Nguồn của Frame Cuối phải là node Video." };
      if (dry) return { ok: true, url: null, urls: [] };
      if (src.status === "succeeded" && src.videoUrl) return { ok: true, url: src.videoUrl, urls: [src.videoUrl] };
      return { ok: false, reason: "Node video nguồn chưa có video kết quả — hãy chạy video nguồn trước." };
    }

    if (src.type === "ref") {
      if (!src.fileUrl) return { ok: false, reason: `Node ảnh tham chiếu "${src.fileName ?? src.id}" chưa upload ảnh.` };
      urls.push(src.fileUrl);
      continue;
    }

    if (src.type === "last_frame") {
      if (dry) continue;
      if (src.status === "succeeded" && src.fileUrl) {
        urls.push(src.fileUrl);
        continue;
      }
      return { ok: false, reason: "Node Frame Cuối chưa chạy xong — hãy trích xuất frame trước." };
    }

    if (src.type === "image") {
      if (src.status === "succeeded" && src.fileUrl) {
        urls.push(src.fileUrl);
        continue;
      }
      if (dry) continue;
      return { ok: false, reason: `Node ảnh nguồn "${src.prompt ? src.prompt.slice(0, 20) + "…" : src.id}" chưa có kết quả — hãy chạy trước.` };
    }
  }

  return { ok: true, url: urls[0] ?? null, urls };
}

/** Check if there is any directed dependency path from fromId to toId (cycle detection). */
function hasPath(nodes: CanvasNode[], fromId: string, toId: string, visited = new Set<string>()): boolean {
  if (fromId === toId) return true;
  if (visited.has(fromId)) return false;
  visited.add(fromId);
  const fromNode = nodes.find((x) => x.id === fromId);
  if (!fromNode) return false;
  const sids = getNodeSourceIds(fromNode);
  for (const sid of sids) {
    if (hasPath(nodes, sid, toId, visited)) return true;
  }
  return false;
}

/** True if `candidate` is `id` itself or sits downstream of it (linking would form a loop). */
export function isDownstream(nodes: CanvasNode[], id: string, candidate: string): boolean {
  return hasPath(nodes, candidate, id);
}

/** Number of hops from the root of n's input chain (ref/unlinked = 0). Cycle-safe. */
export function chainDepth(nodes: CanvasNode[], n: CanvasNode, seen = new Set<string>()): number {
  if (seen.has(n.id)) return 0;
  seen.add(n.id);
  const sids = getNodeSourceIds(n);
  if (sids.length === 0) return 0;
  let maxD = 0;
  for (const sid of sids) {
    const parent = nodes.find((x) => x.id === sid);
    if (parent) {
      maxD = Math.max(maxD, 1 + chainDepth(nodes, parent, new Set(seen)));
    }
  }
  return maxD;
}

export function isVideoContinuation(nodes: CanvasNode[], n: CanvasNode): boolean {
  if (n.type !== "video" || !n.sourceImageId) return false;
  const parent = nodes.find((x) => x.id === n.sourceImageId);
  return parent?.type === "last_frame" || parent?.type === "video";
}

let seq = Date.now() % 100000;
export const nextId = (type: string) => `${type}_${(seq++).toString(36)}`;

export function newNode(type: NodeType, opts: NodeMediaOptions | null, x: number, y: number): CanvasNode {
  const base: CanvasNode = {
    id: nextId(type),
    type,
    x,
    y,
    prompt: "",
    aspectRatio: opts?.image.default_aspect_ratio ?? "16:9",
    seed: null,
    sourceImageId: null,
    sourceImageIds: [],
    videoRatio: opts?.video.default_aspect_ratio ?? "9:16",
    resolution: "1080p",
    imageAspectRatio: "16:9",
    imageModel: opts?.image.default_model ?? "nano_banana_2_1",
    imageCount: opts?.image.default_count ?? 1,
    videoModel: opts?.video.default_model ?? "omni_1_2_flash",
    videoSubMode: opts?.video.default_sub_mode ?? "frames",
    videoCount: opts?.video.default_count ?? 1,
    // Preferred length when creating a node. The model's own `durations_s` wins once the
    // card mounts and the catalog is loaded; this is only the pre-fetch fallback.
    videoDurationS: DEFAULT_VIDEO_DURATION_S,
    videoLastFrameSourceId: null,
    videoReferenceTitle: null,
    agentMode: false,
    autoImagePrompt: "",
    removeWatermark: true,
    jobId: null,
    status: "idle",
    isItem: false,
  };
  return base;
}

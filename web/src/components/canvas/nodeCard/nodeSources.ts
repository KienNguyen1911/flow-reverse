import { isDownstream, getNodeSourceIds } from "../graph";
import type { CanvasNode } from "../types";

/** What a node is wired to, plus the upstream nodes it could still be wired to. */
export interface NodeSources {
  currentSids: string[];
  connectedSources: CanvasNode[];
  /** Primary (first) upstream node — the frame/video source for video & last_frame nodes. */
  upstream: CanvasNode | undefined;
  /** "Thành phần" là text→video: không cần frame nên không có nguồn nào bị chặn. */
  textToVideo: boolean;
  /** An upstream node has not produced its result yet. */
  sourceBlocked: boolean;
  /** Nodes this one may legally pick as input (no self/downstream, right type). */
  sourceOptions: CanvasNode[];
  /** `sourceOptions` not already connected. */
  availableOptions: CanvasNode[];
}

export function deriveNodeSources(n: CanvasNode, allNodes: CanvasNode[]): NodeSources {
  const isRef = n.type === "ref";
  const isVid = n.type === "video";
  const isLastFrame = n.type === "last_frame";

  const currentSids = getNodeSourceIds(n);
  const connectedSources = currentSids
    .map((sid) => allNodes.find((i) => i.id === sid))
    .filter(Boolean) as CanvasNode[];

  const upstream = n.sourceImageId ? allNodes.find((i) => i.id === n.sourceImageId) : undefined;
  const textToVideo = isVid && (n.videoSubMode ?? "frames") === "ingredients";
  const sourceBlocked =
    !isRef &&
    connectedSources.length > 0 &&
    connectedSources.some((src) => {
      if (isLastFrame) return src.status !== "succeeded" || !src.videoUrl;
      return src.type !== "ref" && src.status !== "succeeded";
    });

  // Selectable upstream nodes:
  // For last_frame: only video nodes
  // For image/video: ref, image, or last_frame nodes
  const sourceOptions = allNodes.filter((c) => {
    if (c.id === n.id || isDownstream(allNodes, n.id, c.id)) return false;
    if (isLastFrame) return c.type === "video";
    return c.type === "ref" || c.type === "image" || c.type === "last_frame";
  });
  const availableOptions = sourceOptions.filter((c) => !currentSids.includes(c.id));

  return {
    currentSids,
    connectedSources,
    upstream,
    textToVideo,
    sourceBlocked,
    sourceOptions,
    availableOptions,
  };
}

export function sourceLabel(c: CanvasNode): string {
  if (c.label) return c.label;
  if (c.type === "ref") return `Tham chiếu: ${c.fileName ?? c.id}`;
  if (c.type === "last_frame") return `Frame Cuối: ${c.id}${c.fileUrl ? " (đã có ảnh)" : ""}`;
  if (c.type === "video") return `Video: ${c.prompt ? c.prompt.slice(0, 24) + "…" : c.id}`;
  return c.prompt ? `Ảnh: ${c.prompt.slice(0, 24)}…` : `Ảnh (${c.id})`;
}

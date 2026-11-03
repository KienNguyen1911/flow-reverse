import type { ItemScope, WorkspaceCanvasState } from "../../types";
import { ITEM_SCOPE_OPTIONS, STORAGE_KEY } from "./constants";
import { clamp } from "./geometry";
import { getNodeSourceIds } from "./graph";
import type { CanvasGroup, CanvasNode, Graph, NodeStatus, NodeType, View } from "./types";

// Conversion between the live graph and its persisted shapes (localStorage
// legacy graph, workspace canvas state). Defensive against old/partial data.

const ITEM_SCOPES: readonly string[] = ITEM_SCOPE_OPTIONS.map((o) => o.value);

const NODE_TYPES: ReadonlySet<string> = new Set(["ref", "image", "video", "last_frame"]);
const NODE_STATUSES: ReadonlySet<string> = new Set([
  "idle",
  "queued",
  "running",
  "succeeded",
  "failed",
  "rejected",
  "skipped",
]);

export function loadGraph(): Graph {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const g = JSON.parse(raw) as Graph;
      if (Array.isArray(g?.nodes)) {
        return {
          nodes: g.nodes,
          groups: Array.isArray(g.groups)
            ? g.groups
                .filter((gr) => gr && typeof gr.id === "string" && Array.isArray(gr.nodeIds))
                .map((gr) => ({ ...gr, nodeIds: gr.nodeIds.filter((id) => typeof id === "string") }))
            : [],
        };
      }
    }
  } catch {
    /* ignore */
  }
  return { nodes: [], groups: [] };
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function optionalStr(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function finite(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** Derive the persisted edge list from the nodes' input links. */
export function graphToCanvasState(
  nodes: CanvasNode[],
  groups: CanvasGroup[],
  view: View,
): WorkspaceCanvasState {
  const edges: WorkspaceCanvasState["edges"] = [];
  const seen = new Set<string>();
  for (const node of nodes) {
    for (const source of getNodeSourceIds(node)) {
      if (!source || !nodes.some((n) => n.id === source)) continue;
      const id = `e_${source}__${node.id}`;
      if (seen.has(id)) continue;
      seen.add(id);
      edges.push({ id, source, target: node.id });
    }
  }
  return {
    viewport: { x: view.x, y: view.y, zoom: view.z },
    nodes: nodes.map((n) => ({ ...n })),
    edges,
    groups: groups.map((g) => ({ ...g, nodeIds: [...g.nodeIds] })),
  };
}

/** Rebuild the live graph from persisted canvas state (defensive against old data). */
export function canvasStateToGraph(state?: WorkspaceCanvasState | null): {
  graph: Graph;
  view: View;
} {
  const rawNodes: unknown[] = Array.isArray(state?.nodes) ? state!.nodes : [];
  const nodes: CanvasNode[] = [];
  for (const raw of rawNodes) {
    if (!raw || typeof raw !== "object") continue;
    const r = raw as Record<string, unknown>;
    if (typeof r.id !== "string" || !NODE_TYPES.has(String(r.type))) continue;
    const rawStatus = String(r.status ?? "idle");
    // A workflow interrupted by a reload must not stay "running" forever.
    const status: NodeStatus =
      rawStatus === "queued" || rawStatus === "running"
        ? "idle"
        : NODE_STATUSES.has(rawStatus)
          ? (rawStatus as NodeStatus)
          : "idle";
    const sourceIds = Array.isArray(r.sourceImageIds)
      ? r.sourceImageIds.filter((x): x is string => typeof x === "string")
      : [];
    nodes.push({
      id: r.id,
      type: r.type as NodeType,
      x: finite(r.x),
      y: finite(r.y),
      label: optionalStr(r.label),
      prompt: str(r.prompt),
      fileName: optionalStr(r.fileName),
      aspectRatio: str(r.aspectRatio, "3:4"),
      seed: typeof r.seed === "number" ? r.seed : null,
      sourceImageId: optionalStr(r.sourceImageId),
      ...(sourceIds.length ? { sourceImageIds: sourceIds } : {}),
      videoRatio: str(r.videoRatio, "9:16"),
      resolution: str(r.resolution, "1080p"),
      imageAspectRatio: str(r.imageAspectRatio, "9:16"),
      imageModel: optionalStr(r.imageModel),
      imageCount: typeof r.imageCount === "number" ? r.imageCount : 1,
      videoModel: optionalStr(r.videoModel),
      videoSubMode: optionalStr(r.videoSubMode) ?? "frames",
      videoCount: typeof r.videoCount === "number" ? r.videoCount : 1,
      videoDurationS: typeof r.videoDurationS === "number" ? r.videoDurationS : 8,
      agentMode: typeof r.agentMode === "boolean" ? r.agentMode : false,
      autoImagePrompt: str(r.autoImagePrompt),
      removeWatermark: typeof r.removeWatermark === "boolean" ? r.removeWatermark : true,
      jobId: optionalStr(r.jobId),
      status,
      fileUrl: optionalStr(r.fileUrl),
      videoUrl: optionalStr(r.videoUrl),
      frameUrl: optionalStr(r.frameUrl),
      reason: optionalStr(r.reason),
      elapsedS: typeof r.elapsedS === "number" ? r.elapsedS : null,
      agentSkillId: optionalStr(r.agentSkillId),
      agentCustomHint: optionalStr(r.agentCustomHint),
      clipId: optionalStr(r.clipId),
      // `runId` is what the delivery export joins clip → file on (CanvasPanel reads it off
      // `lb_video_*`). It used to be dropped here, so a reload silently emptied the export.
      runId: optionalStr(r.runId),
      isItem: typeof r.isItem === "boolean" ? r.isItem : false,
      itemName: optionalStr(r.itemName),
      itemScope: ITEM_SCOPES.includes(String(r.itemScope) as ItemScope)
        ? (r.itemScope as ItemScope)
        : null,
    });
  }

  // Restore links from explicit edges only where node-level links are missing.
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const incoming = new Map<string, string[]>();
  const rawEdges: unknown[] = Array.isArray(state?.edges) ? state!.edges : [];
  for (const raw of rawEdges) {
    if (!raw || typeof raw !== "object") continue;
    const e = raw as Record<string, unknown>;
    const source = typeof e.source === "string" ? e.source : null;
    const target = typeof e.target === "string" ? e.target : null;
    if (!source || !target || !byId.has(source) || !byId.has(target)) continue;
    const list = incoming.get(target) ?? [];
    if (!list.includes(source)) list.push(source);
    incoming.set(target, list);
  }
  for (const [target, sources] of incoming) {
    const node = byId.get(target);
    if (!node) continue;
    if (node.type === "image") {
      const existing = getNodeSourceIds(node);
      if (existing.length === 0) {
        node.sourceImageIds = [...sources];
        node.sourceImageId = sources[0] ?? null;
      }
    } else if (!node.sourceImageId) {
      node.sourceImageId = sources[0] ?? null;
    }
  }

  const existingIds = new Set(nodes.map((n) => n.id));
  const rawGroups: unknown[] = Array.isArray(state?.groups) ? state!.groups : [];
  const groups: CanvasGroup[] = [];
  for (const raw of rawGroups) {
    if (!raw || typeof raw !== "object") continue;
    const g = raw as Record<string, unknown>;
    if (typeof g.id !== "string") continue;
    groups.push({
      id: g.id,
      name: str(g.name, "Nhóm"),
      nodeIds: Array.isArray(g.nodeIds)
        ? g.nodeIds.filter((id): id is string => typeof id === "string" && existingIds.has(id))
        : [],
      color: optionalStr(g.color),
      x: typeof g.x === "number" ? g.x : null,
      y: typeof g.y === "number" ? g.y : null,
      w: typeof g.w === "number" ? g.w : null,
      h: typeof g.h === "number" ? g.h : null,
    });
  }

  const vp = state?.viewport;
  const view: View = {
    x: finite(vp?.x, 40),
    y: finite(vp?.y, 20),
    z: clamp(finite(vp?.zoom, 1), 0.2, 2.5),
  };

  return { graph: { nodes, groups }, view };
}

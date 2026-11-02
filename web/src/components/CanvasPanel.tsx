import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import {
  ArrowsCounterClockwise,
  ArrowsOut,
  CheckCircle,
  DownloadSimple,
  FilmSlate,
  FlowArrow,
  Image as ImageIcon,
  LinkSimple,
  ListDashes,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  FolderSimple,
  Play,
  Plus,
  Sparkle,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type {
  DeliveryItemRef,
  ItemScope,
  Job,
  LibraryItem,
  NodeMediaOptions,
  WorkspaceCanvasState,
} from "../types";
import { CanvasDrawer, type CanvasDrawerNode } from "./CanvasDrawer";
import {
  OrderBadge,
  PromptEditorModal,
  PromptPreviewCard,
  SummaryPill,
  highlightPrompt,
} from "./canvasNodeBits";
import { Chip, Spinner } from "./ui";
import { useLimits } from "../hooks";
import { MediaPreviewModal, type PreviewMediaItem } from "./MediaPreviewModal";
import { DeliveryModal } from "./DeliveryModal";

// --------------------------------------------------------------------------- //
// Canvas node graph — image nodes feed video nodes (image-to-video chains).
// Backend: POST /api/node/image, POST /api/node/video, POST /api/node/last_frame
// Chaining works because resolve_input_path() accepts /api/node/files/... URLs
// as attachments, so an image node's file_url becomes a video node's frame_path,
// and a last_frame node extracts the final frame of a video to feed the next video/image.
// --------------------------------------------------------------------------- //

const NODE_W = 280;
const ANCHOR_Y = 22;
const GROUP_PAD = 26;
const GROUP_HEADER_H = 40;
const FALLBACK_NODE_H = 220;
const GROUP_COLORS = ["#7c9cff", "#4ade80", "#f59e0b", "#c084fc", "#f472b6", "#22d3ee"];
const STORAGE_KEY = "fb_canvas_graph_v1";
const TEMPLATES_KEY = "fb_custom_templates_v1";

export interface CustomTemplate {
  id: string;
  name: string;
  createdAt: number;
  nodes: CanvasNode[];
  groups?: CanvasGroup[];
}
const TERMINAL = new Set(["succeeded", "failed", "rejected"]);
const ACTIVE = new Set(["queued", "running"]);

type NodeStatus = "idle" | "queued" | "running" | "succeeded" | "failed" | "rejected" | "skipped";
type NodeType = "ref" | "image" | "video" | "last_frame";

/** Tab / section the Right Inspector should focus when opened from the node body. */
export type DrawerSection = "config" | "prompt" | "sources" | "preview" | "logs" | "error";


type CanvasNode = CanvasDrawerNode;

/**
 * Visual Group / Scope: a labelled frame that owns a set of nodes.
 * Failure policy: when a node inside a group fails, the rest of THAT group is
 * skipped and the workflow continues with the next group.
 */
interface CanvasGroup {
  id: string;
  name: string;
  nodeIds: string[];
  color?: string | null;
  /** Manual frame override (set when the user drags/resizes the frame itself). */
  x?: number | null;
  y?: number | null;
  w?: number | null;
  h?: number | null;
}

interface Graph {
  nodes: CanvasNode[];
  groups: CanvasGroup[];
}

interface View {
  x: number;
  y: number;
  z: number;
}

interface ToastInfo {
  id: number;
  message: string;
  type: "ok" | "info" | "err";
  nodeId?: string;
}

function loadGraph(): Graph {
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

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

// -- workspace serialization ------------------------------------------------ //

export const BUILTIN_TEMPLATES = [
  { id: "lookbook_8s", name: "Lookbook 16s (Plate → Video 1 → Video 2)" },
  { id: "tryon", name: "Video Thử Đồ (Try-On 16s)" },
] as const;

/**
 * Phạm vi ảnh sản phẩm. Bắt buộc phải chọn khi ảnh ref là cả bộ: skill cutout mặc định
 * "một món", nên không nói rõ thì model chọn vật thể nổi bật nhất — luôn là chiếc áo.
 */
const ITEM_SCOPE_OPTIONS: { value: ItemScope; label: string; hint: string }[] = [
  { value: "top", label: "Áo", hint: "Chỉ món mặc trên: áo, camisole, cardigan" },
  { value: "bottom", label: "Quần / Váy", hint: "Chỉ món mặc dưới: quần, váy, shorts" },
  { value: "full_set", label: "Cả bộ", hint: "Các món xếp cạnh nhau trên một ảnh — không tách nền được" },
];
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

type SourceResult = { ok: true; url: string | null; urls: string[] } | { ok: false; reason: string };

function getNodeSourceIds(n: CanvasNode): string[] {
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
function resolveSource(nodes: CanvasNode[], n: CanvasNode, dry: boolean): SourceResult {
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
function isDownstream(nodes: CanvasNode[], id: string, candidate: string): boolean {
  return hasPath(nodes, candidate, id);
}

/** Number of hops from the root of n's input chain (ref/unlinked = 0). Cycle-safe. */
function chainDepth(nodes: CanvasNode[], n: CanvasNode, seen = new Set<string>()): number {
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

function isVideoContinuation(nodes: CanvasNode[], n: CanvasNode): boolean {
  if (n.type !== "video" || !n.sourceImageId) return false;
  const parent = nodes.find((x) => x.id === n.sourceImageId);
  return parent?.type === "last_frame" || parent?.type === "video";
}

// --------------------------------------------------------------------------- //
// Visual Group / Scope
// A group is a labelled frame owning a set of nodes. Execution treats every
// group as an isolated unit: a node failure aborts only that group, the next
// group still runs. Ungrouped nodes form one virtual, implicit unit.
// --------------------------------------------------------------------------- //

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface RunUnit {
  id: string;
  name: string;
  color: string | null;
  kind: "group" | "loose";
  nodeIds: string[];
}

function nodeHeight(n: CanvasNode, heights: Record<string, number>): number {
  return heights[n.id] ?? FALLBACK_NODE_H;
}

/** Frame that encloses all member nodes (derived, so it always stays tight). */
function groupFrame(
  group: CanvasGroup,
  byId: Map<string, CanvasNode>,
  heights: Record<string, number>,
): Rect | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let count = 0;
  for (const id of group.nodeIds) {
    const m = byId.get(id);
    if (!m) continue;
    count++;
    minX = Math.min(minX, m.x);
    minY = Math.min(minY, m.y);
    maxX = Math.max(maxX, m.x + NODE_W);
    maxY = Math.max(maxY, m.y + nodeHeight(m, heights));
  }
  if (count === 0) return null;
  const x = minX - GROUP_PAD;
  const y = minY - GROUP_PAD - GROUP_HEADER_H;
  return {
    x,
    y,
    w: maxX - minX + GROUP_PAD * 2,
    h: maxY - minY + GROUP_PAD * 2 + GROUP_HEADER_H,
  };
}

/** Weakly-connected components of the given node ids (via source links). */
function componentsOf(nodes: CanvasNode[], ids: string[]): string[][] {
  const allowed = new Set(ids);
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let p = parent.get(x) ?? x;
    while (p !== (parent.get(p) ?? p)) p = parent.get(p) ?? p;
    return p;
  };
  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };
  ids.forEach((id) => parent.set(id, id));
  for (const n of nodes) {
    if (!allowed.has(n.id)) continue;
    for (const sid of getNodeSourceIds(n)) {
      if (allowed.has(sid)) union(n.id, sid);
    }
  }
  const buckets = new Map<string, string[]>();
  for (const id of ids) {
    const root = find(id);
    const arr = buckets.get(root);
    if (arr) arr.push(id);
    else buckets.set(root, [id]);
  }
  return Array.from(buckets.values());
}

/**
 * Build the ordered execution plan.
 * - No selection: every group runs (plus virtual units for ungrouped nodes,
 *   split into connected components so separate pipelines stay independent).
 * - With a selection: only groups touched by the selection run (whole group,
 *   because a group is one unit), plus the selected ungrouped nodes.
 * Units are ordered by the shallowest chain depth they contain.
 */
function buildRunUnits(nodes: CanvasNode[], groups: CanvasGroup[], selectedIds: string[]): RunUnit[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const sel = new Set(selectedIds.filter((id) => byId.has(id)));

  const units: RunUnit[] = [];
  const inGroup = new Set<string>();

  for (const g of groups) {
    const ids = g.nodeIds.filter((id) => byId.has(id));
    if (ids.length === 0) continue;
    ids.forEach((id) => inGroup.add(id));
    if (sel.size > 0 && !ids.some((id) => sel.has(id))) continue;
    units.push({
      id: g.id,
      name: g.name || "Nhóm chưa đặt tên",
      color: g.color ?? null,
      kind: "group",
      nodeIds: ids,
    });
  }

  const loose = nodes
    .filter((n) => !inGroup.has(n.id))
    .filter((n) => sel.size === 0 || sel.has(n.id))
    .map((n) => n.id);
  const comps = componentsOf(nodes, loose);
  comps.forEach((comp, i) => {
    units.push({
      id: `__loose_${i}`,
      name: comps.length > 1 ? `Node lẻ (nhánh ${i + 1})` : "Node lẻ (không thuộc nhóm)",
      color: null,
      kind: "loose",
      nodeIds: comp,
    });
  });

  const depthOf = (unit: RunUnit): number => {
    let min = Infinity;
    for (const id of unit.nodeIds) {
      const n = byId.get(id);
      if (!n || n.type === "ref") continue;
      min = Math.min(min, chainDepth(nodes, n));
    }
    return Number.isFinite(min) ? min : 0;
  };

  return units.sort((a, b) => depthOf(a) - depthOf(b));
}

/** Executable (non-ref) members of a unit, parents first. */
function unitMembers(nodes: CanvasNode[], unit: RunUnit): CanvasNode[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return unit.nodeIds
    .map((id) => byId.get(id))
    .filter((n): n is CanvasNode => !!n && n.type !== "ref")
    .sort((a, b) => chainDepth(nodes, a) - chainDepth(nodes, b));
}

let seq = Date.now() % 100000;
const nextId = (type: string) => `${type}_${(seq++).toString(36)}`;

function newNode(type: NodeType, opts: NodeMediaOptions | null, x: number, y: number): CanvasNode {
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
    resolution: opts?.video.default_resolution ?? "1080p",
    imageAspectRatio: "16:9",
    autoImagePrompt: "",
    removeWatermark: true,
    jobId: null,
    status: "idle",
    isItem: false,
    itemScope: null,
  };
  return base;
}

function statusStyle(s: NodeStatus): { border: string; label: string; cls: string } {
  switch (s) {
    case "queued":
      return { border: "border-mut/60", label: "Trong hàng đợi", cls: "text-dim" };
    case "running":
      return { border: "border-acc", label: "Đang chạy", cls: "text-acc" };
    case "succeeded":
      return { border: "border-ok/60", label: "Thành công", cls: "text-ok" };
    case "failed":
      return { border: "border-err", label: "Thất bại", cls: "text-err" };
    case "rejected":
      return { border: "border-err", label: "Bị từ chối", cls: "text-err" };
    case "skipped":
      return { border: "border-warn/60", label: "Bỏ qua", cls: "text-warn" };
    default:
      return { border: "border-line2", label: "", cls: "text-mut" };
  }
}

function createLookbook8sTemplate(): { nodes: CanvasNode[]; groups: CanvasGroup[] } {
  const nodes: CanvasNode[] = [
    // --- Nhóm 1: Plate → Video 1 → Frame cuối → Video 2 ---
    // Board có cột item đã bị bỏ: AI video không vẽ được chữ/logic UI. Lớp dựng
    // (HyperFrames desktop) lo card/kinetic text và tự canh vị trí, nên plate không
    // cần chừa cột trái nữa — chỉ cần nền sạch và người mẫu đúng khung.
    {
      id: "lb_ref_model",
      type: "ref",
      label: "Ảnh tham chiếu (ảnh sản phẩm gốc)",
      x: 60,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: null,
      fileName: null,
    },
    {
      id: "lb_plate",
      type: "image",
      label: "Plate (chỉ người mẫu, nền sạch)",
      x: 420,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_ref_model",
      sourceImageIds: ["lb_ref_model"],
      agentSkillId: "try-on-image-prompter",
      agentCustomHint: "plate first frame",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_video_1",
      type: "video",
      label: "Video 1 (8s: hook)",
      x: 780,
      y: 80,
      prompt: "Prompt chuyển động cho clip hook 8s...",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_plate",
      sourceImageIds: ["lb_plate"],
      agentSkillId: "lookbook-video-prompter",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_last_frame",
      type: "last_frame",
      label: "Frame Cuối Video 1",
      x: 1140,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_video_1",
      sourceImageIds: ["lb_video_1"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_video_2",
      type: "video",
      label: "Video 2 (8s: showcase)",
      x: 1500,
      y: 80,
      prompt: "Prompt chuyển động cho clip showcase 8s...",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_last_frame",
      sourceImageIds: ["lb_last_frame"],
      agentSkillId: "lookbook-video-prompter",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },

    // --- Nhóm 2: Cutout sản phẩm cho lớp card (không phải first frame) ---
    {
      id: "lb_ref_garment_upload",
      type: "ref",
      label: "Ảnh Shopee (lifestyle, kéo thả)",
      x: 60,
      y: 690,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: null,
      fileName: null,
    },
    {
      id: "lb_node_cutout_front",
      type: "image",
      label: "Cutout sản phẩm",
      x: 420,
      y: 690,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_ref_garment_upload",
      sourceImageIds: ["lb_ref_garment_upload"],
      agentSkillId: "lookbook-item-cutout-prompter",
      isItem: true,
      itemName: "",
      itemScope: "top",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "1:1",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
  ];

  // Mỗi món đúng MỘT node cutout — một mặt trước là đủ, không có node mặt sau.
  // Thẻ sản phẩm trên timeline chỉ cần một ảnh; ảnh lưng là chi phí credit không đổi lại
  // được gì (nó chỉ xuất hiện ở một shot 2–3s và có thể bị che bởi chữ).
  // Template chỉ cấp MỘT node mẫu: người bán có bao nhiêu món cũng dùng lại được bằng
  // cách nhân bản node và đặt `itemName`, không phải khai danh sách vào script.
  const cutoutIds = nodes
    .filter((n) => n.id.startsWith("lb_node_cutout_"))
    .map((n) => n.id);

  const groups: CanvasGroup[] = [
    {
      id: "lb_group_video_8s",
      name: "Nhóm 1: Plate → Video 1 → Video 2 (nền cho HyperFrames)",
      nodeIds: ["lb_ref_model", "lb_plate", "lb_video_1", "lb_last_frame", "lb_video_2"],
      color: GROUP_COLORS[0],
    },
    {
      id: "lb_group_items",
      name: "Nhóm 2: Cutout sản phẩm (lớp card, không phải first frame)",
      nodeIds: ["lb_ref_garment_upload", ...cutoutIds],
      color: GROUP_COLORS[1],
    },
  ];

  return { nodes, groups };
}

function createTryOnTemplate(): CanvasNode[] {
  return [
    {
      id: "tryon_ref_model",
      type: "ref",
      label: "Ảnh Người Mẫu (Nabi)",
      x: 60,
      y: 90,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: "/api/assets/nabi_model.png",
      fileName: "nabi_model.png",
    },
    {
      id: "tryon_ref_garment",
      type: "ref",
      label: "Ảnh Trang Phục",
      x: 60,
      y: 430,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: "/api/assets/sample_garment.png",
      fileName: "sample_garment.png",
    },
    {
      id: "tryon_node_image",
      type: "image",
      label: "Node Ảnh (First Frame)",
      x: 420,
      y: 220,
      prompt: "@nabi wearing this outfit, elegant studio fashion portrait, full body shot, high resolution, 8k, photorealistic",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_ref_model",
      sourceImageIds: ["tryon_ref_model", "tryon_ref_garment"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_video_1",
      type: "video",
      label: "Node Video 1 (8s)",
      x: 780,
      y: 220,
      prompt: "Nabi stands elegantly, smooth camera slow zoom in, gentle movement showing garment drape, natural studio lighting, 8 seconds",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_image",
      sourceImageIds: ["tryon_node_image"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_last_frame",
      type: "last_frame",
      label: "Frame Cuối (Video 1)",
      x: 1140,
      y: 220,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_video_1",
      sourceImageIds: ["tryon_node_video_1"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_video_2",
      type: "video",
      label: "Node Video 2 (8s Nối tiếp)",
      x: 1500,
      y: 220,
      prompt: "Nabi turns slightly to showcase side profile and back of the outfit, natural fashion pose, seamless motion continuation, 8 seconds",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_last_frame",
      sourceImageIds: ["tryon_node_last_frame"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
  ];
}

export interface CanvasStats {
  imageCount: number;
  videoCount: number;
  lastFrameCount: number;
  nRunning: number;
  nDone: number;
  nPending: number;
  groupCount: number;
  selectedCount: number;
  wfBusy: boolean;
  linking: boolean;
}

export interface CanvasPanelHandle {
  addNode: (type: NodeType) => void;
  addReferenceNode: (url: string, fileName?: string) => void;
  loadTemplate: (name: string) => void;
  saveCurrentTemplate: (name: string) => void;
  deleteCustomTemplate: (id: string) => void;
  getCustomTemplates: () => CustomTemplate[];
  runWorkflow: (dry: boolean) => Promise<void>;
  openConfirmWorkflow: () => void;
  /** Current serialized canvas, including viewport and derived edges. */
  getCanvasState: () => WorkspaceCanvasState;
  /** Built-in/custom template as a standalone canvas state (for new projects). */
  getTemplateCanvasState: (name: string) => WorkspaceCanvasState | null;
  /** Persist any pending debounced edit immediately. */
  flushSave: () => Promise<void>;
}

export type WorkspaceSaveState = "idle" | "saving" | "saved" | "error";

export interface CanvasPanelProps {
  /** Active workspace project (local canvas group). */
  workspaceProjectId?: string | null;
  /** Persisted canvas of the active project; hydrated once per project id. */
  workspaceCanvasState?: WorkspaceCanvasState | null;
  onWorkspaceSaveState?: (state: WorkspaceSaveState) => void;
  onWorkspaceSaved?: (projectId: string) => void;
  onStatsChange?: (stats: CanvasStats) => void;
  onToggleAssetDrawer?: () => void;
  assetDrawerOpen?: boolean;
  onTemplatesChange?: (templates: { id: string; name: string }[]) => void;
  onAssetGenerated?: () => void;
}

export const CanvasPanel = forwardRef<CanvasPanelHandle, CanvasPanelProps>(function CanvasPanel(
  props,
  ref,
) {
  const [graph, setGraph] = useState<Graph>(loadGraph);
  const limits = useLimits();
  const [view, setView] = useState<View>({ x: 40, y: 20, z: 1 });
  const [opts, setOpts] = useState<NodeMediaOptions | null>(null);
  const [linking, setLinking] = useState<{ id: string; kind: NodeType; side: "in" | "out" } | null>(null);
  const [previewMedia, setPreviewMedia] = useState<PreviewMediaItem | null>(null);
  const [deliveryOpen, setDeliveryOpen] = useState(false);

  const [toast, setToast] = useState<ToastInfo | null>(null);
  const [wfBusy, setWfBusy] = useState(false);
  const [canvasDrag, setCanvasDrag] = useState(false);
  const [drawerNodeId, setDrawerNodeId] = useState<string | null>(null);
  const [drawerSection, setDrawerSection] = useState<DrawerSection>("config");
  const [promptEditorNodeId, setPromptEditorNodeId] = useState<string | null>(null);
  /** Hover trên chip `#n` → tô sáng đúng edge + node nguồn. */
  const [focusLink, setFocusLink] = useState<{ from: string; to: string } | null>(null);
  /** Tooltip xem nhanh ảnh tham chiếu — toạ độ viewport (portal, không bị strip cắt). */
  const [hoverRef, setHoverRef] = useState<{
    src: CanvasNode;
    index: number;
    x: number;
    y: number;
  } | null>(null);
  const [aiGeneratingId, setAiGeneratingId] = useState<string | null>(null);
  const [jitPromptEnabled, setJitPromptEnabled] = useState<boolean>(true);
  const [skillsList, setSkillsList] = useState<{ id: string; name: string }[]>([]);
  // Thư viện ảnh sản phẩm của project (`out/items/<project_id>/`). Không phụ thuộc script.
  const [itemLibrary, setItemLibrary] = useState<LibraryItem[]>([]);
  const [confirmTarget, setConfirmTarget] = useState<
    { mode: "workflow" } | { mode: "node"; nodeId: string } | null
  >(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [marquee, setMarquee] = useState<Rect | null>(null);
  const [nodeHeights, setNodeHeights] = useState<Record<string, number>>({});
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    canvasX: number;
    canvasY: number;
  } | null>(null);

  const viewportRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const dragRef = useRef<
    | { kind: "pan"; sx: number; sy: number; ox: number; oy: number }
    | { kind: "node"; id: string; sx: number; sy: number; ox: number; oy: number }
    | { kind: "group"; id: string; sx: number; sy: number; origin: { id: string; x: number; y: number }[] }
    | { kind: "marquee"; sx: number; sy: number; cx: number; cy: number; additive: boolean; base: string[]; moved: boolean; keep: boolean }
    | null
  >(null);

  const nodes = graph.nodes;
  const groups = graph.groups;
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const groupsRef = useRef(groups);
  groupsRef.current = groups;
  const selectedRef = useRef(selectedIds);
  selectedRef.current = selectedIds;

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const heightRef = useRef<Record<string, number>>({});
  heightRef.current = nodeHeights;
  const spaceDownRef = useRef(false);

  const measureNode = useCallback((id: string, h: number) => {
    if (h <= 0) return;
    setNodeHeights((cur) => (Math.abs((cur[id] ?? 0) - h) < 1 ? cur : { ...cur, [id]: h }));
  }, []);


  const showToast = useCallback(
    (message: string, type: ToastInfo["type"] = "ok", nodeId?: string) => {
      const id = Date.now();
      setToast({ id, message, type, nodeId });
      window.setTimeout(() => setToast((cur) => (cur?.id === id ? null : cur)), 4200);
    },
    [],
  );

  // -- workspace persistence (debounced autosave + hydration) ---------------- //
  const workspaceProjectId = props.workspaceProjectId ?? null;
  const projectIdRef = useRef<string | null>(workspaceProjectId);
  projectIdRef.current = workspaceProjectId;
  const onSaveStateRef = useRef(props.onWorkspaceSaveState);
  onSaveStateRef.current = props.onWorkspaceSaveState;
  const onSavedRef = useRef(props.onWorkspaceSaved);
  onSavedRef.current = props.onWorkspaceSaved;

  const saveStateRef = useRef<WorkspaceSaveState>("idle");
  const saveTimerRef = useRef<number | null>(null);
  const dirtyRef = useRef(false);
  const lastSavedJsonRef = useRef<string>("");
  const hydratedProjectRef = useRef<string | null>(null);

  const emitSaveState = useCallback((state: WorkspaceSaveState) => {
    if (saveStateRef.current === state) return;
    saveStateRef.current = state;
    onSaveStateRef.current?.(state);
  }, []);

  const buildState = useCallback(
    () => graphToCanvasState(nodesRef.current, groupsRef.current, viewRef.current),
    [],
  );

  const persistNow = useCallback(
    async (pid: string, state: WorkspaceCanvasState) => {
      const json = JSON.stringify(state);
      emitSaveState("saving");
      try {
        await api.saveWorkspaceCanvas(pid, state);
        lastSavedJsonRef.current = json;
        dirtyRef.current = false;
        emitSaveState("saved");
        onSavedRef.current?.(pid);
      } catch {
        emitSaveState("error");
      }
    },
    [emitSaveState],
  );

  const flushSave = useCallback(async () => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const pid = projectIdRef.current;
    if (!pid) return;
    if (hydratedProjectRef.current !== pid) return;
    const state = buildState();
    if (JSON.stringify(state) === lastSavedJsonRef.current) return;
    await persistNow(pid, state);
  }, [buildState, persistNow]);

  // Hydrate during render so the committed graph always belongs to the active
  // project; an effect would leave one frame where a stale graph could be
  // autosaved into the newly selected project.
  const [hydratedPid, setHydratedPid] = useState<string | null>(null);
  if (
    workspaceProjectId &&
    props.workspaceCanvasState &&
    hydratedPid !== workspaceProjectId
  ) {
    const { graph: nextGraph, view: nextView } = canvasStateToGraph(props.workspaceCanvasState);
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    setGraph(nextGraph);
    setView(nextView);
    setHydratedPid(workspaceProjectId);
    hydratedProjectRef.current = workspaceProjectId;
    lastSavedJsonRef.current = JSON.stringify(
      graphToCanvasState(nextGraph.nodes, nextGraph.groups, nextView),
    );
    dirtyRef.current = false;
  }

  // Reset transient UI state once the new canvas is in place.
  useEffect(() => {
    if (!hydratedPid) return;
    setSelectedIds([]);
    setLinking(null);
    setContextMenu(null);
    setMarquee(null);
    setNodeHeights({});
    saveStateRef.current = "saved";
    onSaveStateRef.current?.("saved");
  }, [hydratedPid]);

  // Debounced autosave on any graph or viewport change.
  useEffect(() => {
    const pid = workspaceProjectId;
    if (!pid || !props.workspaceCanvasState) return;
    if (hydratedProjectRef.current !== pid) return;
    const state = buildState();
    const json = JSON.stringify(state);
    if (json === lastSavedJsonRef.current) {
      // Hydration or a no-op re-render: nothing to persist.
      dirtyRef.current = false;
      emitSaveState("saved");
      return;
    }
    dirtyRef.current = true;
    emitSaveState("saving");
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      const pidNow = projectIdRef.current;
      if (!pidNow || hydratedProjectRef.current !== pidNow) return;
      const latest = buildState();
      if (JSON.stringify(latest) === lastSavedJsonRef.current) {
        dirtyRef.current = false;
        emitSaveState("saved");
        return;
      }
      void persistNow(pidNow, latest);
    }, 800);
  }, [graph, view, workspaceProjectId, buildState, emitSaveState, persistNow]);

  // Last-chance save when the tab is hidden/closed or the panel unmounts.
  useEffect(() => {
    const flushBeacon = () => {
      const pid = projectIdRef.current;
      if (!pid || !dirtyRef.current) return;
      const state = buildState();
      const json = JSON.stringify(state);
      if (json === lastSavedJsonRef.current) return;
      lastSavedJsonRef.current = json;
      dirtyRef.current = false;
      api.saveWorkspaceCanvasBeacon(pid, state);
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushBeacon();
    };
    window.addEventListener("pagehide", flushBeacon);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", flushBeacon);
      document.removeEventListener("visibilitychange", onVisibility);
      flushBeacon();
    };
  }, [buildState]);

  // -- node options & agent skills ------------------------------------------ //
  useEffect(() => {
    api
      .nodeOptions()
      .then(setOpts)
      .catch(() => {
        /* fallback */
      });

    api
      .agentSkills()
      .then((res) => {
        if (res.skills) {
          setSkillsList(res.skills.map((s) => ({ id: s.id, name: s.name })));
        }
      })
      .catch(() => {});
  }, []);

  // Thư viện món đồ đổi theo project ⇒ nạp lại khi đổi project.
  useEffect(() => {
    api
      .itemLibrary(props.workspaceProjectId ?? null)
      .then((res) => setItemLibrary(res.items))
      .catch(() => {
        /* chưa có thư viện cũng chạy bình thường — chỉ mất danh sách gợi ý */
      });
  }, [props.workspaceProjectId]);

  const patchNode = useCallback((id: string, patch: Partial<CanvasNode>) => {
    if (nodesRef.current) {
      nodesRef.current = nodesRef.current.map((n) => (n.id === id ? { ...n, ...patch } : n));
    }
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    }));
  }, []);

  // -- background pan + node / group drag + marquee selection ---------------- //
  useEffect(() => {
    const toCanvas = (clientX: number, clientY: number) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      const v = viewRef.current;
      return {
        x: (clientX - (rect?.left ?? 0) - v.x) / v.z,
        y: (clientY - (rect?.top ?? 0) - v.y) / v.z,
      };
    };

    const move = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      if (d.kind === "pan") {
        setView((v) => ({ ...v, x: d.ox + (e.clientX - d.sx), y: d.oy + (e.clientY - d.sy) }));
        return;
      }
      if (d.kind === "marquee") {
        const p = toCanvas(e.clientX, e.clientY);
        d.cx = p.x;
        d.cy = p.y;
        const rect: Rect = {
          x: Math.min(d.sx, p.x),
          y: Math.min(d.sy, p.y),
          w: Math.abs(p.x - d.sx),
          h: Math.abs(p.y - d.sy),
        };
        if (rect.w > 3 || rect.h > 3) d.moved = true;
        setMarquee(rect);
        // Live preview: nodes intersecting the marquee.
        const hits = nodesRef.current
          .filter((n) => {
            const h = nodeHeight(n, heightRef.current);
            return !(
              n.x > rect.x + rect.w ||
              n.x + NODE_W < rect.x ||
              n.y > rect.y + rect.h ||
              n.y + h < rect.y
            );
          })
          .map((n) => n.id);
        setSelectedIds(d.additive ? Array.from(new Set([...d.base, ...hits])) : hits);
        return;
      }
      if (d.kind === "group") {
        const z = viewRef.current.z;
        const dx = (e.clientX - d.sx) / z;
        const dy = (e.clientY - d.sy) / z;
        const pos = new Map(d.origin.map((o) => [o.id, o]));
        setGraph((g) => ({
          ...g,
          nodes: g.nodes.map((n) => {
            const o = pos.get(n.id);
            return o ? { ...n, x: o.x + dx, y: o.y + dy } : n;
          }),
        }));
        return;
      }
      const z = viewRef.current.z;
      setGraph((g) => ({
        ...g,
        nodes: g.nodes.map((n) =>
          n.id === d.id
            ? { ...n, x: d.ox + (e.clientX - d.sx) / z, y: d.oy + (e.clientY - d.sy) / z }
            : n,
        ),
      }));
    };
    const up = () => {
      const d = dragRef.current;
      if (d?.kind === "marquee") {
        // A plain click (no meaningful drag) on empty canvas clears the selection.
        if (!d.moved && !d.keep) setSelectedIds([]);
        setMarquee(null);
      }
      dragRef.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  // -- wheel zoom (anchored at cursor, non-passive) --------------------------- //
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setContextMenu(null);
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setView((v) => {
        const z2 = clamp(v.z * (e.deltaY < 0 ? 1.12 : 0.89), 0.35, 1.8);
        const k = z2 / v.z;
        return { z: z2, x: mx - (mx - v.x) * k, y: my - (my - v.y) * k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // -- escape cancels linking, context menu, drawer, or clears the selection --- //
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (contextMenu) setContextMenu(null);
      else if (linking) setLinking(null);
      else if (drawerNodeId) setDrawerNodeId(null);
      else if (selectedRef.current.length > 0) setSelectedIds([]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [linking, drawerNodeId, contextMenu]);

  // -- close context menu on click outside ------------------------------------ //
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!contextMenu) return;
    const handlePointerDown = (e: PointerEvent) => {
      if (menuRef.current && menuRef.current.contains(e.target as Node)) {
        return;
      }
      setContextMenu(null);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [contextMenu]);

  // -- poll jobs for nodes with an active job --------------------------------- //
  const activeJobKey = nodes
    .filter((n) => n.jobId && ACTIVE.has(n.status))
    .map((n) => n.jobId)
    .join("|");

  useEffect(() => {
    if (!activeJobKey) return;
    let stop = false;
    const tick = async () => {
      try {
        const { jobs } = await api.jobs(100);
        if (stop) return;
        const map = new Map(jobs.map((j) => [j.id, j]));
        setGraph((g) => {
          let changed = false;
          const next = g.nodes.map((n) => {
            if (!n.jobId || !ACTIVE.has(n.status)) return n;
            const j = map.get(n.jobId);
            if (!j || j.state === n.status) return n;
            changed = true;
            return { ...n, ...jobPatch(n, j) };
          });
          return changed ? { ...g, nodes: next } : g;
        });
      } catch {
        /* transient */
      }
    };
    tick();
    const t = window.setInterval(tick, 1200);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
  }, [activeJobKey]);

  function jobPatch(n: CanvasNode, j: Job): Partial<CanvasNode> {
    const patch: Partial<CanvasNode> = { status: j.state as NodeStatus };
    const r = j.result as Record<string, unknown> | undefined;
    if (r) {
      const errDetail = r.hint
        ? `${r.reason ? `[${r.reason}] ` : ""}${r.hint}`
        : ((r.reason as string) ?? (r.detail as string) ?? null);
      if (n.type === "image" || n.type === "last_frame") {
        patch.fileUrl = (r.file_url as string) ?? null;
        patch.reason = errDetail;
      } else {
        patch.videoUrl = (r.video_url as string) ?? null;
        patch.frameUrl = (r.frame_url as string) ?? null;
        patch.reason = errDetail;
      }
      patch.elapsedS = (r.elapsed_s as number) ?? null;
      // run_id là thứ duy nhất nối được node → thư mục file thật khi xuất bộ dựng phim.
      if (typeof r.run_id === "string" && r.run_id) patch.runId = r.run_id;
      // Ảnh sản phẩm đã được server chép vào thư viện: tên file thật (đã slugify) có thể
      // khác chữ người dùng gõ, nên ghi lại để lần xuất sau không đẻ ra file thứ hai.
      if (typeof r.item_name === "string" && r.item_name) patch.itemName = r.item_name;
    }
    if (!patch.reason && j.error) patch.reason = j.error;
    return patch;
  }

  // -- run one node (submit + await terminal) --------------------------------- //
  const runNodeNow = useCallback(
    async (nodeId: string, dry: boolean): Promise<{ ok: boolean; fileUrl?: string | null }> => {
      const n = nodesRef.current.find((x) => x.id === nodeId);
      if (!n) return { ok: false };

      // Nút "Chạy node" trên thẻ đã bị `canRun` chặn prompt rỗng, nhưng workflow theo
      // nhóm và nút "Chạy lại" trong drawer gọi thẳng vào đây. Không chặn ở tầng này thì
      // request rỗng bay tới backend và quay về 422 "prompt: String should have at least
      // 1 character" — một lỗi trông như lỗi mạng, không chỉ ra được node nào.
      if (!dry && n.type !== "ref" && n.type !== "last_frame" && !n.prompt.trim()) {
        const reason = "Prompt đang rỗng — nhập prompt hoặc bấm AI Prompt trước khi chạy.";
        patchNode(nodeId, { status: "failed", reason });
        showToast(reason, "err", nodeId);
        return { ok: false };
      }

      patchNode(nodeId, { status: "queued", reason: null });
      try {
        if (n.type === "ref") return { ok: !!n.fileUrl, fileUrl: n.fileUrl };

        const srcRes = resolveSource(nodesRef.current, n, dry);
        if (!srcRes.ok) {
          patchNode(nodeId, { status: "failed", reason: srcRes.reason });
          showToast(`Lỗi node: ${srcRes.reason}`, "err", nodeId);
          return { ok: false };
        }

        let promise: Promise<{ job_id: string }>;
        if (n.type === "image") {
          promise = api.nodeImage({
            prompt: n.prompt.trim(),
            aspect_ratio: n.aspectRatio,
            seed: n.seed,
            reference_image_path: srcRes.url,
            reference_image_paths: srcRes.urls,
            project_id: undefined,
            workspace_project_id: props.workspaceProjectId ?? null,
            // Server chép ảnh vào `out/items/<project>/` ngay sau khi sinh xong — không
            // phải đợi tới lúc xuất bộ dựng phim mới copy tay.
            is_item: !!n.isItem,
            item_name: n.isItem ? n.itemName || n.label || n.id : undefined,
            dry_run: dry,
            confirm: !dry,
          });
        } else if (n.type === "video") {
          const framePath = srcRes.url;
          const autoImage = !framePath;
          promise = api.nodeVideo({
            prompt: n.prompt.trim(),
            aspect_ratio: n.videoRatio,
            frame_path: framePath,
            auto_image: autoImage,
            image_prompt: autoImage && n.autoImagePrompt.trim() ? n.autoImagePrompt.trim() : undefined,
            image_aspect_ratio: autoImage ? n.imageAspectRatio : undefined,
            seed: n.seed,
            resolution: n.resolution,
            project_id: undefined,
            workspace_project_id: props.workspaceProjectId ?? null,
            dry_run: dry,
            confirm: !dry,
          });
        } else {
          // last_frame
          if (dry) {
            patchNode(nodeId, { status: "succeeded", reason: null, elapsedS: 0 });
            return { ok: true, fileUrl: null };
          }
          if (!srcRes.url) {
            patchNode(nodeId, { status: "failed", reason: "Chưa có file video nguồn để trích xuất frame." });
            return { ok: false };
          }
          promise = api.nodeLastFrame({
            video_path: srcRes.url,
            remove_watermark: n.removeWatermark ?? true,
            workspace_project_id: props.workspaceProjectId ?? null,
          });
        }

        const { job_id } = await promise;
        patchNode(nodeId, { jobId: job_id, status: "queued" });

        // await terminal state
        let final: Job | null = null;
        for (;;) {
          const j = await api.job(job_id);
          if (TERMINAL.has(j.state)) {
            final = j;
            break;
          }
          patchNode(nodeId, { status: j.state === "running" ? "running" : "queued" });
          await new Promise((r) => setTimeout(r, 1200));
        }
        const patch = jobPatch(n, final);
        patchNode(nodeId, patch);
        Object.assign(n, patch);
        if (nodesRef.current) {
          nodesRef.current = nodesRef.current.map((x) => (x.id === nodeId ? { ...x, ...patch } : x));
        }
        const ok = final.state === "succeeded";
        if (ok && !dry) {
          props.onAssetGenerated?.();
        } else if (!ok && !dry) {
          const typeName =
            n.type === "image" ? "ảnh" : n.type === "video" ? "video" : "frame cuối";
          showToast(
            `Node ${typeName} thất bại: ${patch.reason ?? final.state}`,
            "err",
            nodeId,
          );
        }
        return { ok, fileUrl: patch.fileUrl };
      } catch (e) {
        const errText =
          e instanceof Error ? e.message : typeof e === "object" ? JSON.stringify(e) : String(e);
        patchNode(nodeId, {
          status: "failed",
          reason: errText,
        });
        showToast(errText || "Lỗi khi gửi job", "err", nodeId);
        return { ok: false };
      }
    },
    [patchNode, showToast],
  );

  // -- Local AI Prompt Agent generator ------------------------------------- //
  const handleGenerateAiPrompt = useCallback(
    async (nodeId: string) => {
      const current = nodesRef.current;
      const target = current.find((x) => x.id === nodeId);
      if (!target || (target.type !== "image" && target.type !== "video")) return;

      const sRes = resolveSource(current, target, false);
      const isCont = isVideoContinuation(current, target);

      setAiGeneratingId(nodeId);
      showToast("Local AI Agent đang phân tích ảnh nguồn để tạo prompt...", "info", nodeId);

      try {
        const res = await api.generateNodePrompt({
          node_id: target.id,
          node_type: target.type,
          upstream_media_urls: sRes.ok ? sRes.urls : [],
          skill_id: target.agentSkillId || undefined,
          custom_hint: target.agentCustomHint || undefined,
          is_video_continuation: isCont,
          // Ảnh sản phẩm ⇒ agent chọn skill cutout, và tên món là ngữ cảnh duy nhất khi
          // node chưa gắn ảnh tham chiếu.
          is_item: !!target.isItem,
          item_name: target.isItem ? target.itemName || undefined : undefined,
          item_scope: target.isItem ? target.itemScope ?? undefined : undefined,
        });

        if (res.ok && res.prompt) {
          patchNode(nodeId, { prompt: res.prompt });
          showToast(`Đã tối ưu prompt bằng ${res.agent.toUpperCase()} (${res.elapsed_s}s)`, "ok", nodeId);
        } else {
          showToast("AI Agent không tạo được prompt.", "err", nodeId);
        }
      } catch (err: any) {
        showToast(`Lỗi AI Agent: ${err?.message || err}`, "err", nodeId);
      } finally {
        setAiGeneratingId(null);
      }
    },
    [patchNode, showToast],
  );

  // Run id của từng clip trong script, suy từ node canvas theo template chuẩn.
  // Nối bằng id node (không đoán theo thứ tự) để đổi template vẫn ra đúng cặp.
  const deliveryRuns = useMemo<Record<string, string | null | undefined>>(() => {
    const byNodeId = new Map(nodes.map((n) => [n.id, n]));
    return {
      clip1: byNodeId.get("lb_video_1")?.runId ?? null,
      clip2: byNodeId.get("lb_video_2")?.runId ?? null,
    };
  }, [nodes]);

  // Ảnh sản phẩm đã sinh: node ảnh nào tick `isItem` và đã có run thì đưa vào bộ dựng phim.
  // Không cần khớp `items[]` của script — tên file lấy từ `itemName` người dùng đặt.
  const deliveryItems = useMemo<DeliveryItemRef[]>(() => {
    return nodes
      .filter((n) => n.type === "image" && n.isItem && !!n.runId)
      .map((n) => ({
        name: n.itemName || n.label || n.id,
        run_id: n.runId as string,
      }));
  }, [nodes]);

  // -- run whole workflow (per group, isolated failure) ------------------------- //
  // Each Visual Group is an independent execution unit. A node failure aborts
  // only the unit that owns it; the following units still run from scratch.
  const runWorkflow = useCallback(
    async (dry: boolean) => {
      if (wfBusy) return;
      setWfBusy(true);
      setConfirmTarget(null);
      try {
        const current = nodesRef.current;
        const units = buildRunUnits(current, groupsRef.current, selectedRef.current);

        if (units.length === 0) {
          showToast("Không có node nào để chạy.", "err");
          return;
        }

        const srcOk = new Map<string, boolean>();
        for (const n of current.filter((x) => x.type === "ref")) srcOk.set(n.id, !!n.fileUrl);

        const executable = units.reduce((acc, u) => acc + unitMembers(current, u).length, 0);
        if (executable === 0) {
          showToast("Không có node ảnh/video nào để chạy.", "err");
          return;
        }

        const aborted: string[] = [];

        for (const unit of units) {
          const members = unitMembers(current, unit);
          if (members.length === 0) continue;

          if (units.length > 1) {
            showToast(`▶ Bắt đầu ${unit.name} (${members.length} node)`, "info", members[0].id);
          }

          let unitFailed = false;
          for (const item of members) {
            const n = nodesRef.current.find((x) => x.id === item.id) || item;

            if (unitFailed) {
              patchNode(n.id, {
                status: "skipped",
                reason: `Đã hủy vì ${unit.name} gặp lỗi trước đó.`,
              });
              srcOk.set(n.id, false);
              continue;
            }

            const sids = getNodeSourceIds(n);
            if (sids.some((sid) => srcOk.get(sid) === false)) {
              patchNode(n.id, {
                status: "skipped",
                reason: "Node nguồn không thành công — bỏ qua node này.",
              });
              srcOk.set(n.id, false);
              continue;
            }

            // Dynamic JIT prompt generation before running
            if (!dry && jitPromptEnabled && (n.type === "image" || n.type === "video")) {
              const sRes = resolveSource(nodesRef.current, n, false);
              if (sRes.ok && sRes.urls.length > 0) {
                setAiGeneratingId(n.id);
                try {
                  showToast(`JIT Agent: Đang phân tích kết quả node trước để tối ưu prompt...`, "info", n.id);
                  const aiRes = await api.generateNodePrompt({
                    node_id: n.id,
                    node_type: n.type,
                    upstream_media_urls: sRes.ok ? sRes.urls : [],
                    skill_id: n.agentSkillId || undefined,
                    custom_hint: n.agentCustomHint || undefined,
                    is_video_continuation: isVideoContinuation(nodesRef.current, n),
                    // Thiếu 2 trường này thì JIT chọn skill lookbook thay vì skill cutout,
                    // và prompt sinh ra lại đi vẽ người mẫu cho node ảnh sản phẩm.
                    is_item: !!n.isItem,
                    item_name: n.isItem ? n.itemName || undefined : undefined,
                    item_scope: n.isItem ? n.itemScope ?? undefined : undefined,
                  });
                  if (aiRes.ok && aiRes.prompt) {
                    patchNode(n.id, { prompt: aiRes.prompt });
                    n.prompt = aiRes.prompt;
                    item.prompt = aiRes.prompt;
                  }
                } catch (e: any) {
                  console.warn("Lỗi sinh prompt JIT, tiếp tục với prompt sẵn có:", e);
                } finally {
                  setAiGeneratingId(null);
                }
              }
            }

            const r = await runNodeNow(n.id, dry);
            srcOk.set(n.id, r.ok);
            if (!r.ok && !dry) {
              unitFailed = true;
              aborted.push(unit.name);
              showToast(
                `Dừng ${unit.name}: node lỗi. Chuyển sang nhóm tiếp theo.`,
                "err",
                n.id,
              );
            }
          }
        }

        if (aborted.length > 0) {
          showToast(
            dry
              ? "Dry-run hoàn tất."
              : `Workflow kết thúc — ${aborted.length} nhóm bị dừng: ${aborted.join(", ")}.`,
            "err",
          );
        } else {
          showToast(dry ? "Dry-run workflow hoàn tất." : "Workflow hoàn tất!", "ok");
        }
      } finally {
        setWfBusy(false);
      }
    },
    [wfBusy, jitPromptEnabled, runNodeNow, patchNode, showToast],
  );

  // -- node / edge actions ----------------------------------------------------- //
  const addNodeAt = (type: NodeType, cx: number, cy: number) => {
    const node = newNode(type, opts, cx, cy);
    setGraph((g) => ({
      ...g,
      nodes: [...g.nodes, node],
    }));
    setContextMenu(null);
    const label =
      type === "ref"
        ? "Ảnh tham chiếu"
        : type === "image"
          ? "Node Ảnh"
          : type === "video"
            ? "Node Video"
            : "Frame Cuối";
    showToast(`Đã thêm ${label}`, "ok");
  };

  const addNode = (type: NodeType) => {
    const v = viewRef.current;
    const cx = Math.round((-v.x + window.innerWidth / 2 - 140) / v.z);
    const cy = Math.round((-v.y + window.innerHeight / 2 - 100) / v.z);
    addNodeAt(type, cx, cy);
  };

  const removeNode = (id: string) => {
    setGraph((g) => ({
      ...g,
      nodes: g.nodes
        .filter((n) => n.id !== id)
        .map((n) => {
          const sids = getNodeSourceIds(n).filter((sid) => sid !== id);
          return {
            ...n,
            sourceImageId: sids[0] ?? null,
            sourceImageIds: sids,
          };
        }),
      groups: g.groups
        .map((gr) => ({ ...gr, nodeIds: gr.nodeIds.filter((nid) => nid !== id) }))
        .filter((gr) => gr.nodeIds.length > 0),
    }));
    setSelectedIds((cur) => cur.filter((nid) => nid !== id));
    if (linking?.id === id) setLinking(null);
    if (drawerNodeId === id) setDrawerNodeId(null);
  };

  // -- selection -------------------------------------------------------------- //
  const toggleSelect = useCallback((id: string, additive: boolean) => {
    setSelectedIds((cur) => {
      if (!additive) return cur.length === 1 && cur[0] === id ? [] : [id];
      return cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    });
  }, []);

  const selectGroup = useCallback((groupId: string) => {
    const g = groupsRef.current.find((x) => x.id === groupId);
    if (!g) return;
    setSelectedIds(g.nodeIds);
  }, []);

  // -- group actions ---------------------------------------------------------- //
  const createGroupFromSelection = useCallback(() => {
    const sel = selectedRef.current;
    if (sel.length === 0) {
      showToast("Chọn node trước (Shift + click hoặc quét chuột) để tạo nhóm.", "err");
      return;
    }
    const existing = groupsRef.current;
    const taken = new Set(existing.flatMap((g) => g.nodeIds));
    const ids = sel.filter((id) => !taken.has(id));
    if (ids.length === 0) {
      showToast("Các node đã chọn đều thuộc nhóm khác — giải tán nhóm cũ trước.", "err");
      return;
    }
    const group: CanvasGroup = {
      id: nextId("group"),
      name: `Nhóm ${existing.length + 1}`,
      nodeIds: ids,
      color: GROUP_COLORS[existing.length % GROUP_COLORS.length],
    };
    setGraph((g) => ({ ...g, groups: [...g.groups, group] }));
    setEditingGroupId(group.id);
    showToast(`Đã tạo "${group.name}" gồm ${ids.length} node.`, "ok");
  }, [showToast]);

  const renameGroup = useCallback((groupId: string, name: string) => {
    setGraph((g) => ({
      ...g,
      groups: g.groups.map((gr) => (gr.id === groupId ? { ...gr, name } : gr)),
    }));
  }, []);

  const dissolveGroup = useCallback(
    (groupId: string) => {
      const g = groupsRef.current.find((x) => x.id === groupId);
      setGraph((cur) => ({ ...cur, groups: cur.groups.filter((gr) => gr.id !== groupId) }));
      if (g) showToast(`Đã giải tán "${g.name}".`, "info");
    },
    [showToast],
  );

  const addSelectionToGroup = useCallback(
    (groupId: string) => {
      const sel = new Set(selectedRef.current);
      if (sel.size === 0) {
        showToast("Chưa chọn node nào để thêm vào nhóm.", "err");
        return;
      }
      const target = groupsRef.current.find((gr) => gr.id === groupId);
      if (!target) return;
      const added = Array.from(sel).filter((id) => !target.nodeIds.includes(id)).length;
      setGraph((g) => ({
        ...g,
        groups: g.groups
          .map((gr) => {
            if (gr.id !== groupId) {
              // Nodes can only belong to one group.
              return { ...gr, nodeIds: gr.nodeIds.filter((id) => !sel.has(id)) };
            }
            return { ...gr, nodeIds: Array.from(new Set([...gr.nodeIds, ...sel])) };
          })
          .filter((gr) => gr.nodeIds.length > 0),
      }));
      showToast(added > 0 ? `Đã thêm ${added} node vào nhóm.` : "Các node này đã ở trong nhóm.", "ok");
    },
    [showToast],
  );

  const removeFromGroup = useCallback(
    (groupId: string) => {
      const sel = new Set(selectedRef.current);
      if (sel.size === 0) return;
      setGraph((g) => ({
        ...g,
        groups: g.groups
          .map((gr) =>
            gr.id === groupId
              ? { ...gr, nodeIds: gr.nodeIds.filter((id) => !sel.has(id)) }
              : gr,
          )
          .filter((gr) => gr.nodeIds.length > 0),
      }));
      showToast("Đã bỏ node khỏi nhóm.", "info");
    },
    [showToast],
  );

  const openDrawer = useCallback((id: string, section: DrawerSection = "config") => {
    setDrawerSection(section);
    setDrawerNodeId(id);
  }, []);

  // -- Ctrl/Cmd+G groups the current selection ------------------------------- //
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "g") {
        e.preventDefault();
        createGroupFromSelection();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [createGroupFromSelection]);

  // -- hold Space to pan the canvas (drag on empty canvas selects instead) ---- //
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      spaceDownRef.current = true;
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") spaceDownRef.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  const uploadRef = useCallback(
    async (id: string, file: File) => {
      if (!file.type.startsWith("image/")) {
        showToast("Chỉ nhận file ảnh (PNG/JPG/WebP).", "err");
        return;
      }
      patchNode(id, { reason: null, status: "queued" });
      try {
        const r = await api.upload(file, props.workspaceProjectId ?? null);
        patchNode(id, { fileUrl: r.url, fileName: file.name, status: "succeeded", reason: null });
        props.onAssetGenerated?.();
      } catch (e) {
        patchNode(id, {
          status: "failed",
          reason: e instanceof Error ? e.message : "Upload thất bại",
        });
        showToast("Upload ảnh tham chiếu thất bại.", "err", id);
      }
    },
    [patchNode, showToast, props.workspaceProjectId],
  );

  const addReferenceNode = useCallback(
    (url: string, fileName?: string) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      const v = viewRef.current;
      const w = rect?.width ?? 800;
      const h = rect?.height ?? 600;
      const gx = (w / 2 - v.x) / v.z;
      const gy = (h / 2 - v.y) / v.z;
      const offset = (Math.random() - 0.5) * 60;
      const node = newNode("ref", opts, gx - NODE_W / 2 + offset, gy - 60 + offset);
      node.fileName = fileName || url.split("/").pop() || "Ảnh tham chiếu";
      node.fileUrl = url;
      node.status = "succeeded";
      setGraph((g) => ({ ...g, nodes: [...g.nodes, node] }));
      showToast(`Đã thêm "${node.fileName}" vào Canvas`, "ok");
    },
    [opts, showToast],
  );

  const dropFiles = (e: React.DragEvent) => {
    e.preventDefault();
    setCanvasDrag(false);
    const customAsset = e.dataTransfer.getData("application/flow-asset");
    if (customAsset) {
      try {
        const parsed = JSON.parse(customAsset);
        const rect = viewportRef.current?.getBoundingClientRect();
        const v = viewRef.current;
        const gx = (e.clientX - (rect?.left ?? 0) - v.x) / v.z;
        const gy = (e.clientY - (rect?.top ?? 0) - v.y) / v.z;
        const node = newNode("ref", opts, gx - NODE_W / 2, gy - 40);
        node.fileName = parsed.name || "Ảnh tham chiếu";
        node.fileUrl = parsed.url;
        node.status = "succeeded";
        setGraph((g) => ({ ...g, nodes: [...g.nodes, node] }));
        showToast(`Đã thêm "${node.fileName}" vào Canvas`, "ok");
        return;
      } catch {
        /* fallback to files */
      }
    }
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) {
      showToast("Chỉ nhận file ảnh (PNG/JPG/WebP).", "err");
      return;
    }
    const rect = viewportRef.current?.getBoundingClientRect();
    const v = viewRef.current;
    const gx = (e.clientX - (rect?.left ?? 0) - v.x) / v.z;
    const gy = (e.clientY - (rect?.top ?? 0) - v.y) / v.z;
    const created = files.map((f, i) => {
      const node = newNode("ref", opts, gx - NODE_W / 2 + i * 30, gy - 40 + i * 30);
      node.fileName = f.name;
      return { node, file: f };
    });
    setGraph((g) => ({ ...g, nodes: [...g.nodes, ...created.map((c) => c.node)] }));
    for (const c of created) void uploadRef(c.node.id, c.file);
  };

  const handleDotClick = (n: CanvasNode, side: "in" | "out") => {
    if (linking) {
      if (linking.id === n.id) {
        setLinking(null);
        return;
      }
      const first = nodes.find((x) => x.id === linking.id);
      if (!first || linking.side === side) {
        showToast("Nối chấm ra (phải) của node nguồn với chấm vào (trái) của node đích.", "err");
        setLinking(null);
        return;
      }
      const src = linking.side === "out" ? first : n;
      const dst = linking.side === "out" ? n : first;

      if (dst.type === "ref") {
        showToast("Node ảnh tham chiếu không nhận đầu vào.", "err");
      } else if (src.type === "video" && dst.type !== "last_frame") {
        showToast("Node Video chỉ có thể nối ra node Frame Cuối (để trích xuất ảnh nối tiếp).", "err");
      } else if (dst.type === "last_frame" && src.type !== "video") {
        showToast("Node Frame Cuối chỉ nhận đầu vào từ node Video.", "err");
      } else if (isDownstream(nodes, dst.id, src.id)) {
        showToast("Không thể nối vòng lặp.", "err");
      } else {
        if (dst.type === "image") {
          const currentSids = getNodeSourceIds(dst);
          if (currentSids.includes(src.id)) {
            showToast("Node này đã được nối làm ảnh tham chiếu.", "info");
          } else {
            const nextSids = [...currentSids, src.id];
            patchNode(dst.id, {
              sourceImageIds: nextSids,
              sourceImageId: nextSids[0],
              status: "idle",
              reason: null,
            });
            showToast(`Đã nối thêm ảnh tham chiếu (${nextSids.length} ảnh) → node ảnh.`, "ok");
          }
        } else {
          patchNode(dst.id, { sourceImageId: src.id, sourceImageIds: [src.id], status: "idle", reason: null });
          const dstLabel = dst.type === "video" ? "node video" : "node frame cuối";
          showToast(`Đã nối → ${dstLabel}.`, "ok");
        }
      }
      setLinking(null);
      return;
    }
    setLinking({ id: n.id, kind: n.type, side });
  };

  // -- edges ------------------------------------------------------------------- //
  const edges = useMemo(() => {
    const list: { from: CanvasNode; to: CanvasNode }[] = [];
    for (const v of nodes) {
      if (v.type === "ref") continue;
      const sids = getNodeSourceIds(v);
      for (const sid of sids) {
        const src = nodes.find((n) => n.id === sid);
        if (src) list.push({ from: src, to: v });
      }
    }
    return list;
  }, [nodes]);

  const imageNodes = nodes.filter((n) => n.type === "image");
  const videoNodes = nodes.filter((n) => n.type === "video");
  const lastFrameNodes = nodes.filter((n) => n.type === "last_frame");
  const jobNodes = nodes.filter((n) => n.type !== "ref");
  const nRunning = jobNodes.filter((n) => ACTIVE.has(n.status)).length;
  const nDone = jobNodes.filter((n) => n.status === "succeeded").length;
  const nPending = jobNodes.filter(
    (n) => n.status === "idle" || n.status === "failed" || n.status === "rejected",
  ).length;

  const imageRatios = Object.keys(opts?.image.aspect_ratios ?? { "16:9": 3 });
  const verifiedRatios = new Set(opts?.image.verified_aspect_ratios ?? ["16:9"]);
  const videoRatios = opts?.video.aspect_ratios ?? ["9:16", "16:9"];
  const resolutions = opts?.video.resolutions ?? ["1080p", "720p"];

  const drawerNode = nodes.find((n) => n.id === drawerNodeId) ?? null;
  const promptEditorNode = nodes.find((n) => n.id === promptEditorNodeId) ?? null;

  // Execution plan preview for the confirm modal + TopBar.
  const runUnits = useMemo(
    () => buildRunUnits(nodes, groups, selectedIds),
    [nodes, groups, selectedIds],
  );

  const [customTemplates, setCustomTemplates] = useState<CustomTemplate[]>(() => {
    try {
      const raw = localStorage.getItem(TEMPLATES_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  const onTemplatesChange = props.onTemplatesChange;
  useEffect(() => {
    onTemplatesChange?.(customTemplates.map((t) => ({ id: t.id, name: t.name })));
  }, [customTemplates, onTemplatesChange]);

  const saveCurrentTemplate = useCallback(
    (name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      try {
        const newTpl: CustomTemplate = {
          id: `custom_tpl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          name: trimmed,
          createdAt: Date.now(),
          nodes: graph.nodes,
          groups: graph.groups || [],
        };
        const updated = [newTpl, ...customTemplates.filter((x) => x.name.toLowerCase() !== trimmed.toLowerCase())];
        setCustomTemplates(updated);
        localStorage.setItem(TEMPLATES_KEY, JSON.stringify(updated));
        showToast(`Đã lưu Mẫu Template: "${trimmed}"`, "ok");
      } catch (err: any) {
        showToast(`Lỗi lưu template: ${err?.message || err}`, "err");
      }
    },
    [graph.nodes, graph.groups, customTemplates, showToast],
  );

  const deleteCustomTemplate = useCallback(
    (id: string) => {
      const updated = customTemplates.filter((x) => x.id !== id);
      setCustomTemplates(updated);
      localStorage.setItem(TEMPLATES_KEY, JSON.stringify(updated));
      showToast("Đã xóa Mẫu Template.", "info");
    },
    [customTemplates, showToast],
  );

  const resolveTemplateGraph = useCallback(
    (nameOrId: string): { nodes: CanvasNode[]; groups: CanvasGroup[]; label: string } | null => {
      if (nameOrId === "tryon") {
        return {
          nodes: createTryOnTemplate(),
          groups: [
            {
              id: "tryon_group_image",
              name: "Nhóm 1: Sinh ảnh Lookbook",
              nodeIds: ["tryon_ref_model", "tryon_ref_garment", "tryon_node_image"],
              color: GROUP_COLORS[0],
            },
            {
              id: "tryon_group_video",
              name: "Nhóm 2: Render Video Try-on",
              nodeIds: ["tryon_node_video_1", "tryon_node_last_frame", "tryon_node_video_2"],
              color: GROUP_COLORS[1],
            },
          ],
          label: "Video Thử Đồ (Try-On 16s)",
        };
      }

      if (nameOrId === "lookbook_8s") {
        // Template chỉ cấp MỘT node cutout mẫu: người bán có bao nhiêu món cũng nhân bản
        // node rồi đặt tên, không phải khai danh sách món vào script.
        const tpl = createLookbook8sTemplate();
        return { ...tpl, label: "Lookbook 16s (Plate → Video 1 → Video 2)" };
      }

      const custom = customTemplates.find((x) => x.id === nameOrId || x.name === nameOrId);
      if (custom && Array.isArray(custom.nodes)) {
        return { nodes: custom.nodes, groups: custom.groups || [], label: custom.name };
      }
      return null;
    },
    [customTemplates],
  );

  const loadTemplate = useCallback(
    (nameOrId: string) => {
      const tpl = resolveTemplateGraph(nameOrId);
      if (!tpl) {
        showToast("Không tìm thấy mẫu template.", "err");
        return;
      }
      setGraph({ nodes: tpl.nodes, groups: tpl.groups });
      setSelectedIds([]);
      setView({ x: 30, y: 20, z: 0.72 });
      showToast(`Đã khởi tạo Mẫu: ${tpl.label}`, "ok");
    },
    [resolveTemplateGraph, showToast],
  );

  useImperativeHandle(
    ref,
    () => {
      const handle: CanvasPanelHandle = {
        addNode,
        addReferenceNode,
        loadTemplate,
        saveCurrentTemplate,
        deleteCustomTemplate,
        getCustomTemplates: () => customTemplates,
        runWorkflow,
        openConfirmWorkflow: () => setConfirmTarget({ mode: "workflow" }),
        getCanvasState: () => buildState(),
        getTemplateCanvasState: (name: string) => {
          const tpl = resolveTemplateGraph(name);
          if (!tpl) return null;
          return graphToCanvasState(tpl.nodes, tpl.groups, { x: 30, y: 20, z: 0.72 });
        },
        flushSave,
      };
      if (typeof window !== "undefined") (window as any).__canvas = handle;
      return handle;
    },
    [
      addNode,
      addReferenceNode,
      loadTemplate,
      saveCurrentTemplate,
      deleteCustomTemplate,
      customTemplates,
      runWorkflow,
      buildState,
      resolveTemplateGraph,
      flushSave,
    ],
  );

  const onStatsChange = props.onStatsChange;
  useEffect(() => {
    onStatsChange?.({
      imageCount: imageNodes.length,
      videoCount: videoNodes.length,
      lastFrameCount: lastFrameNodes.length,
      nRunning,
      nDone,
      nPending,
      groupCount: groups.length,
      selectedCount: selectedIds.length,
      wfBusy,
      linking: !!linking,
    });
  }, [
    imageNodes.length,
    videoNodes.length,
    lastFrameNodes.length,
    nRunning,
    nDone,
    nPending,
    groups.length,
    selectedIds.length,
    wfBusy,
    linking,
    onStatsChange,
  ]);

  return (
    <div className="flex flex-col w-full h-full relative overflow-hidden">
      {/* Toast Notification with Click-to-Open-Drawer */}
      {toast && (
        <div className="fixed top-16 right-5 z-40 flex items-center gap-2.5 rounded-ctl border border-line2 bg-panel px-4 py-3 shadow-2xl backdrop-blur-md text-[12.5px] animate-in fade-in slide-in-from-top-2">
          <span
            className={`size-2 rounded-full shrink-0 ${
              toast.type === "ok" ? "bg-ok" : toast.type === "err" ? "bg-err" : "bg-acc"
            }`}
          />
          <span className="font-medium text-fg max-w-[340px] truncate">{toast.message}</span>
          {toast.nodeId && (
            <button
              onClick={() => {
                setDrawerNodeId(toast.nodeId!);
                setToast(null);
              }}
              className="px-2 py-0.5 rounded text-[11px] font-bold text-acc bg-acc/10 hover:bg-acc/20 transition-colors cursor-pointer shrink-0"
            >
              Xem log →
            </button>
          )}
          <button
            onClick={() => setToast(null)}
            className="ml-1 text-mut hover:text-fg cursor-pointer shrink-0"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Linking Helper Bar */}
      {linking && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-acc/40 bg-panel/95 backdrop-blur-md text-[12px] text-acc shadow-lg select-none">
          <LinkSimple size={14} className="animate-pulse" />
          <span>
            Đang nối: bấm vào chấm đối diện để liên kết (Nhấn{" "}
            <kbd className="font-mono bg-panel2 px-1 rounded text-[11px]">Esc</kbd> để hủy)
          </span>
        </div>
      )}

      {/* Canvas Viewport */}
      <div
        ref={viewportRef}
        className={`relative w-full h-full flex-1 bg-ink overflow-hidden select-none ${
          canvasDrag ? "border-2 border-acc" : ""
        }`}
        onContextMenu={(e) => {
          e.preventDefault();
          const t = e.target as HTMLElement;
          if (t.closest("button, select, input, textarea, a, video, .canvas-node-card")) return;
          const rect = viewportRef.current?.getBoundingClientRect();
          if (!rect) return;
          const relX = e.clientX - rect.left;
          const relY = e.clientY - rect.top;
          const v = viewRef.current;
          const gx = Math.round((relX - v.x) / v.z);
          const gy = Math.round((relY - v.y) / v.z);
          setContextMenu({
            x: e.clientX,
            y: e.clientY,
            canvasX: gx,
            canvasY: gy,
          });
        }}
        onDragOver={(e) => {
          if (!Array.from(e.dataTransfer.types).includes("Files")) return;
          e.preventDefault();
          setCanvasDrag(true);
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setCanvasDrag(false);
        }}
        onDrop={dropFiles}
        style={{
          backgroundImage: "radial-gradient(var(--color-line2) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
        }}
        onPointerDown={(e) => {
          if (contextMenu) setContextMenu(null);
          const t = e.target as HTMLElement;
          if (t.closest("button, select, input, textarea, a, video")) return;
          setLinking(null);

          const toCanvas = (clientX: number, clientY: number) => {
            const rect = viewportRef.current?.getBoundingClientRect();
            const v = viewRef.current;
            return {
              x: (clientX - (rect?.left ?? 0) - v.x) / v.z,
              y: (clientY - (rect?.top ?? 0) - v.y) / v.z,
            };
          };

          // Middle button or Space+drag pans the canvas; left drag on empty
          // canvas sweeps a selection rectangle (Shift = additive).
          if (e.button === 1 || spaceDownRef.current) {
            e.preventDefault();
            dragRef.current = { kind: "pan", sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
            return;
          }
          if (e.button !== 0) return;

          const p = toCanvas(e.clientX, e.clientY);
          const additive = e.shiftKey;
          dragRef.current = {
            kind: "marquee",
            sx: p.x,
            sy: p.y,
            cx: p.x,
            cy: p.y,
            additive,
            base: additive ? selectedRef.current : [],
            moved: false,
            keep: false,
          };
          if (!additive) setSelectedIds([]);
          setMarquee({ x: p.x, y: p.y, w: 0, h: 0 });
        }}
      >
        {/* Selection / group toolbar */}
        <div className="absolute left-3 top-3 z-20 flex flex-col gap-1.5">
          {selectedIds.length > 0 && (
            <div className="flex items-center gap-1.5 rounded-ctl border border-acc/45 bg-panel/95 backdrop-blur-md px-2.5 py-1.5 shadow-lg text-[11.5px]">
              <span className="font-bold text-acc">{selectedIds.length} node chọn</span>
              <span className="h-3.5 w-px bg-line2" />
              <button
                type="button"
                onClick={createGroupFromSelection}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-[6px] bg-acc text-accink font-bold hover:bg-acc2 cursor-pointer"
                title="Tạo nhóm từ node đã chọn (Ctrl+G)"
              >
                <Plus size={11} weight="bold" />
                Tạo nhóm
              </button>
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) addSelectionToGroup(e.target.value);
                  e.currentTarget.value = "";
                }}
                className="text-[11px] bg-panel2 border border-line2 rounded-[6px] px-1.5 py-1 text-dim cursor-pointer"
                title="Thêm node đã chọn vào nhóm có sẵn"
              >
                <option value="">Thêm vào nhóm…</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              {groups.some((g) => g.nodeIds.some((id) => selectedIds.includes(id))) && (
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) removeFromGroup(e.target.value);
                    e.currentTarget.value = "";
                  }}
                  className="text-[11px] bg-panel2 border border-line2 rounded-[6px] px-1.5 py-1 text-dim cursor-pointer"
                  title="Bỏ node đã chọn khỏi nhóm"
                >
                  <option value="">Bỏ khỏi nhóm…</option>
                  {groups
                    .filter((g) => g.nodeIds.some((id) => selectedIds.includes(id)))
                    .map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                      </option>
                    ))}
                </select>
              )}
              <button
                type="button"
                onClick={() => setSelectedIds([])}
                className="text-mut hover:text-fg cursor-pointer"
                title="Bỏ chọn (Esc)"
              >
                <X size={12} />
              </button>
            </div>
          )}

          {groups.length === 0 && selectedIds.length === 0 && nodes.length > 0 && (
            <div className="text-[10.5px] text-mut bg-panel/85 border border-line rounded-ctl px-2.5 py-1.5 max-w-[300px] leading-relaxed">
              Kéo chuột trên nền để <strong className="text-fg">quét chọn</strong> node · Giữ{" "}
              <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Shift</kbd> + click để chọn
              từng node · Ctrl+G để gom nhóm.
            </div>
          )}
        </div>

        {/* Xuất bộ dựng phim — gom file thật vào một thư mục cho HyperFrames desktop */}
        <button
          type="button"
          onClick={() => setDeliveryOpen(true)}
          className="absolute right-3 top-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-ctl border border-line2 bg-panel/90 backdrop-blur-md text-[12px] font-semibold text-dim hover:text-fg hover:border-acc/60 hover:bg-panel2 shadow-lg transition-all cursor-pointer group"
          title="Xuất plate + clip + cutout thành thư mục cho HyperFrames desktop"
        >
          <DownloadSimple size={15} weight="bold" className="text-acc group-hover:scale-110 transition-transform" />
          <span>Xuất bộ dựng phim</span>
        </button>

        {/* Floating Left Assets Drawer Toggle */}
        {props.onToggleAssetDrawer && !props.assetDrawerOpen && (
          <button
            type="button"
            onClick={props.onToggleAssetDrawer}
            className="absolute left-3 top-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-ctl border border-line2 bg-panel/90 backdrop-blur-md text-[12px] font-semibold text-dim hover:text-fg hover:border-acc/60 hover:bg-panel2 shadow-lg transition-all cursor-pointer group"
            title="Mở Kho Assets [Phím tắt: A]"
          >
            <FolderSimple size={15} weight="bold" className="text-acc group-hover:scale-110 transition-transform" />
            <span>Kho Assets</span>
            <span className="text-[10px] text-mut font-mono bg-panel2 px-1 rounded">A</span>
          </button>
        )}

        {/* Zoom Controls */}
        <div className="absolute left-3 bottom-3 z-20 flex items-center gap-1.5">
          <button
            onClick={() => setView((v) => ({ ...v, z: clamp(v.z * 1.15, 0.35, 1.8) }))}
            className="grid place-items-center size-8 rounded-ctl border border-line2 bg-panel text-dim hover:text-fg cursor-pointer"
            title="Phóng to"
          >
            <MagnifyingGlassPlus size={15} />
          </button>
          <button
            onClick={() => setView((v) => ({ ...v, z: clamp(v.z * 0.87, 0.35, 1.8) }))}
            className="grid place-items-center size-8 rounded-ctl border border-line2 bg-panel text-dim hover:text-fg cursor-pointer"
            title="Thu nhỏ"
          >
            <MagnifyingGlassMinus size={15} />
          </button>
          <button
            onClick={() => setView({ x: 40, y: 20, z: 1 })}
            className="grid place-items-center size-8 rounded-ctl border border-line2 bg-panel text-dim hover:text-fg cursor-pointer"
            title="Về khung mặc định"
          >
            <ArrowsCounterClockwise size={15} />
          </button>
          <span className="text-[11px] font-mono text-mut px-1">{Math.round(view.z * 100)}%</span>
        </div>

        <div className="absolute right-3 bottom-3 z-20 text-[10.5px] text-mut bg-panel/85 border border-line rounded-ctl px-2.5 py-1.5 max-w-[340px] leading-relaxed">
          Kéo nền để <strong className="text-fg">quét chọn</strong> ·{" "}
          <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Shift</kbd>+click chọn từng
          node · Giữ <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Space</kbd> hoặc
          chuột giữa để <strong className="text-fg">di chuyển canvas</strong>.
        </div>

        {canvasDrag && (
          <div className="absolute inset-0 z-30 grid place-items-center bg-acc/5 pointer-events-none">
            <span className="text-[13px] font-semibold text-acc">Thả ảnh để tạo node Ảnh tham chiếu</span>
          </div>
        )}
        {nodes.length === 0 && (
          <div className="absolute inset-0 grid place-items-center pointer-events-none">
            <div className="flex flex-col items-center gap-2 text-mut">
              <FlowArrow size={34} weight="thin" />
              <p className="text-[12.5px] font-medium">Canvas trống</p>
              <p className="text-[11px]">
                Thêm <span className="text-acc">Node Ảnh</span> hoặc <span className="text-acc">Node Video</span> để bắt đầu workflow.
              </p>
            </div>
          </div>
        )}

        {/* Transformed graph layer */}
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})` }}
        >
          <svg
            className="absolute left-0 top-0 overflow-visible pointer-events-none"
            style={{ width: 1, height: 1 }}
          >
            <defs>
              <marker
                id="cv-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--color-acc)" strokeWidth="1.6" />
              </marker>
            </defs>
            {edges.map(({ from, to }) => {
              const x1 = from.x + NODE_W;
              const y1 = from.y + ANCHOR_Y;
              const x2 = to.x;
              const y2 = to.y + ANCHOR_Y;
              const mid = Math.max(40, Math.abs(x2 - x1) / 2);
              const active = from.status === "succeeded";
              const focused = focusLink?.from === from.id && focusLink?.to === to.id;
              return (
                <g key={`${from.id}->${to.id}`}>
                  {focused && (
                    <path
                      d={`M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`}
                      fill="none"
                      stroke="var(--color-warn)"
                      strokeOpacity={0.28}
                      strokeWidth={9}
                      strokeLinecap="round"
                    />
                  )}
                  <path
                    d={`M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`}
                    fill="none"
                    stroke={focused ? "var(--color-warn)" : active ? "var(--color-ok)" : "var(--color-acc)"}
                    strokeOpacity={focused ? 1 : active ? 0.9 : 0.55}
                    strokeWidth={focused ? 3 : 2}
                    strokeDasharray={active || focused ? undefined : "6 5"}
                    markerEnd="url(#cv-arrow)"
                  />
                </g>
              );
            })}
          </svg>

          {/* Rubber-band selection rectangle */}
          {marquee && (marquee.w > 2 || marquee.h > 2) && (
            <div
              className="absolute border-2 border-acc bg-acc/10 rounded-[4px] pointer-events-none"
              style={{ left: marquee.x, top: marquee.y, width: marquee.w, height: marquee.h, zIndex: 5 }}
            />
          )}

          {/* Visual Groups: frames drawn behind nodes */}
          {groups.map((gr) => {
            const frame = groupFrame(gr, nodeById, nodeHeights);
            if (!frame) return null;
            const color = gr.color || "var(--color-acc)";
            const members = gr.nodeIds.filter((id) => nodeById.has(id));
            const selCount = members.filter((id) => selectedIds.includes(id)).length;
            const allSelected = members.length > 0 && selCount === members.length;
            const statuses = members
              .map((id) => nodeById.get(id)?.status)
              .filter(Boolean) as NodeStatus[];
            const hasFailed = statuses.some((s) => s === "failed" || s === "rejected");
            const hasRunning = statuses.some((s) => s === "running" || s === "queued");
            const allDone =
              statuses.length > 0 && statuses.every((s) => s === "succeeded");
            const label = hasFailed
              ? "Lỗi — dừng nhóm"
              : hasRunning
                ? "Đang chạy"
                : allDone
                  ? "Hoàn tất"
                  : `${members.length} node`;
            const labelCls = hasFailed
              ? "text-err"
              : hasRunning
                ? "text-acc"
                : allDone
                  ? "text-ok"
                  : "text-mut";

            return (
              <div
                key={gr.id}
                className="absolute rounded-[14px] border-2 transition-colors pointer-events-none"
                style={{
                  left: frame.x,
                  top: frame.y,
                  width: frame.w,
                  height: frame.h,
                  zIndex: -1,
                  borderColor: color,
                  borderStyle: allSelected || selectedIds.some((id) => members.includes(id)) ? "solid" : "dashed",
                  opacity: allSelected ? 1 : 0.72,
                  background: `color-mix(in srgb, ${color} 7%, transparent)`,
                }}
              >
                {/* Group header: drag to move all members, double-click to rename */}
                <div
                  className="group-header absolute left-0 top-0 h-[40px] flex items-center gap-1.5 px-2 rounded-t-[12px] pointer-events-auto cursor-grab active:cursor-grabbing"
                  style={{ width: Math.max(210, Math.min(frame.w, 460)) }}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    if (e.button !== 0) return;
                    dragRef.current = {
                      kind: "group",
                      id: gr.id,
                      sx: e.clientX,
                      sy: e.clientY,
                      origin: members
                        .map((id) => nodeById.get(id))
                        .filter(Boolean)
                        .map((m) => ({ id: m!.id, x: m!.x, y: m!.y })),
                    };
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEditingGroupId(gr.id);
                  }}
                >
                  <span
                    className="size-2.5 rounded-full shrink-0"
                    style={{ background: color }}
                  />
                  {editingGroupId === gr.id ? (
                    <input
                      autoFocus
                      value={gr.name}
                      onChange={(e) => renameGroup(gr.id, e.target.value)}
                      onBlur={() => {
                        if (!gr.name.trim()) renameGroup(gr.id, "Nhóm chưa đặt tên");
                        setEditingGroupId(null);
                      }}
                      onKeyDown={(e) => {
                        e.stopPropagation();
                        if (e.key === "Enter" || e.key === "Escape") {
                          if (!gr.name.trim()) renameGroup(gr.id, "Nhóm chưa đặt tên");
                          setEditingGroupId(null);
                        }
                      }}
                      onPointerDown={(e) => e.stopPropagation()}
                      className="flex-1 min-w-0 bg-panel border border-line2 rounded px-1.5 py-0.5 text-[12.5px] font-bold text-fg outline-none"
                    />
                  ) : (
                    <span
                      className="text-[12.5px] font-bold truncate flex-1"
                      style={{ color }}
                      title="Nháy đúp để đổi tên"
                    >
                      {gr.name}
                    </span>
                  )}
                  <span className={`text-[10px] font-mono shrink-0 ${labelCls}`}>{label}</span>
                  <button
                    type="button"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedIds(members);
                      setConfirmTarget({ mode: "workflow" });
                    }}
                    className="grid place-items-center size-8 rounded-[8px] text-mut hover:text-ok hover:bg-panel2 cursor-pointer shrink-0 disabled:opacity-40 disabled:pointer-events-none"
                    title={`Chạy riêng nhóm "${gr.name}"`}
                    disabled={wfBusy}
                  >
                    <Play size={18} weight="fill" />
                  </button>
                  <button
                    type="button"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      selectGroup(gr.id);
                    }}
                    className="grid place-items-center size-8 rounded-[8px] text-mut hover:text-fg hover:bg-panel2 cursor-pointer shrink-0"
                    title="Chọn toàn bộ node trong nhóm"
                  >
                    <CheckCircle size={18} weight={allSelected ? "fill" : "regular"} />
                  </button>
                  <button
                    type="button"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      dissolveGroup(gr.id);
                    }}
                    className="grid place-items-center size-8 rounded-[8px] text-mut hover:text-err hover:bg-panel2 cursor-pointer shrink-0"
                    title="Giải tán nhóm (giữ nguyên các node)"
                  >
                    <X size={18} weight="bold" />
                  </button>
                </div>
              </div>
            );
          })}

          {nodes.map((n) => (
            <CanvasNodeCard
              key={n.id}
              n={n}
              allNodes={nodes}
              imageRatios={imageRatios}
              verifiedRatios={verifiedRatios}
              videoRatios={videoRatios}
              resolutions={resolutions}
              linking={linking}
              wfBusy={wfBusy}
              onPromptChange={(prompt) => patchNode(n.id, { prompt })}
              onFieldChange={(patch) => patchNode(n.id, patch)}
              onSourceChange={(sid) =>
                patchNode(n.id, {
                  sourceImageId: sid || null,
                  sourceImageIds: sid ? [sid] : [],
                  status: "idle",
                  reason: null,
                })
              }
              onSourcesChange={(sids) =>
                patchNode(n.id, {
                  sourceImageIds: sids,
                  sourceImageId: sids[0] ?? null,
                  status: "idle",
                  reason: null,
                })
              }
              onRemove={() => removeNode(n.id)}
              onRun={() => {
                if (n.type === "last_frame") void runNodeNow(n.id, false);
                else setConfirmTarget({ mode: "node", nodeId: n.id });
              }}
              onDot={(side) => handleDotClick(n, side)}
              onUpload={(file) => void uploadRef(n.id, file)}
              onOpenDrawer={openDrawer}
              onOpenPromptEditor={(id) => setPromptEditorNodeId(id)}
              onPreviewMedia={setPreviewMedia}
              aiGeneratingId={aiGeneratingId}
              onGenerateAiPrompt={handleGenerateAiPrompt}
              skillsList={skillsList}
              itemLibrary={itemLibrary}
              selected={selectedIds.includes(n.id)}
              onSelect={(additive) => toggleSelect(n.id, additive)}
              onMeasure={measureNode}
              focusLink={focusLink}
              onFocusLink={setFocusLink}
              onHoverRef={setHoverRef}
              onHeaderDown={(e) => {
                e.stopPropagation();
                // Shift/Ctrl+click toggles membership instead of starting a drag.
                if (e.shiftKey || e.ctrlKey || e.metaKey) {
                  toggleSelect(n.id, true);
                  return;
                }
                // Dragging a node that is already part of the selection moves
                // the whole selection. A plain click never changes selection —
                // selection is explicit (Shift+click / rubber-band) so the
                // "Chạy N node chọn" scope cannot change by accident.
                const moving = selectedRef.current.includes(n.id) ? selectedRef.current : [n.id];
                const members = moving
                  .map((id) => nodesRef.current.find((x) => x.id === id))
                  .filter(Boolean)
                  .map((m) => ({ id: m!.id, x: m!.x, y: m!.y }));
                if (members.length > 1) {
                  dragRef.current = {
                    kind: "group",
                    id: n.id,
                    sx: e.clientX,
                    sy: e.clientY,
                    origin: members,
                  };
                } else {
                  dragRef.current = { kind: "node", id: n.id, sx: e.clientX, sy: e.clientY, ox: n.x, oy: n.y };
                }
              }}
            />
          ))}
        </div>
      </div>

      {/* Floating Context Menu (Right-Click on Canvas) */}
      {contextMenu && (
        <div
          ref={menuRef}
          className="fixed z-50 min-w-[210px] rounded-ctl border border-line2 bg-panel/95 backdrop-blur-md p-1.5 shadow-2xl animate-in fade-in zoom-in-95 duration-100 select-none text-[12.5px]"
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 225),
            top: Math.min(contextMenu.y, window.innerHeight - 210),
          }}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => e.preventDefault()}
        >
          <div className="px-2.5 py-1 text-[10px] font-bold text-mut uppercase tracking-wider border-b border-line mb-1">
            Thêm Node Mới
          </div>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => addNodeAt("ref", contextMenu.canvasX, contextMenu.canvasY)}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer"
          >
            <span className="grid place-items-center size-5 rounded-[4px] bg-acc/15 text-acc">
              <UploadSimple size={13} />
            </span>
            <span>Ảnh tham chiếu</span>
          </button>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => addNodeAt("image", contextMenu.canvasX, contextMenu.canvasY)}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer"
          >
            <span className="grid place-items-center size-5 rounded-[4px] bg-acc/15 text-acc">
              <ImageIcon size={13} />
            </span>
            <span>Node Ảnh</span>
          </button>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => addNodeAt("video", contextMenu.canvasX, contextMenu.canvasY)}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer"
          >
            <span className="grid place-items-center size-5 rounded-[4px] bg-ok/15 text-ok">
              <VideoCamera size={13} />
            </span>
            <span>Node Video</span>
          </button>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => addNodeAt("last_frame", contextMenu.canvasX, contextMenu.canvasY)}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer"
          >
            <span className="grid place-items-center size-5 rounded-[4px] bg-purple-500/15 text-purple-400">
              <FilmSlate size={13} />
            </span>
            <span>Frame Cuối</span>
          </button>

          <div className="px-2.5 py-1 mt-1 mb-1 text-[10px] font-bold text-mut uppercase tracking-wider border-t border-line pt-1.5">
            Nhóm
          </div>
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => {
              createGroupFromSelection();
              setContextMenu(null);
            }}
            disabled={selectedIds.length === 0}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
          >
            <span className="grid place-items-center size-5 rounded-[4px] bg-acc/15 text-acc">
              <Plus size={13} />
            </span>
            <span>Tạo nhóm từ node đã chọn</span>
          </button>
          {groups.length > 0 && (
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => {
                if (groups[0]) {
                  addSelectionToGroup(groups[0].id);
                  setContextMenu(null);
                }
              }}
              disabled={selectedIds.length === 0}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-left text-dim hover:text-fg hover:bg-panel2 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
            >
              <span className="grid place-items-center size-5 rounded-[4px] bg-ok/15 text-ok">
                <FlowArrow size={13} />
              </span>
              <span>Thêm vào {groups[0].name}</span>
            </button>
          )}
        </div>
      )}

      {/* Right Drawer for Logs & Errors */}
      <CanvasDrawer
        node={drawerNode}
        allNodes={nodes}
        initialSection={drawerSection}
        onClose={() => setDrawerNodeId(null)}
        onRunNode={(id, dry) => void runNodeNow(id, dry)}
        onRemoveNode={removeNode}
        onUpdatePrompt={(id, prompt) => patchNode(id, { prompt })}
        onUpdateNode={patchNode}
      />

      {/* Centered Prompt Editor Modal (mở từ khung Prompt trên node) */}
      <PromptEditorModal
        open={!!promptEditorNode}
        title={`Prompt — ${promptEditorNode?.label ?? (promptEditorNode?.type === "video" ? "Node Video" : "Node Ảnh")}`}
        value={promptEditorNode?.prompt ?? ""}
        onChange={(v) => {
          if (promptEditorNode) patchNode(promptEditorNode.id, { prompt: v });
        }}
        onClose={() => setPromptEditorNodeId(null)}
        placeholder="Mô tả ảnh / chuyển động cần tạo…"
        maxChars={limits.max_prompt_chars}
      />

      {/* Confirm Modal (Real Run) */}
      {confirmTarget && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={() => setConfirmTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-panel border border-line2 bg-panel p-5 flex flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2">
              <span className="grid place-items-center size-8 rounded-full bg-warn/15 text-warn">
                <Warning size={17} weight="fill" />
              </span>
              <h3 className="text-[14px] font-bold text-fg">Xác nhận chạy thật</h3>
            </div>
            <p className="text-[12.5px] leading-relaxed text-dim">
              {confirmTarget.mode === "workflow"
                ? selectedIds.length > 0
                  ? `Sẽ chạy ${runUnits.length} nhóm chứa ${selectedIds.length} node đã chọn. Mỗi nhóm là một đơn vị độc lập — node lỗi chỉ dừng nhóm đó.`
                  : `Sẽ chạy ${runUnits.length} nhóm (${imageNodes.length} node ảnh + ${videoNodes.length} node video + ${lastFrameNodes.length} node frame cuối). Mỗi nhóm là một đơn vị độc lập — node lỗi chỉ dừng nhóm đó, các nhóm khác vẫn chạy.`
                : "Sẽ chạy node này qua tài khoản Flow."}
            </p>

            {confirmTarget.mode === "workflow" && runUnits.length > 0 && (
              <div className="flex flex-col gap-1 max-h-44 overflow-y-auto slim-scroll">
                {runUnits.map((u) => {
                  const imgs = u.nodeIds.filter((id) => nodeById.get(id)?.type === "image").length;
                  const vids = u.nodeIds.filter((id) => nodeById.get(id)?.type === "video").length;
                  const frames = u.nodeIds.filter((id) => nodeById.get(id)?.type === "last_frame").length;
                  return (
                    <div
                      key={u.id}
                      className="flex items-center justify-between gap-2 rounded-ctl border border-line bg-panel2 px-2.5 py-1.5 text-[11.5px]"
                    >
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="size-1.5 rounded-full shrink-0"
                          style={{ background: u.color ?? "var(--color-mut)" }}
                        />
                        <span className="truncate font-semibold text-fg">{u.name}</span>
                      </span>
                      <span className="font-mono text-[10.5px] text-mut shrink-0">
                        {imgs} ảnh · {vids} video · {frames} frame
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            <p className="text-[12px] leading-relaxed text-warn bg-warn/5 border border-warn/25 rounded-ctl px-3 py-2">
              Chi phí ước tính ~
              {confirmTarget.mode === "workflow"
                ? ` ${runUnits.reduce(
                    (acc, u) =>
                      acc +
                      u.nodeIds.filter((id) => {
                        const t = nodeById.get(id)?.type;
                        return t === "image" || t === "video";
                      }).length,
                    0,
                  )} credit (các node Frame Cuối: 0 credit)`
                : " 1 credit"}{" "}
              nếu Google nhận (bị từ chối = 0 credit).
            </p>

            {confirmTarget.mode === "workflow" && (
              <label className="flex items-start gap-2.5 p-2.5 rounded-ctl border border-acc/35 bg-acc/10 text-[12px] text-fg cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={jitPromptEnabled}
                  onChange={(e) => setJitPromptEnabled(e.target.checked)}
                  className="mt-0.5 accent-acc"
                />
                <div>
                  <span className="font-bold text-acc">Dynamic JIT: Tự động tối ưu prompt theo kết quả node trước</span>
                  <p className="text-[10.5px] text-mut mt-0.5 leading-snug">
                    AI Agent cục bộ sẽ nhìn ảnh thật vừa sinh để viết prompt chính xác cho node tiếp theo trước khi chạy.
                  </p>
                </div>
              </label>
            )}
            <div className="flex justify-end gap-2 mt-1">
              <button
                onClick={() => setConfirmTarget(null)}
                className="h-9 px-4 rounded-ctl border border-line2 text-[12.5px] font-semibold text-dim hover:text-fg cursor-pointer"
              >
                Hủy
              </button>
              <button
                onClick={() => {
                  if (confirmTarget.mode === "workflow") void runWorkflow(false);
                  else void runNodeNow(confirmTarget.nodeId, false).then(() => setConfirmTarget(null));
                }}
                className="h-9 px-4 rounded-ctl bg-acc text-accink text-[12.5px] font-bold hover:bg-acc2 cursor-pointer"
              >
                Chạy thật
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Tooltip xem nhanh ảnh tham chiếu — portal ở cấp panel nên không bị
          strip chip (overflow) cắt mất. */}
      {hoverRef && (
        <div
          className="fixed z-[70] pointer-events-none"
          style={{
            left: Math.min(hoverRef.x, window.innerWidth - 190),
            top: Math.min(hoverRef.y + 8, window.innerHeight - 150),
          }}
        >
          <div className="w-44 rounded-ctl border border-line2 bg-panel p-1.5 shadow-2xl">
            {hoverRef.src.fileUrl ? (
              <img
                src={hoverRef.src.fileUrl}
                alt=""
                className="w-full h-40 object-contain rounded bg-ink"
              />
            ) : (
              <div className="w-full h-40 grid place-items-center rounded bg-ink text-mut text-[10px]">
                Chưa có ảnh kết quả
              </div>
            )}
            <div className="mt-1.5 flex items-center gap-1.5">
              <OrderBadge index={hoverRef.index} size="xs" />
              <span className="text-[10px] text-dim truncate" title={hoverRef.src.fileName ?? ""}>
                {hoverRef.src.type === "ref"
                  ? (hoverRef.src.fileName ?? hoverRef.src.id)
                  : hoverRef.src.label || hoverRef.src.id}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Media Preview Modal (Large Split View) */}
      <MediaPreviewModal
        item={previewMedia}
        onClose={() => setPreviewMedia(null)}
        onInsertToCanvas={(it) => addReferenceNode(it.url, it.name)}
      />
      <DeliveryModal
        open={deliveryOpen}
        onClose={() => setDeliveryOpen(false)}
        runsByClip={deliveryRuns}
        itemsByNode={deliveryItems}
      />
    </div>
  );
});

// --------------------------------------------------------------------------- //
// Node Card
// --------------------------------------------------------------------------- //

function CanvasNodeCard(props: {
  n: CanvasNode;
  allNodes: CanvasNode[];
  imageRatios: string[];
  verifiedRatios: Set<string>;
  videoRatios: string[];
  resolutions: string[];
  linking: { id: string; kind: NodeType; side: "in" | "out" } | null;
  wfBusy: boolean;
  onPromptChange: (v: string) => void;
  onFieldChange: (patch: Partial<CanvasNode>) => void;
  onSourceChange: (sid: string) => void;
  onSourcesChange: (sids: string[]) => void;
  onRemove: () => void;
  onRun: () => void;
  onDot: (side: "in" | "out") => void;
  onUpload: (file: File) => void;
  onOpenDrawer: (id: string, section?: DrawerSection) => void;
  onOpenPromptEditor: (id: string) => void;
  onPreviewMedia?: (item: PreviewMediaItem) => void;
  aiGeneratingId?: string | null;
  onGenerateAiPrompt?: (id: string) => void;
  skillsList?: { id: string; name: string }[];
  itemLibrary?: LibraryItem[];
  /** Cặp (nguồn → đích) đang được hover để tô sáng edge + node nguồn. */
  focusLink?: { from: string; to: string } | null;
  onFocusLink?: (link: { from: string; to: string } | null) => void;
  onHoverRef?: (
    info: { src: CanvasNode; index: number; x: number; y: number } | null,
  ) => void;
  selected?: boolean;
  onSelect?: (additive: boolean) => void;
  onMeasure?: (id: string, height: number) => void;
  onHeaderDown: (e: React.PointerEvent) => void;
}) {
  const { n, allNodes, imageRatios, verifiedRatios, videoRatios, resolutions, linking, wfBusy, aiGeneratingId, onGenerateAiPrompt, skillsList, itemLibrary, selected } = props;
  const st = statusStyle(n.status);
  const isRef = n.type === "ref";
  const isImg = n.type === "image";
  const isVid = n.type === "video";
  const isLastFrame = n.type === "last_frame";

  const nodeSkills = useMemo(() => {
    if (!skillsList) return [];
    return [...skillsList].sort((a, b) => {
      const aIsVid = a.id.includes("video");
      const bIsVid = b.id.includes("video");
      if (isVid) {
        if (aIsVid && !bIsVid) return -1;
        if (!aIsVid && bIsVid) return 1;
      } else {
        if (!aIsVid && bIsVid) return -1;
        if (aIsVid && !bIsVid) return 1;
      }
      return a.name.localeCompare(b.name);
    });
  }, [skillsList, isVid]);

  const [dragOver, setDragOver] = useState(false);
  const [mediaTab, setMediaTab] = useState<"video" | "frame">("video");
  /** URL đã 404/không giải mã được — ẩn khung thay vì hiện icon ảnh hỏng. */
  const [brokenMedia, setBrokenMedia] = useState<Record<string, boolean>>({});
  const markBroken = (url?: string | null) => {
    if (!url) return;
    setBrokenMedia((cur) => (cur[url] ? cur : { ...cur, [url]: true }));
  };
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Report card height so group frames can wrap nodes tightly.
  // offsetHeight is layout-space (unaffected by the canvas scale transform).
  useEffect(() => {
    const el = cardRef.current;
    if (!el || !props.onMeasure) return;
    const report = () => props.onMeasure?.(n.id, el.offsetHeight);
    report();
    const ro = new ResizeObserver(report);
    ro.observe(el);
    return () => ro.disconnect();
  }, [n.id, props.onMeasure]);

  const currentSids = getNodeSourceIds(n);
  const connectedSources = currentSids
    .map((sid) => allNodes.find((i) => i.id === sid))
    .filter(Boolean) as CanvasNode[];

  /** Thứ tự `#n` của node này khi nó làm ảnh tham chiếu (dùng cho badge trên header). */
  const refOrders = useMemo(() => {
    const out: { to: string; index: number }[] = [];
    for (const other of allNodes) {
      if (other.type !== "image") continue;
      const idx = getNodeSourceIds(other).indexOf(n.id);
      if (idx >= 0) out.push({ to: other.id, index: idx + 1 });
    }
    return out;
  }, [allNodes, n.id]);

  const canRun =
    !wfBusy &&
    n.status !== "running" &&
    n.status !== "queued" &&
    (isLastFrame ? !!n.sourceImageId : n.prompt.trim().length > 0);

  const upstream = n.sourceImageId ? allNodes.find((i) => i.id === n.sourceImageId) : undefined;
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

  const sourceLabel = (c: CanvasNode) => {
    if (c.label) return c.label;
    if (c.type === "ref") return `Tham chiếu: ${c.fileName ?? c.id}`;
    if (c.type === "last_frame") return `Frame Cuối: ${c.id}${c.fileUrl ? " (đã có ảnh)" : ""}`;
    if (c.type === "video") return `Video: ${c.prompt ? c.prompt.slice(0, 24) + "…" : c.id}`;
    return c.prompt ? `Ảnh: ${c.prompt.slice(0, 24)}…` : `Ảnh (${c.id})`;
  };

  const nodeTitle =
    n.label ||
    (isRef
      ? "Ảnh tham chiếu"
      : isImg
        ? "Node Ảnh"
        : isVid
          ? "Node Video"
          : "Frame Cuối Video");

  const dotCls = (side: "in" | "out", accent: boolean) =>
    `absolute ${side === "out" ? "-right-2.5" : "-left-2.5"} top-[12px] size-5 rounded-full border-2 grid place-items-center cursor-pointer transition-all ${
      linking?.id === n.id && linking.side === side
        ? "border-acc bg-acc/30 ring-2 ring-acc/60 animate-pulse"
        : accent
          ? "border-acc/70 bg-panel hover:bg-acc/20"
          : "border-line2 bg-panel hover:border-acc/70 hover:bg-acc/20"
    }`;

  const dot = (side: "in" | "out", accent: boolean, title: string) => (
    <button
      onClick={(e) => {
        e.stopPropagation();
        props.onDot(side);
      }}
      onPointerDown={(e) => e.stopPropagation()}
      className={dotCls(side, accent)}
      title={title}
    >
      <LinkSimple size={9} className={accent ? "text-acc" : "text-mut"} />
    </button>
  );

  const pickFile = (f?: File | null) => {
    if (f) props.onUpload(f);
  };

  const isFocusSource = props.focusLink?.from === n.id;
  const isFocusTarget = props.focusLink?.to === n.id;

  return (
    <div
      ref={cardRef}
      className={`canvas-node-card absolute rounded-panel border-2 bg-panel shadow-xl ${st.border} ${
        selected ? "ring-2 ring-acc ring-offset-2 ring-offset-ink" : ""
      } ${isFocusSource || isFocusTarget ? "canvas-node-focus" : ""}`}
      style={{ left: n.x, top: n.y, width: NODE_W }}
      onPointerDown={(e) => {
        e.stopPropagation();
        const t = e.target as HTMLElement;
        if (t.closest("input, textarea, select, button")) return;
        if (e.shiftKey || e.ctrlKey || e.metaKey) {
          e.preventDefault();
          props.onSelect?.(true);
        }
      }}
    >
      {/* Header (Drag handle) */}
      <div
        className="flex items-center gap-2 px-3 h-[44px] rounded-t-panel border-b border-line bg-panel2 cursor-grab active:cursor-grabbing"
        onPointerDown={props.onHeaderDown}
      >
        <span
          className={`grid place-items-center size-6 rounded-ctl shrink-0 ${
            isImg || isRef
              ? "bg-acc/15 text-acc"
              : isVid
                ? "bg-ok/15 text-ok"
                : "bg-purple-500/15 text-purple-400"
          }`}
        >
          {isRef ? (
            <UploadSimple size={13} />
          ) : isImg ? (
            <ImageIcon size={13} />
          ) : isVid ? (
            <VideoCamera size={13} />
          ) : (
            <FilmSlate size={13} />
          )}
        </span>
        <span className="text-[12px] font-bold text-fg truncate flex-1">{nodeTitle}</span>

        {/* Badge thứ tự ảnh tham chiếu: node này đang là Image 1/2/3 của node ảnh nào. */}
        {refOrders.length > 0 && (
          <span className="flex items-center gap-0.5 shrink-0">
            {refOrders.map((o) => (
              <span
                key={o.to}
                className="inline-flex items-center gap-1 rounded-full border border-warn/50 bg-warn/15 pl-1 pr-1.5 h-[18px]"
                title={`Đang là ảnh tham chiếu #${o.index} (Image ${o.index}) của ${
                  allNodes.find((x) => x.id === o.to)?.label || "node ảnh"
                }`}
              >
                <OrderBadge index={o.index} size="xs" muted />
                <span className="text-[8.5px] font-bold text-warn/80 leading-none">REF</span>
              </span>
            ))}
          </span>
        )}

        {n.status === "running" || n.status === "queued" ? (
          <Spinner size={12} className="text-acc shrink-0" />
        ) : n.status === "succeeded" ? (
          <CheckCircle size={13} weight="fill" className="text-ok shrink-0" />
        ) : n.status === "failed" || n.status === "rejected" || n.status === "skipped" ? (
          <Warning size={13} weight="fill" className="text-err shrink-0" />
        ) : null}

        {st.label && <span className={`text-[10px] font-semibold ${st.cls} shrink-0`}>{st.label}</span>}

        {/* View Logs / Details button */}
        <button
          onClick={() => props.onOpenDrawer(n.id)}
          onPointerDown={(e) => e.stopPropagation()}
          className="text-mut hover:text-fg cursor-pointer shrink-0 ml-0.5"
          title="Xem chi tiết & nhật ký"
        >
          <ListDashes size={14} />
        </button>

        {/* Delete node button */}
        <button
          onClick={props.onRemove}
          onPointerDown={(e) => e.stopPropagation()}
          className="text-mut hover:text-err cursor-pointer shrink-0"
          title="Xóa node"
        >
          <Trash size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="p-3 flex flex-col gap-2">
        {/* REF NODE */}
        {isRef && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                pickFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setDragOver(false);
                pickFile(e.dataTransfer.files?.[0]);
              }}
              className={`rounded-ctl border border-dashed bg-panel2 overflow-hidden transition-colors relative group ${
                dragOver ? "border-acc bg-acc/10" : "border-line2 hover:border-acc/60"
              }`}
            >
              {n.fileUrl ? (
                <>
                  <img
                    src={n.fileUrl}
                    alt="Ảnh tham chiếu"
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full max-h-44 object-contain cursor-pointer hover:opacity-95 transition-opacity"
                    title="Bấm để thay đổi ảnh"
                  />
                  <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        props.onPreviewMedia?.({
                          url: n.fileUrl!,
                          name: n.fileName || n.label || "Ảnh tham chiếu",
                          category: "image",
                        });
                      }}
                      className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
                      title="Xem ảnh to"
                    >
                      <ArrowsOut size={13} weight="bold" />
                    </button>
                  </div>
                </>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center gap-1.5 py-7 text-mut cursor-pointer"
                  title="Bấm hoặc kéo-thả ảnh vào đây"
                >
                  {n.status === "queued" ? <Spinner size={18} /> : <UploadSimple size={22} />}
                  <span className="text-[11px] font-medium">
                    {n.status === "queued" ? "Đang upload…" : "Bấm hoặc kéo-thả ảnh"}
                  </span>
                  <span className="text-[10px]">PNG / JPG / WebP</span>
                </div>
              )}
            </div>
            {n.fileUrl && (
              <p className="text-[10px] text-mut truncate" title={n.fileName ?? ""}>
                {n.fileName ?? "ảnh đã upload"} — bấm ảnh để thay
              </p>
            )}
          </>
        )}

        {/* IMAGE NODE */}
        {isImg && (
          <>
            <div className="flex flex-col gap-1.5">
              {/* Tiêu đề + "Xóa hết" trên một dòng riêng; strip chip chiếm trọn bề ngang
                  node bên dưới để 5+ ảnh xuống dòng gọn (3–4 chip/hàng) thay vì 1 chip/hàng. */}
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold text-mut truncate">
                  Ảnh tham chiếu ({connectedSources.length})
                </span>
                {connectedSources.length > 0 && (
                  <button
                    type="button"
                    onClick={() => props.onSourcesChange([])}
                    className="text-[9.5px] text-mut hover:text-err cursor-pointer shrink-0 whitespace-nowrap"
                    title="Bỏ tất cả ảnh tham chiếu"
                  >
                    Xóa hết
                  </button>
                )}
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                {connectedSources.map((src, idx) => (
                    <div
                      key={src.id}
                      className="group/ref relative shrink-0"
                      onMouseEnter={(e) => {
                        props.onFocusLink?.({ from: src.id, to: n.id });
                        const r = e.currentTarget.getBoundingClientRect();
                        props.onHoverRef?.({ src, index: idx + 1, x: r.left, y: r.bottom });
                      }}
                      onMouseLeave={() => {
                        props.onFocusLink?.(null);
                        props.onHoverRef?.(null);
                      }}
                    >
                      <div
                        className={`inline-flex items-center gap-1 h-6 pl-1 pr-1.5 rounded-full border text-[10px] font-semibold transition-colors ${
                          props.focusLink?.from === src.id && props.focusLink?.to === n.id
                            ? "border-warn/70 bg-warn/20 text-warn"
                            : "border-line2 bg-panel2 text-dim hover:border-warn/50 hover:text-fg"
                        }`}
                        title={
                          src.type === "ref"
                            ? `${src.fileName ?? src.id} — Image ${idx + 1}`
                            : `${sourceLabel(src)} — Image ${idx + 1}`
                        }
                      >
                        <OrderBadge index={idx + 1} size="xs" />
                        {src.fileUrl ? (
                          <img src={src.fileUrl} alt="" className="size-4 rounded-[3px] object-cover" />
                        ) : (
                          <ImageIcon size={11} className="text-mut" />
                        )}
                      </div>
                    </div>
                  ))}
                  {availableOptions.length > 0 && (
                    <button
                      type="button"
                      onClick={() => props.onOpenDrawer(n.id, "sources")}
                      className="shrink-0 grid place-items-center size-6 rounded-full border border-dashed border-line2 text-mut hover:border-acc hover:text-acc transition-colors cursor-pointer"
                      title="Nối thêm ảnh tham chiếu (mở Cấu hình)"
                    >
                      <Plus size={11} weight="bold" />
                    </button>
                  )}
                  {connectedSources.length === 0 && availableOptions.length === 0 && (
                    <span className="text-[9.5px] text-mut">Chưa có ảnh nào</span>
                  )}
              </div>

              {sourceBlocked && (
                <p className="text-[10px] text-warn leading-snug">
                  Một số node nguồn chưa có kết quả — hãy chạy trước khi chạy node này.
                </p>
              )}
            </div>

            <div className="flex items-center justify-between mt-0.5 gap-1.5 min-w-0">
              <span className="text-[10px] font-semibold text-mut shrink-0">Prompt ảnh</span>
              <div className="flex items-center gap-1 min-w-0 flex-1 justify-end">
                {nodeSkills && nodeSkills.length > 0 && (
                  <select
                    value={n.agentSkillId ?? ""}
                    onChange={(e) => props.onFieldChange({ agentSkillId: e.target.value || null })}
                    className="h-5 min-w-0 flex-1 max-w-[135px] rounded border border-line2 bg-panel px-1 text-[9px] text-fg focus:border-acc outline-none cursor-pointer"
                    title="Chọn skill quy chuẩn AI tạo prompt cho node này"
                  >
                    <option value="">(Tự động: Ảnh Lookbook)</option>
                    {nodeSkills.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                )}
                {onGenerateAiPrompt && (
                  <button
                    type="button"
                    disabled={aiGeneratingId === n.id || wfBusy}
                    onClick={() => onGenerateAiPrompt(n.id)}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] border border-acc/40 bg-acc/10 text-[9.5px] font-bold text-acc hover:bg-acc/20 hover:border-acc/70 transition-all cursor-pointer disabled:opacity-40 shrink-0 whitespace-nowrap"
                    title="Local AI Agent sẽ phân tích ảnh kết quả nguồn để sinh prompt chuẩn"
                  >
                    {aiGeneratingId === n.id ? (
                      <>
                        <Spinner size={9} />
                        <span>Đang tạo…</span>
                      </>
                    ) : (
                      <>
                        <Sparkle size={10} weight="fill" className="text-acc" />
                        <span>AI Prompt</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            {/* Ô này KHÔNG gắn ảnh — ảnh tham chiếu nằm ở strip pill phía trên.
                Nó chỉ đánh dấu: ảnh node này sinh ra là **ảnh sản phẩm**, nên được chép vào
                thư viện `out/items/<project>/` ngay khi sinh xong. Tên món quyết định tên file.
                Phạm vi cắt món (Áo/Quần/Cả bộ) đã chuyển vào Drawer cho gọn node. */}
            {n.type === "image" && (
              <div className="flex items-center gap-1.5 min-w-0">
                <label className="flex items-center gap-1.5 cursor-pointer select-none shrink-0">
                  <input
                    type="checkbox"
                    checked={!!n.isItem}
                    onChange={(e) =>
                      props.onFieldChange({
                        isItem: e.target.checked,
                        // Bật cờ thì mặc định luôn một phạm vi: để null nghĩa là agent
                        // không được chỉ định món nào và quay lại lỗi "ra chiếc áo".
                        ...(e.target.checked ? { itemScope: n.itemScope ?? "top" } : {}),
                      })
                    }
                    className="h-3 w-3 accent-[var(--acc)] cursor-pointer"
                  />
                  <span className="text-[10px] font-semibold text-mut whitespace-nowrap">Ảnh sản phẩm</span>
                </label>
                {n.isItem && (
                  <input
                    type="text"
                    value={n.itemName ?? ""}
                    onChange={(e) => props.onFieldChange({ itemName: e.target.value })}
                    placeholder="Tên món…"
                    list="canvas-item-library"
                    className="h-6 min-w-0 flex-1 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[10px] text-fg focus:border-acc outline-none"
                    title="Tên file trong thư viện: bỏ dấu, thường hoá, cách nhau bằng _"
                  />
                )}
                <datalist id="canvas-item-library">
                  {(itemLibrary ?? []).map((it) => (
                    <option key={it.file} value={it.name} />
                  ))}
                </datalist>
              </div>
            )}

            <PromptPreviewCard
              prompt={n.prompt}
              placeholder="Prompt mô tả ảnh cần tạo… bấm để sửa"
              onExpand={() => props.onOpenPromptEditor(n.id)}
            />

            {/* Summary pills thay cho dropdown Tỷ lệ + ô Seed: 1 hàng, bấm → Drawer. */}
            <div className="flex items-center gap-1 flex-wrap">
              <SummaryPill
                value={n.aspectRatio + (verifiedRatios.has(n.aspectRatio) ? "" : " ⚠")}
                title={`Tỷ lệ khung hình: ${n.aspectRatio}${
                  verifiedRatios.has(n.aspectRatio) ? "" : " (chưa verify)"
                } — bấm để đổi`}
                onClick={() => props.onOpenDrawer(n.id, "config")}
              />
              <SummaryPill
                value={`Seed: ${n.seed ?? "random"}`}
                title="Seed — bấm để đổi trong Cấu hình"
                onClick={() => props.onOpenDrawer(n.id, "config")}
              />
              {n.isItem && (
                <SummaryPill
                  tone="warn"
                  value={`Sản phẩm · ${ITEM_SCOPE_OPTIONS.find((o) => o.value === (n.itemScope ?? "top"))?.label ?? "Áo"}`}
                  title="Ảnh sản phẩm lưu vào thư viện items/ — bấm để sửa"
                  onClick={() => props.onOpenDrawer(n.id, "config")}
                />
              )}
            </div>
          </>
        )}

        {/* VIDEO NODE */}
        {isVid && (
          <>
            <label className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-mut">Nguồn ảnh khung hình</span>
              <select
                value={n.sourceImageId ?? ""}
                onChange={(e) => props.onSourceChange(e.target.value)}
                className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
              >
                <option value="">Tự tạo ảnh khung (auto)</option>
                {sourceOptions.map((i) => (
                  <option key={i.id} value={i.id}>
                    {sourceLabel(i)}
                  </option>
                ))}
              </select>
            </label>
            {sourceBlocked && (
              <p className="text-[10px] text-warn leading-snug">
                Node nguồn chưa chạy xong — video sẽ chờ/bỏ qua khi chạy workflow.
              </p>
            )}

            <div className="flex items-center justify-between mt-0.5 gap-1.5 min-w-0">
              <span className="text-[10px] font-semibold text-mut shrink-0">Prompt video</span>
              <div className="flex items-center gap-1 min-w-0 flex-1 justify-end">
                {nodeSkills && nodeSkills.length > 0 && (
                  <select
                    value={n.agentSkillId ?? ""}
                    onChange={(e) => props.onFieldChange({ agentSkillId: e.target.value || null })}
                    className="h-5 min-w-0 flex-1 max-w-[135px] rounded border border-line2 bg-panel px-1 text-[9px] text-fg focus:border-acc outline-none cursor-pointer"
                    title="Chọn skill quy chuẩn AI tạo prompt cho video"
                  >
                    <option value="">(Tự động: V1 Push / V2 Showcase)</option>
                    {nodeSkills.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                )}
                {onGenerateAiPrompt && (
                  <button
                    type="button"
                    disabled={aiGeneratingId === n.id || wfBusy}
                    onClick={() => onGenerateAiPrompt(n.id)}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] border border-acc/40 bg-acc/10 text-[9.5px] font-bold text-acc hover:bg-acc/20 hover:border-acc/70 transition-all cursor-pointer disabled:opacity-40 shrink-0 whitespace-nowrap"
                    title="Local AI Agent sẽ nhìn vào ảnh First Frame hoặc Last Frame nguồn để viết prompt chuyển động nối tiếp chuẩn xác"
                  >
                    {aiGeneratingId === n.id ? (
                      <>
                        <Spinner size={9} />
                        <span>Đang tạo…</span>
                      </>
                    ) : (
                      <>
                        <Sparkle size={10} weight="fill" className="text-acc" />
                        <span>AI Prompt</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            <PromptPreviewCard
              prompt={n.prompt}
              placeholder="Prompt chuyển động cho video 8s… bấm để sửa"
              onExpand={() => props.onOpenPromptEditor(n.id)}
            />

            {/* Summary pills: Tỷ lệ • Độ phân giải • Frame nguồn — chỉnh chi tiết trong Drawer. */}
            <div className="flex items-center gap-1 flex-wrap">
              <SummaryPill
                value={n.videoRatio}
                title={`Tỷ lệ video: ${n.videoRatio} — bấm để đổi`}
                onClick={() => props.onOpenDrawer(n.id, "config")}
              />
              <SummaryPill
                value={n.resolution}
                title={`Độ phân giải: ${n.resolution} — bấm để đổi`}
                onClick={() => props.onOpenDrawer(n.id, "config")}
              />
              <SummaryPill
                label="Frame"
                value={upstream ? (upstream.type === "last_frame" ? "Nối tiếp" : "Node Ảnh") : "Auto"}
                title="Ảnh khung nguồn — bấm để đổi trong Cấu hình"
                onClick={() => props.onOpenDrawer(n.id, "config")}
              />
            </div>
          </>
        )}

        {/* LAST FRAME NODE */}
        {isLastFrame && (
          <>
            <div className="flex flex-col gap-1">
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] font-semibold text-mut">Video nguồn (input)</span>
                <select
                  value={n.sourceImageId ?? ""}
                  onChange={(e) => props.onSourceChange(e.target.value)}
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
                onChange={(e) => props.onFieldChange({ removeWatermark: e.target.checked })}
                className="rounded border-line2 text-acc focus:ring-0"
              />
              <span>Tự động xóa watermark Flow</span>
            </label>
          </>
        )}

        {/* Result Preview — với Node Video, Video và Ảnh khung dùng chung MỘT khung
            có tab chuyển đổi nhỏ, thay vì hai khung xếp dọc (giảm nửa chiều cao).
            Chỉ render khi thực sự có media: một <video> rỗng vẫn chiếm 300×150 và
            hiện khung đen "0:00" — đó là lỗi UI khi node chưa có kết quả. */}
        {(() => {
          const hasImage = !!(n.fileUrl && (isImg || isLastFrame) && !brokenMedia[n.fileUrl]);
          const hasVideo = isVid && !!n.videoUrl && !brokenMedia[n.videoUrl];
          const hasFrame = isVid && !!n.frameUrl && !brokenMedia[n.frameUrl];
          const showVideo = hasVideo && (mediaTab === "video" || !hasFrame);
          if (!hasImage && !hasVideo && !hasFrame) return null;
          return (
            <div className="rounded-ctl overflow-hidden border border-line2 bg-panel2 relative group">
              {hasVideo && hasFrame && (
                <div className="absolute top-1.5 left-1.5 z-10 flex items-center gap-0.5 rounded-full border border-line2 bg-ink/85 p-0.5 backdrop-blur-sm">
                  {([
                    { key: "video", label: "Video" },
                    { key: "frame", label: "Ảnh khung" },
                  ] as const).map((tb) => (
                    <button
                      key={tb.key}
                      type="button"
                      onClick={() => setMediaTab(tb.key)}
                      className={`h-[18px] px-1.5 rounded-full text-[9px] font-bold transition-colors cursor-pointer ${
                        mediaTab === tb.key ? "bg-acc text-accink" : "text-dim hover:text-fg"
                      }`}
                    >
                      {tb.label}
                    </button>
                  ))}
                </div>
              )}
              {hasImage ? (
                <img
                  src={n.fileUrl!}
                  alt="Kết quả"
                  onError={() => markBroken(n.fileUrl)}
                  className="w-full max-h-40 object-contain cursor-pointer hover:opacity-95 transition-opacity"
                  onClick={() =>
                    props.onPreviewMedia?.({
                      url: n.fileUrl!,
                      name: n.label || (isImg ? "Node Ảnh" : "Frame Cuối"),
                      category: "image",
                      prompt: n.prompt,
                      resolution: n.aspectRatio,
                      aspect_ratio: n.aspectRatio,
                      seed: n.seed,
                    })
                  }
                  title="Bấm để xem ảnh to với kích thước đầy đủ"
                />
              ) : showVideo ? (
                <video
                  src={n.videoUrl!}
                  controls
                  onError={() => markBroken(n.videoUrl)}
                  className="w-full max-h-40"
                />
              ) : (
                <img
                  src={n.frameUrl!}
                  alt="Ảnh khung"
                  onError={() => markBroken(n.frameUrl)}
                  className="w-full max-h-40 object-contain cursor-pointer hover:opacity-95 transition-opacity bg-ink/40"
                  onClick={() =>
                    props.onPreviewMedia?.({
                      url: n.frameUrl!,
                      name: `${n.label || "Video"} - Khung hình (First Frame)`,
                      category: "image",
                    })
                  }
                  title="Ảnh khung đã dùng / tự tạo — bấm để xem to"
                />
              )}
            <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
              <button
                type="button"
                onClick={() =>
                  props.onPreviewMedia?.({
                    url: showVideo ? n.videoUrl! : hasImage ? n.fileUrl! : n.frameUrl!,
                    name: n.label || (isImg ? "Node Ảnh" : isVid ? "Node Video" : "Frame Cuối"),
                    category: showVideo ? "video" : "image",
                    prompt: n.prompt,
                    resolution: isVid ? n.resolution : n.aspectRatio,
                    aspect_ratio: isVid ? n.videoRatio : n.aspectRatio,
                    seed: n.seed,
                    duration_s: showVideo ? 8 : undefined,
                  })
                }
                className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
                title="Xem ảnh to / phóng to chi tiết"
              >
                <ArrowsOut size={13} weight="bold" />
              </button>
              <a
                href={showVideo ? n.videoUrl! : hasImage ? n.fileUrl! : n.frameUrl!}
                download
                className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
                title="Tải xuống"
              >
                <DownloadSimple size={13} />
              </a>
            </div>
          </div>
          );
        })()}

        {/* Sleek Error Banner (opens Right Drawer) */}
        {(n.status === "failed" || n.status === "rejected" || n.status === "skipped") && (
          <button
            type="button"
            onClick={() => props.onOpenDrawer(n.id)}
            className="w-full text-left px-2.5 py-1.5 rounded-ctl bg-err/10 border border-err/35 hover:bg-err/20 text-err transition-colors flex items-center justify-between gap-1.5 cursor-pointer group"
            title="Bấm để mở chi tiết lỗi và nhật ký thực thi"
          >
            <div className="flex items-center gap-1.5 truncate">
              <Warning size={13} weight="fill" className="shrink-0 text-err" />
              <span className="truncate text-[10.5px] font-medium">{n.reason || "Lỗi thực thi"}</span>
            </div>
            <span className="text-[10px] font-bold underline shrink-0 text-err group-hover:text-err2">
              Xem log →
            </span>
          </button>
        )}

        {/* Action Buttons */}
        {!isRef && (
          <div className="flex items-center gap-1.5 pt-0.5">
            <button
              onClick={props.onRun}
              disabled={!canRun}
              className="flex-1 h-7 rounded-ctl bg-acc text-accink text-[11px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none inline-flex items-center justify-center gap-1"
              title={
                isLastFrame
                  ? "Trích xuất frame cuối (0 credit)"
                  : "Chạy node này (xác nhận trước khi chạy thật)"
              }
            >
              <Play size={10} weight="fill" />
              <span>{isLastFrame ? "Trích xuất" : "Chạy node"}</span>
            </button>
            {n.elapsedS != null && n.status === "succeeded" && (
              <span className="text-[10px] font-mono text-mut px-1">{n.elapsedS.toFixed(1)}s</span>
            )}
          </div>
        )}
      </div>

      {/* Connection dots: right = output, left = input */}
      {/* OUT dot */}
      {(isRef || isImg || isVid || isLastFrame) &&
        dot(
          "out",
          true,
          isVid
            ? "Chấm ra: nối sang node Frame Cuối"
            : isLastFrame
              ? "Chấm ra: ảnh frame cuối nối sang node Video hoặc node Ảnh"
              : "Chấm ra: bấm đây rồi bấm chấm vào (trái) của node ảnh/video",
        )}

      {/* IN dot */}
      {!isRef &&
        dot(
          "in",
          currentSids.length > 0,
          isLastFrame
            ? "Chấm vào: nhận video từ node Video"
            : isImg
              ? `Chấm vào: nhận ảnh tham chiếu (${currentSids.length} ảnh đã nối) — bấm để nối thêm ảnh`
              : "Chấm vào: nhận ảnh khung từ node Ảnh tham chiếu, node Ảnh hoặc Frame Cuối",
        )}
    </div>
  );
}

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import {
  ArrowsCounterClockwise,
  CheckCircle,
  DownloadSimple,
  FilmSlate,
  FlowArrow,
  Image as ImageIcon,
  LinkSimple,
  ListDashes,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  Play,
  Plus,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { Job, NodeMediaOptions, Project } from "../types";
import { CanvasDrawer, type CanvasDrawerNode } from "./CanvasDrawer";
import { Chip, Spinner } from "./ui";

// --------------------------------------------------------------------------- //
// Canvas node graph — image nodes feed video nodes (image-to-video chains).
// Backend: POST /api/node/image, POST /api/node/video, POST /api/node/last_frame
// Chaining works because resolve_input_path() accepts /api/node/files/... URLs
// as attachments, so an image node's file_url becomes a video node's frame_path,
// and a last_frame node extracts the final frame of a video to feed the next video/image.
// --------------------------------------------------------------------------- //

const NODE_W = 280;
const ANCHOR_Y = 22;
const STORAGE_KEY = "fb_canvas_graph_v1";
const TERMINAL = new Set(["succeeded", "failed", "rejected"]);
const ACTIVE = new Set(["queued", "running"]);

type NodeStatus = "idle" | "queued" | "running" | "succeeded" | "failed" | "rejected" | "skipped";
type NodeType = "ref" | "image" | "video" | "last_frame";

type CanvasNode = CanvasDrawerNode;

interface Graph {
  nodes: CanvasNode[];
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
      if (Array.isArray(g?.nodes)) return g;
    }
  } catch {
    /* ignore */
  }
  return { nodes: [] };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
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
  wfBusy: boolean;
  linking: boolean;
}

export interface CanvasPanelHandle {
  addNode: (type: NodeType) => void;
  loadTemplate: (name: "tryon") => void;
  runWorkflow: (dry: boolean) => Promise<void>;
  openConfirmWorkflow: () => void;
}

export interface CanvasPanelProps {
  projects?: Project[];
  selectedProjectId?: string | null;
  onStatsChange?: (stats: CanvasStats) => void;
}

export const CanvasPanel = forwardRef<CanvasPanelHandle, CanvasPanelProps>(function CanvasPanel(
  props,
  ref,
) {
  const [graph, setGraph] = useState<Graph>(loadGraph);
  const [view, setView] = useState<View>({ x: 40, y: 20, z: 1 });
  const [opts, setOpts] = useState<NodeMediaOptions | null>(null);
  const [linking, setLinking] = useState<{ id: string; kind: NodeType; side: "in" | "out" } | null>(null);

  const [toast, setToast] = useState<ToastInfo | null>(null);
  const [wfBusy, setWfBusy] = useState(false);
  const [canvasDrag, setCanvasDrag] = useState(false);
  const [drawerNodeId, setDrawerNodeId] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<
    { mode: "workflow" } | { mode: "node"; nodeId: string } | null
  >(null);
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
    | null
  >(null);

  const nodes = graph.nodes;
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;


  const showToast = useCallback(
    (message: string, type: ToastInfo["type"] = "ok", nodeId?: string) => {
      const id = Date.now();
      setToast({ id, message, type, nodeId });
      window.setTimeout(() => setToast((cur) => (cur?.id === id ? null : cur)), 4200);
    },
    [],
  );

  // -- persistence ---------------------------------------------------------- //
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(graph));
    } catch {
      /* quota */
    }
  }, [graph]);

  // -- node options ---------------------------------------------------------- //
  useEffect(() => {
    api
      .nodeOptions()
      .then(setOpts)
      .catch(() => {
        /* fallback */
      });
  }, []);

  const patchNode = useCallback((id: string, patch: Partial<CanvasNode>) => {
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    }));
  }, []);

  // -- background pan + node drag ------------------------------------------- //
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      if (d.kind === "pan") {
        setView((v) => ({ ...v, x: d.ox + (e.clientX - d.sx), y: d.oy + (e.clientY - d.sy) }));
      } else {
        const z = viewRef.current.z;
        setGraph((g) => ({
          ...g,
          nodes: g.nodes.map((n) =>
            n.id === d.id
              ? { ...n, x: d.ox + (e.clientX - d.sx) / z, y: d.oy + (e.clientY - d.sy) / z }
              : n,
          ),
        }));
      }
    };
    const up = () => {
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

  // -- escape cancels linking, context menu, or closes drawer ----------------- //
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (contextMenu) setContextMenu(null);
        else if (linking) setLinking(null);
        else if (drawerNodeId) setDrawerNodeId(null);
      }
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
    }
    if (!patch.reason && j.error) patch.reason = j.error;
    return patch;
  }

  // -- run one node (submit + await terminal) --------------------------------- //
  const runNodeNow = useCallback(
    async (nodeId: string, dry: boolean): Promise<{ ok: boolean; fileUrl?: string | null }> => {
      const n = nodesRef.current.find((x) => x.id === nodeId);
      if (!n) return { ok: false };


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
        const ok = final.state === "succeeded";
        if (!ok && !dry) {
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

  // -- run whole workflow (topological execution in chain order) ---------------- //
  const runWorkflow = useCallback(
    async (dry: boolean) => {
      if (wfBusy) return;
      setWfBusy(true);
      setConfirmTarget(null);
      try {
        const current = nodesRef.current;
        // Non-ref nodes sorted by chain depth so parent outputs are ready before child runs
        const runnable = current
          .filter((n) => n.type !== "ref")
          .sort((a, b) => chainDepth(current, a) - chainDepth(current, b));

        if (runnable.length === 0) {
          showToast("Canvas trống — thêm node trước khi chạy.", "err");
          return;
        }

        const srcOk = new Map<string, boolean>();
        for (const n of current.filter((x) => x.type === "ref")) srcOk.set(n.id, !!n.fileUrl);

        for (const n of runnable) {
          const sids = getNodeSourceIds(n);
          if (sids.some((sid) => srcOk.get(sid) === false)) {
            patchNode(n.id, {
              status: "skipped",
              reason: "Node nguồn không thành công — bỏ qua node này.",
            });
            srcOk.set(n.id, false);
            continue;
          }
          const r = await runNodeNow(n.id, dry);
          srcOk.set(n.id, r.ok);
          if (!r.ok && !dry) {
            showToast(`Dừng workflow: node lỗi.`, "err", n.id);
            return;
          }
        }
        showToast(dry ? "Dry-run workflow hoàn tất." : "Workflow hoàn tất!", "ok");
      } finally {
        setWfBusy(false);
      }
    },
    [wfBusy, runNodeNow, patchNode, showToast],
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
    }));
    if (linking?.id === id) setLinking(null);
    if (drawerNodeId === id) setDrawerNodeId(null);
  };

  const uploadRef = useCallback(
    async (id: string, file: File) => {
      if (!file.type.startsWith("image/")) {
        showToast("Chỉ nhận file ảnh (PNG/JPG/WebP).", "err");
        return;
      }
      patchNode(id, { reason: null, status: "queued" });
      try {
        const r = await api.upload(file);
        patchNode(id, { fileUrl: r.url, fileName: file.name, status: "succeeded", reason: null });
      } catch (e) {
        patchNode(id, {
          status: "failed",
          reason: e instanceof Error ? e.message : "Upload thất bại",
        });
        showToast("Upload ảnh tham chiếu thất bại.", "err", id);
      }
    },
    [patchNode, showToast],
  );

  const dropFiles = (e: React.DragEvent) => {
    e.preventDefault();
    setCanvasDrag(false);
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

  const loadTemplate = useCallback(
    (name: "tryon") => {
      if (name === "tryon") {
        const tplNodes = createTryOnTemplate();
        setGraph({ nodes: tplNodes });
        setView({ x: 20, y: 30, z: 0.82 });
        showToast("Đã khởi tạo Mẫu Workflow: Video Thử Đồ (6 nodes liên kết)", "ok");
      }
    },
    [showToast],
  );

  useImperativeHandle(
    ref,
    () => ({
      addNode,
      loadTemplate,
      runWorkflow,
      openConfirmWorkflow: () => setConfirmTarget({ mode: "workflow" }),
    }),
    [addNode, loadTemplate, runWorkflow],
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
          dragRef.current = { kind: "pan", sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
          setLinking(null);
        }}
      >
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

        <div className="absolute right-3 bottom-3 z-20 text-[10.5px] text-mut bg-panel/85 border border-line rounded-ctl px-2.5 py-1.5 max-w-[320px] leading-relaxed">
          Nối <strong>Video → Frame Cuối → Video tiếp theo</strong> để tạo chuỗi video liền mạch giống Try-On.
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
              return (
                <g key={`${from.id}->${to.id}`}>
                  <path
                    d={`M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`}
                    fill="none"
                    stroke={active ? "var(--color-ok)" : "var(--color-acc)"}
                    strokeOpacity={active ? 0.9 : 0.55}
                    strokeWidth={2}
                    strokeDasharray={active ? undefined : "6 5"}
                    markerEnd="url(#cv-arrow)"
                  />
                </g>
              );
            })}
          </svg>

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
              onOpenDrawer={(id) => setDrawerNodeId(id)}
              onHeaderDown={(e) => {
                e.stopPropagation();
                dragRef.current = { kind: "node", id: n.id, sx: e.clientX, sy: e.clientY, ox: n.x, oy: n.y };
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
        </div>
      )}

      {/* Right Drawer for Logs & Errors */}
      <CanvasDrawer
        node={drawerNode}
        allNodes={nodes}
        onClose={() => setDrawerNodeId(null)}
        onRunNode={(id, dry) => void runNodeNow(id, dry)}
        onRemoveNode={removeNode}
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
                ? `Sẽ chạy ${imageNodes.length} node ảnh + ${videoNodes.length} node video + ${lastFrameNodes.length} node frame cuối qua tài khoản Flow theo chuỗi.`
                : "Sẽ chạy node này qua tài khoản Flow."}
            </p>
            <p className="text-[12px] leading-relaxed text-warn bg-warn/5 border border-warn/25 rounded-ctl px-3 py-2">
              Chi phí ước tính ~
              {confirmTarget.mode === "workflow"
                ? ` ${imageNodes.length + videoNodes.length} credit (các node Frame Cuối: 0 credit)`
                : " 1 credit"}{" "}
              nếu Google nhận (bị từ chối = 0 credit).
            </p>
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
  onOpenDrawer: (id: string) => void;
  onHeaderDown: (e: React.PointerEvent) => void;
}) {
  const { n, allNodes, imageRatios, verifiedRatios, videoRatios, resolutions, linking, wfBusy } = props;
  const st = statusStyle(n.status);
  const isRef = n.type === "ref";
  const isImg = n.type === "image";
  const isVid = n.type === "video";
  const isLastFrame = n.type === "last_frame";

  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentSids = getNodeSourceIds(n);
  const connectedSources = currentSids
    .map((sid) => allNodes.find((i) => i.id === sid))
    .filter(Boolean) as CanvasNode[];

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

  return (
    <div
      className={`canvas-node-card absolute rounded-panel border-2 bg-panel shadow-xl ${st.border}`}
      style={{ left: n.x, top: n.y, width: NODE_W }}
      onPointerDown={(e) => e.stopPropagation()}
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
              onClick={() => fileInputRef.current?.click()}
              className={`rounded-ctl border border-dashed bg-panel2 cursor-pointer overflow-hidden transition-colors ${
                dragOver ? "border-acc bg-acc/10" : "border-line2 hover:border-acc/60"
              }`}
              title="Bấm hoặc kéo-thả ảnh vào đây"
            >
              {n.fileUrl ? (
                <img src={n.fileUrl} alt="Ảnh tham chiếu" className="w-full max-h-44 object-contain" />
              ) : (
                <div className="flex flex-col items-center gap-1.5 py-7 text-mut">
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
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold text-mut">
                  Ảnh tham chiếu ({connectedSources.length})
                </span>
                {connectedSources.length > 0 && (
                  <button
                    type="button"
                    onClick={() => props.onSourcesChange([])}
                    className="text-[9.5px] text-mut hover:text-err cursor-pointer"
                    title="Bỏ tất cả ảnh tham chiếu"
                  >
                    Xóa hết
                  </button>
                )}
              </div>

              {/* List of connected reference thumbnails / chips */}
              {connectedSources.length > 0 && (
                <div className="flex flex-col gap-1 max-h-36 overflow-y-auto slim-scroll pr-0.5">
                  {connectedSources.map((src, idx) => (
                    <div
                      key={src.id}
                      className="group flex items-center justify-between gap-1.5 bg-panel2/90 border border-line2 rounded-ctl px-2 py-1 text-[10.5px]"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {src.fileUrl ? (
                          <img
                            src={src.fileUrl}
                            alt=""
                            className="size-6 rounded object-cover border border-line2 shrink-0 opacity-90"
                          />
                        ) : (
                          <div className="size-6 rounded bg-panel border border-line2 grid place-items-center text-mut shrink-0">
                            <ImageIcon size={12} />
                          </div>
                        )}
                        <div className="flex flex-col min-w-0">
                          <span className="truncate text-fg font-medium leading-tight">
                            #{idx + 1}: {src.type === "ref" ? (src.fileName ?? src.id) : (src.prompt ? src.prompt.slice(0, 18) + "…" : src.id)}
                          </span>
                          <span className="text-[9px] text-mut truncate">
                            {src.type === "ref" ? "Ảnh upload" : src.type === "last_frame" ? "Frame cuối" : "Node ảnh"}
                            {!src.fileUrl && src.status !== "succeeded" ? " (chưa có kết quả)" : ""}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          const next = currentSids.filter((id) => id !== src.id);
                          props.onSourcesChange(next);
                        }}
                        className="text-mut hover:text-err p-1 rounded hover:bg-panel transition-colors cursor-pointer shrink-0 ml-1"
                        title="Gỡ ảnh tham chiếu này"
                      >
                        <X size={12} weight="bold" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Selector to add another source */}
              {availableOptions.length > 0 && (
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      props.onSourcesChange([...currentSids, e.target.value]);
                    }
                  }}
                  className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none cursor-pointer"
                >
                  <option value="">
                    {connectedSources.length === 0
                      ? "+ Chọn ảnh tham chiếu (tùy chọn)"
                      : "+ Nối thêm ảnh tham chiếu…"}
                  </option>
                  {availableOptions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {sourceLabel(i)}
                    </option>
                  ))}
                </select>
              )}

              {sourceBlocked && (
                <p className="text-[10px] text-warn leading-snug">
                  Một số node nguồn chưa có kết quả — hãy chạy trước khi chạy node này.
                </p>
              )}
            </div>

            <textarea
              rows={2}
              value={n.prompt}
              onChange={(e) => props.onPromptChange(e.target.value)}
              placeholder="Prompt mô tả ảnh cần tạo…"
              className="w-full rounded-ctl border border-line2 bg-panel2 p-2 text-[11px] font-mono text-fg focus:border-acc outline-none resize-y leading-relaxed"
            />

            <div className="grid grid-cols-2 gap-1.5">
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] font-semibold text-mut">Tỷ lệ</span>
                <select
                  value={n.aspectRatio}
                  onChange={(e) => props.onFieldChange({ aspectRatio: e.target.value })}
                  className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
                >
                  {imageRatios.map((r) => (
                    <option key={r} value={r}>
                      {r}
                      {verifiedRatios.has(r) ? "" : " (chưa verify)"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] font-semibold text-mut">Seed (tùy chọn)</span>
                <input
                  type="number"
                  min={1}
                  max={2147483647}
                  value={n.seed ?? ""}
                  onChange={(e) =>
                    props.onFieldChange({ seed: e.target.value === "" ? null : Number(e.target.value) })
                  }
                  placeholder="random"
                  className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
                />
              </label>
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

            <textarea
              rows={2}
              value={n.prompt}
              onChange={(e) => props.onPromptChange(e.target.value)}
              placeholder="Prompt chuyển động cho video 8s…"
              className="w-full rounded-ctl border border-line2 bg-panel2 p-2 text-[11px] font-mono text-fg focus:border-acc outline-none resize-y leading-relaxed"
            />

            <div className="grid grid-cols-2 gap-1.5">
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] font-semibold text-mut">Tỷ lệ video</span>
                <select
                  value={n.videoRatio}
                  onChange={(e) => props.onFieldChange({ videoRatio: e.target.value })}
                  className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
                >
                  {videoRatios.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-[10px] font-semibold text-mut">Độ phân giải</span>
                <select
                  value={n.resolution}
                  onChange={(e) => props.onFieldChange({ resolution: e.target.value })}
                  className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
                >
                  {resolutions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {!n.sourceImageId && (
              <input
                value={n.autoImagePrompt}
                onChange={(e) => props.onFieldChange({ autoImagePrompt: e.target.value })}
                placeholder="Prompt ảnh khung (bỏ trống = dùng prompt chính)"
                className="w-full h-7 rounded-ctl border border-line2 bg-panel2 px-2 text-[10.5px] text-fg focus:border-acc outline-none"
              />
            )}
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

        {/* Result Preview */}
        {(isImg || isLastFrame ? n.fileUrl : n.videoUrl) && (
          <div className="rounded-ctl overflow-hidden border border-line2 bg-panel2 relative">
            {isImg || isLastFrame ? (
              <img src={n.fileUrl!} alt="Kết quả" className="w-full max-h-40 object-contain" />
            ) : (
              <video src={n.videoUrl!} controls className="w-full max-h-40" />
            )}
            <a
              href={isImg || isLastFrame ? n.fileUrl! : n.videoUrl!}
              download
              className="absolute top-1.5 right-1.5 grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer"
              title="Tải xuống"
            >
              <DownloadSimple size={13} />
            </a>
          </div>
        )}

        {/* Video node auto frame preview */}
        {isVid && n.frameUrl && (
          <img
            src={n.frameUrl}
            alt="Ảnh khung"
            className="rounded-ctl border border-line2 w-full max-h-16 object-cover opacity-80"
            title="Ảnh khung đã dùng / tự tạo"
          />
        )}

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

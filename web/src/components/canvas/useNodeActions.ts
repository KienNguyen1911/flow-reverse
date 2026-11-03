import { useCallback, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from "react";
import { api } from "../../api";
import type { NodeMediaOptions } from "../../types";
import { NODE_W } from "./constants";
import { clientToCanvas } from "./geometry";
import { getNodeSourceIds, isDownstream, newNode } from "./graph";
import type {
  CanvasNode,
  ContextMenuState,
  Graph,
  LinkingState,
  NodeType,
  ShowToast,
  View,
} from "./types";

/**
 * Structural edits of the node graph: add / remove nodes, upload & drop
 * reference images, and the two-click "dot → dot" linking flow.
 */
export function useNodeActions(params: {
  nodes: CanvasNode[];
  opts: NodeMediaOptions | null;
  setGraph: Dispatch<SetStateAction<Graph>>;
  patchNode: (id: string, patch: Partial<CanvasNode>) => void;
  showToast: ShowToast;
  viewRef: MutableRefObject<View>;
  viewportRef: RefObject<HTMLDivElement | null>;
  setContextMenu: Dispatch<SetStateAction<ContextMenuState | null>>;
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  linking: LinkingState | null;
  setLinking: Dispatch<SetStateAction<LinkingState | null>>;
  drawerNodeId: string | null;
  setDrawerNodeId: Dispatch<SetStateAction<string | null>>;
  setCanvasDrag: Dispatch<SetStateAction<boolean>>;
  workspaceProjectId?: string | null;
  onAssetGenerated?: () => void;
}) {
  const {
    nodes,
    opts,
    setGraph,
    patchNode,
    showToast,
    viewRef,
    viewportRef,
    setContextMenu,
    setSelectedIds,
    linking,
    setLinking,
    drawerNodeId,
    setDrawerNodeId,
    setCanvasDrag,
  } = params;

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

  const uploadRef = useCallback(
    async (id: string, file: File) => {
      if (!file.type.startsWith("image/")) {
        showToast("Chỉ nhận file ảnh (PNG/JPG/WebP).", "err");
        return;
      }
      patchNode(id, { reason: null, status: "queued" });
      try {
        const r = await api.upload(file, params.workspaceProjectId ?? null);
        patchNode(id, { fileUrl: r.url, fileName: file.name, status: "succeeded", reason: null });
        params.onAssetGenerated?.();
      } catch (e) {
        patchNode(id, {
          status: "failed",
          reason: e instanceof Error ? e.message : "Upload thất bại",
        });
        showToast("Upload ảnh tham chiếu thất bại.", "err", id);
      }
    },
    [patchNode, showToast, params.workspaceProjectId],
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
        const { x: gx, y: gy } = clientToCanvas(
          viewportRef.current?.getBoundingClientRect(),
          viewRef.current,
          e.clientX,
          e.clientY,
        );
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
    const { x: gx, y: gy } = clientToCanvas(
      viewportRef.current?.getBoundingClientRect(),
      viewRef.current,
      e.clientX,
      e.clientY,
    );
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
        const canMulti =
          dst.type === "image" ||
          (dst.type === "video" && (dst.videoSubMode ?? "frames") === "ingredients");
        if (canMulti) {
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
            const typeLabel =
              dst.type === "image" ? "node ảnh" : "node video (thành phần)";
            showToast(`Đã nối thêm ảnh tham chiếu (${nextSids.length} ảnh) → ${typeLabel}.`, "ok");
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

  return { addNodeAt, addNode, removeNode, uploadRef, addReferenceNode, dropFiles, handleDotClick };
}

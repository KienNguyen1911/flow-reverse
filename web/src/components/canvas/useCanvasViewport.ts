import { useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { NODE_W } from "./constants";
import { clamp, clientToCanvas, nodeHeight } from "./geometry";
import type {
  CanvasNode,
  ContextMenuState,
  DragState,
  Graph,
  LinkingState,
  Rect,
  View,
} from "./types";

/**
 * Pan / zoom / drag / marquee interactions of the canvas viewport.
 *
 * Owns the viewport transform and the single in-flight pointer gesture
 * (`dragRef`): background pan (middle button or Space), rubber-band selection,
 * node drag and group drag. Global pointer listeners drive the gesture; the
 * `begin*` / `onPointerDown` helpers only start one.
 */
export function useCanvasViewport(params: {
  nodesRef: MutableRefObject<CanvasNode[]>;
  heightRef: MutableRefObject<Record<string, number>>;
  selectedRef: MutableRefObject<string[]>;
  setGraph: Dispatch<SetStateAction<Graph>>;
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  setLinking: Dispatch<SetStateAction<LinkingState | null>>;
  contextMenu: ContextMenuState | null;
  setContextMenu: Dispatch<SetStateAction<ContextMenuState | null>>;
}) {
  const {
    nodesRef,
    heightRef,
    selectedRef,
    setGraph,
    setSelectedIds,
    setLinking,
    contextMenu,
    setContextMenu,
  } = params;

  const [view, setView] = useState<View>({ x: 40, y: 20, z: 1 });
  const [marquee, setMarquee] = useState<Rect | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const dragRef = useRef<DragState | null>(null);
  const spaceDownRef = useRef(false);

  // -- background pan + node / group drag + marquee selection ---------------- //
  useEffect(() => {
    const toCanvas = (clientX: number, clientY: number) =>
      clientToCanvas(viewportRef.current?.getBoundingClientRect(), viewRef.current, clientX, clientY);

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

  /** Pointer down on empty canvas: pan (middle button / Space) or start a marquee. */
  const onPointerDown = (e: React.PointerEvent) => {
    if (contextMenu) setContextMenu(null);
    const t = e.target as HTMLElement;
    if (t.closest("button, select, input, textarea, a, video")) return;
    setLinking(null);

    // Middle button or Space+drag pans the canvas; left drag on empty
    // canvas sweeps a selection rectangle (Shift = additive).
    if (e.button === 1 || spaceDownRef.current) {
      e.preventDefault();
      dragRef.current = { kind: "pan", sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
      return;
    }
    if (e.button !== 0) return;

    const p = clientToCanvas(viewportRef.current?.getBoundingClientRect(), viewRef.current, e.clientX, e.clientY);
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
  };

  /** Right-click on empty canvas opens the "add node" menu at that canvas position. */
  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    const t = e.target as HTMLElement;
    if (t.closest("button, select, input, textarea, a, video, .canvas-node-card")) return;
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) return;
    const p = clientToCanvas(rect, viewRef.current, e.clientX, e.clientY);
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      canvasX: Math.round(p.x),
      canvasY: Math.round(p.y),
    });
  };

  /** Start dragging every member of a group together (group frame header). */
  const beginGroupDrag = (
    groupId: string,
    e: React.PointerEvent,
    origin: { id: string; x: number; y: number }[],
  ) => {
    dragRef.current = { kind: "group", id: groupId, sx: e.clientX, sy: e.clientY, origin };
  };

  /** Pointer down on a node header: toggle selection (with modifier) or start a drag. */
  const onNodeHeaderDown = (
    n: CanvasNode,
    e: React.PointerEvent,
    toggleSelect: (id: string, additive: boolean) => void,
  ) => {
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
  };

  return {
    view,
    setView,
    viewRef,
    viewportRef,
    marquee,
    setMarquee,
    onPointerDown,
    onContextMenu,
    beginGroupDrag,
    onNodeHeaderDown,
  };
}

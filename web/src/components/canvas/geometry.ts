import { ANCHOR_Y, FALLBACK_NODE_H, GROUP_HEADER_H, GROUP_PAD, NODE_W } from "./constants";
import type { CanvasGroup, CanvasNode, Rect, View } from "./types";

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Map a pointer position (client px) into canvas space under the current pan/zoom. */
export function clientToCanvas(
  viewportRect: DOMRect | undefined,
  view: View,
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  return {
    x: (clientX - (viewportRect?.left ?? 0) - view.x) / view.z,
    y: (clientY - (viewportRect?.top ?? 0) - view.y) / view.z,
  };
}

export function nodeHeight(n: CanvasNode, heights: Record<string, number>): number {
  return heights[n.id] ?? FALLBACK_NODE_H;
}

/** Frame that encloses all member nodes (derived, so it always stays tight). */
export function groupFrame(
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

/** Cubic-bezier path between a node's output anchor and another node's input anchor. */
export function edgePath(from: CanvasNode, to: CanvasNode): string {
  const x1 = from.x + NODE_W;
  const y1 = from.y + ANCHOR_Y;
  const x2 = to.x;
  const y2 = to.y + ANCHOR_Y;
  const mid = Math.max(40, Math.abs(x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`;
}

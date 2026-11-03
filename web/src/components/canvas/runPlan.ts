import { chainDepth, getNodeSourceIds } from "./graph";
import type { CanvasGroup, CanvasNode, RunUnit } from "./types";

// --------------------------------------------------------------------------- //
// Visual Group / Scope
// A group is a labelled frame owning a set of nodes. Execution treats every
// group as an isolated unit: a node failure aborts only that group, the next
// group still runs. Ungrouped nodes form one virtual, implicit unit.
// --------------------------------------------------------------------------- //

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
export function buildRunUnits(nodes: CanvasNode[], groups: CanvasGroup[], selectedIds: string[]): RunUnit[] {
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
export function unitMembers(nodes: CanvasNode[], unit: RunUnit): CanvasNode[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return unit.nodeIds
    .map((id) => byId.get(id))
    .filter((n): n is CanvasNode => !!n && n.type !== "ref")
    .sort((a, b) => chainDepth(nodes, a) - chainDepth(nodes, b));
}

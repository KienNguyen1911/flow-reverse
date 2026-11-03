import type { Dispatch, SetStateAction } from "react";
import { CheckCircle, Play, X } from "@phosphor-icons/react";
import { edgePath, groupFrame } from "./geometry";
import type { CanvasGroup, CanvasNode, FocusLink, NodeStatus, Rect } from "./types";

// Visual layers drawn inside the transformed graph space, behind/around the node cards.

/** Dependency edges between nodes (arrow markers; highlighted when hovered / done). */
export function EdgesLayer({
  edges,
  focusLink,
}: {
  edges: { from: CanvasNode; to: CanvasNode }[];
  focusLink: FocusLink | null;
}) {
  return (
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
        const d = edgePath(from, to);
        const active = from.status === "succeeded";
        const focused = focusLink?.from === from.id && focusLink?.to === to.id;
        return (
          <g key={`${from.id}->${to.id}`}>
            {focused && (
              <path
                d={d}
                fill="none"
                stroke="var(--color-warn)"
                strokeOpacity={0.28}
                strokeWidth={9}
                strokeLinecap="round"
              />
            )}
            <path
              d={d}
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
  );
}

/** Rubber-band selection rectangle. */
export function MarqueeRect({ marquee }: { marquee: Rect }) {
  return (
    <div
      className="absolute border-2 border-acc bg-acc/10 rounded-[4px] pointer-events-none"
      style={{ left: marquee.x, top: marquee.y, width: marquee.w, height: marquee.h, zIndex: 5 }}
    />
  );
}

/** Visual Groups: frames drawn behind nodes. */
export function GroupFrames({
  groups,
  nodeById,
  nodeHeights,
  selectedIds,
  editingGroupId,
  setEditingGroupId,
  wfBusy,
  onBeginDrag,
  onRename,
  onRunGroup,
  onSelectGroup,
  onDissolve,
}: {
  groups: CanvasGroup[];
  nodeById: Map<string, CanvasNode>;
  nodeHeights: Record<string, number>;
  selectedIds: string[];
  editingGroupId: string | null;
  setEditingGroupId: Dispatch<SetStateAction<string | null>>;
  wfBusy: boolean;
  onBeginDrag: (
    groupId: string,
    e: React.PointerEvent,
    origin: { id: string; x: number; y: number }[],
  ) => void;
  onRename: (groupId: string, name: string) => void;
  onRunGroup: (memberIds: string[]) => void;
  onSelectGroup: (groupId: string) => void;
  onDissolve: (groupId: string) => void;
}) {
  return (
    <>
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
                onBeginDrag(
                  gr.id,
                  e,
                  members
                    .map((id) => nodeById.get(id))
                    .filter(Boolean)
                    .map((m) => ({ id: m!.id, x: m!.x, y: m!.y })),
                );
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
                  onChange={(e) => onRename(gr.id, e.target.value)}
                  onBlur={() => {
                    if (!gr.name.trim()) onRename(gr.id, "Nhóm chưa đặt tên");
                    setEditingGroupId(null);
                  }}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter" || e.key === "Escape") {
                      if (!gr.name.trim()) onRename(gr.id, "Nhóm chưa đặt tên");
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
                  onRunGroup(members);
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
                  onSelectGroup(gr.id);
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
                  onDissolve(gr.id);
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
    </>
  );
}

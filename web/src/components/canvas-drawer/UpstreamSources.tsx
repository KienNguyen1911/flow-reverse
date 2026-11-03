import { useState, type RefObject } from "react";
import { CaretDown, CaretUp, Image as ImageIcon, X } from "@phosphor-icons/react";
import { OrderBadge } from "../node-badge/NodeBadges";
import type { CanvasDrawerNode } from "./types";

interface Props {
  node: CanvasDrawerNode;
  allNodes: CanvasDrawerNode[];
  anchorRef: RefObject<HTMLDivElement | null>;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** Connected source nodes of a node; image nodes can reorder (drag / arrows), remove and add sources. */
export function UpstreamSources({ node, allNodes, anchorRef, onUpdateNode }: Props) {
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [hoverUpId, setHoverUpId] = useState<string | null>(null);

  const upstreamIds =
    Array.isArray(node.sourceImageIds) && node.sourceImageIds.length > 0
      ? node.sourceImageIds
      : node.sourceImageId
        ? [node.sourceImageId]
        : [];
  const upstreams = upstreamIds
    .map((id) => allNodes.find((x) => x.id === id))
    .filter(Boolean) as CanvasDrawerNode[];

  const canMultiRef =
    node.type === "image" ||
    (node.type === "video" && (node.videoSubMode ?? "frames") === "ingredients");

  /** Ghi lại danh sách nguồn đã sắp xếp — `sourceImageId` luôn = phần tử đầu. */
  const commitSources = (sids: string[]) => {
    onUpdateNode?.(node.id, {
      sourceImageIds: sids,
      sourceImageId: sids[0] ?? null,
      status: "idle",
      reason: null,
    });
  };

  const moveUpstream = (from: number, to: number) => {
    const sids = [...upstreamIds];
    if (to < 0 || to >= sids.length || from === to) return;
    const [moved] = sids.splice(from, 1);
    sids.splice(to, 0, moved);
    commitSources(sids);
  };

  const removeUpstream = (id: string) => commitSources(upstreamIds.filter((x) => x !== id));

  const addUpstream = (id: string) => {
    if (upstreamIds.includes(id)) return;
    commitSources([...upstreamIds, id]);
  };

  // Node nguồn có thể nối thêm: không phải chính nó, không nằm trong danh sách đã nối.
  const addableSources = allNodes
    .filter((c) => c.id !== node.id && !upstreamIds.includes(c.id))
    .filter((c) => c.type === "ref" || c.type === "image" || c.type === "last_frame")
    .map((c) => ({
      id: c.id,
      label:
        c.label ||
        (c.type === "ref"
          ? `Tham chiếu: ${c.fileName ?? c.id}`
          : c.type === "last_frame"
            ? `Frame cuối: ${c.id}`
            : `Ảnh: ${c.prompt ? c.prompt.slice(0, 24) + "…" : c.id}`),
    }));

  if (upstreams.length === 0) return null;

  return (
    <div
      ref={anchorRef}
      className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-1.5 scroll-mt-2"
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-dim">
          {upstreams.length > 1
            ? `Nguồn kết nối (${upstreams.length} ảnh tham chiếu)`
            : "Nguồn kết nối (Upstream Node)"}
        </span>
        {upstreams.length > 1 && (
          <span className="text-[9.5px] text-mut">Thứ tự = Image 1, 2, 3 trong prompt</span>
        )}
      </div>

      {upstreams.map((up, idx) => (
        <div
          key={up.id}
          draggable={canMultiRef}
          onDragStart={(e) => {
            if (!canMultiRef) return;
            e.dataTransfer.setData("text/plain", String(idx));
            e.dataTransfer.effectAllowed = "move";
            setDragIdx(idx);
          }}
          onDragOver={(e) => {
            if (!canMultiRef) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
          }}
          onDrop={(e) => {
            if (!canMultiRef) return;
            e.preventDefault();
            const from = Number(e.dataTransfer.getData("text/plain"));
            const to = idx;
            if (Number.isFinite(from) && from !== to) moveUpstream(from, to);
            setDragIdx(null);
          }}
          onDragEnd={() => setDragIdx(null)}
          onMouseEnter={() => setHoverUpId(up.id)}
          onMouseLeave={() => setHoverUpId(null)}
          className={`flex items-center gap-2 rounded-ctl border px-2 py-1.5 text-[11.5px] transition-colors ${
            dragIdx === idx
              ? "border-acc/70 bg-acc/10"
              : hoverUpId === up.id
                ? "border-warn/50 bg-warn/5"
                : "border-line2 bg-panel"
          } ${canMultiRef ? "cursor-grab active:cursor-grabbing" : ""}`}
        >
          {canMultiRef ? <OrderBadge index={idx + 1} size="sm" /> : null}
          {up.fileUrl ? (
            <img
              src={up.fileUrl}
              alt=""
              className="size-8 object-cover rounded border border-line2 shrink-0"
            />
          ) : (
            <div className="size-8 grid place-items-center rounded border border-line2 bg-panel2 text-mut shrink-0">
              <ImageIcon size={13} />
            </div>
          )}
          <div className="flex flex-col min-w-0 flex-1">
            <span className="truncate font-semibold text-fg">
              {up.type === "ref"
                ? (up.fileName ?? up.id)
                : up.type === "video"
                  ? `Video: ${up.prompt.slice(0, 26)}…`
                  : up.type === "last_frame"
                    ? `Frame cuối: ${up.id}`
                    : `Ảnh: ${up.prompt.slice(0, 26)}…`}
            </span>
            <span className="text-[9.5px] text-mut truncate">
              {up.type === "ref" ? "Ảnh upload" : up.type === "last_frame" ? "Frame cuối" : "Node ảnh"}
              {!up.fileUrl && up.status !== "succeeded" ? " · chưa có kết quả" : ""}
            </span>
          </div>
          {canMultiRef && (
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                disabled={idx === 0}
                onClick={() => moveUpstream(idx, idx - 1)}
                className="grid place-items-center size-6 rounded border border-line2 bg-panel2 text-dim hover:text-fg hover:border-line2/80 cursor-pointer transition-colors disabled:opacity-30 disabled:pointer-events-none"
                title="Đưa lên trước (giảm số thứ tự)"
              >
                <CaretUp size={11} weight="bold" />
              </button>
              <button
                type="button"
                disabled={idx === upstreams.length - 1}
                onClick={() => moveUpstream(idx, idx + 1)}
                className="grid place-items-center size-6 rounded border border-line2 bg-panel2 text-dim hover:text-fg hover:border-line2/80 cursor-pointer transition-colors disabled:opacity-30 disabled:pointer-events-none"
                title="Đưa xuống sau (tăng số thứ tự)"
              >
                <CaretDown size={11} weight="bold" />
              </button>
              <button
                type="button"
                onClick={() => removeUpstream(up.id)}
                className="grid place-items-center size-6 rounded border border-line2 bg-panel2 text-mut hover:text-err hover:border-err/50 cursor-pointer transition-colors"
                title="Gỡ kết nối ảnh tham chiếu này"
              >
                <X size={11} weight="bold" />
              </button>
            </div>
          )}
        </div>
      ))}

      {canMultiRef && addableSources.length > 0 && (
        <select
          value=""
          onChange={(e) => {
            if (e.target.value) addUpstream(e.target.value);
          }}
          className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11px] text-fg focus:border-acc outline-none cursor-pointer"
        >
          <option value="">+ Nối thêm ảnh tham chiếu…</option>
          {addableSources.map((i) => (
            <option key={i.id} value={i.id}>
              {i.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

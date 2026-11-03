import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle,
  FilmSlate,
  Image as ImageIcon,
  LinkSimple,
  ListDashes,
  Play,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
} from "@phosphor-icons/react";
import { OrderBadge } from "../../node-badge/NodeBadges";
import { Spinner } from "../../ui";
import { NODE_W } from "../constants";
import { getNodeSourceIds } from "../graph";
import type { NodeStatus } from "../types";
import { ImageNodeBody } from "./ImageNodeBody";
import { LastFrameNodeBody } from "./LastFrameNodeBody";
import { NodeResultPreview } from "./NodeResultPreview";
import { RefNodeBody } from "./RefNodeBody";
import { VideoNodeBody } from "./VideoNodeBody";
import { deriveNodeSources } from "./nodeSources";
import type { CanvasNodeCardProps, CardDropdown, NodeBodyActions } from "./types";

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

export function CanvasNodeCard(props: CanvasNodeCardProps) {
  const {
    n, allNodes, linking, wfBusy, aiGeneratingId, onGenerateAiPrompt, skillsList, itemLibrary, selected,
  } = props;
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

  const cardRef = useRef<HTMLDivElement>(null);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  useEffect(() => {
    if (!openDropdown) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as HTMLElement;
      const activeEl = cardRef.current?.querySelector(`[data-dropdown-id="${openDropdown}"]`);
      if (activeEl && activeEl.contains(target)) return;
      setOpenDropdown(null);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenDropdown(null);
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [openDropdown]);

  const dropdown: CardDropdown = {
    open: openDropdown,
    toggle: (id) => setOpenDropdown((cur) => (cur === id ? null : id)),
    close: () => setOpenDropdown(null),
  };

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

  const sources = deriveNodeSources(n, allNodes);
  const { currentSids } = sources;

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

  const isFocusSource = props.focusLink?.from === n.id;
  const isFocusTarget = props.focusLink?.to === n.id;

  const actions: NodeBodyActions = {
    onFieldChange: props.onFieldChange,
    onSourceChange: props.onSourceChange,
    onSourcesChange: props.onSourcesChange,
    onOpenDrawer: props.onOpenDrawer,
    onOpenPromptEditor: props.onOpenPromptEditor,
    onPreviewMedia: props.onPreviewMedia,
  };

  return (
    <div
      ref={cardRef}
      className={`canvas-node-card absolute rounded-panel border-2 bg-panel shadow-xl ${st.border} ${
        selected ? "ring-2 ring-acc ring-offset-2 ring-offset-ink" : ""
      } ${isFocusSource || isFocusTarget ? "canvas-node-focus" : ""} ${
        openDropdown ? "z-30" : ""
      }`}
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
        {isRef && (
          <RefNodeBody n={n} onUpload={props.onUpload} onPreviewMedia={props.onPreviewMedia} />
        )}

        {isImg && (
          <ImageNodeBody
            n={n}
            options={props}
            sources={sources}
            nodeSkills={nodeSkills}
            dropdown={dropdown}
            actions={actions}
            wfBusy={wfBusy}
            aiGeneratingId={aiGeneratingId}
            onGenerateAiPrompt={onGenerateAiPrompt}
            itemLibrary={itemLibrary}
            focusLink={props.focusLink}
            onFocusLink={props.onFocusLink}
            onHoverRef={props.onHoverRef}
          />
        )}

        {isVid && (
          <VideoNodeBody
            n={n}
            options={props}
            sources={sources}
            nodeSkills={nodeSkills}
            dropdown={dropdown}
            actions={actions}
            wfBusy={wfBusy}
            aiGeneratingId={aiGeneratingId}
            onGenerateAiPrompt={onGenerateAiPrompt}
          />
        )}

        {isLastFrame && (
          <LastFrameNodeBody
            n={n}
            sources={sources}
            onSourceChange={props.onSourceChange}
            onFieldChange={props.onFieldChange}
          />
        )}

        <NodeResultPreview n={n} onPreviewMedia={props.onPreviewMedia} />

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

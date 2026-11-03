import type { Dispatch, SetStateAction } from "react";
import {
  ArrowsCounterClockwise,
  DownloadSimple,
  FlowArrow,
  FolderSimple,
  LinkSimple,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  Plus,
  X,
} from "@phosphor-icons/react";
import { OrderBadge } from "../node-badge/NodeBadges";
import { clamp } from "./geometry";
import type { CanvasGroup, HoverRefInfo, ToastInfo, View } from "./types";

// Stateless floating chrome drawn over the canvas viewport: toast, linking
// banner, selection toolbar, export / asset buttons, zoom controls, hints and
// the reference-image tooltip.

/** Toast with an optional "Xem log →" shortcut that opens the node's drawer. */
export function CanvasToast({
  toast,
  onOpenLog,
  onDismiss,
}: {
  toast: ToastInfo;
  onOpenLog: (nodeId: string) => void;
  onDismiss: () => void;
}) {
  return (
    <div className="fixed top-16 right-5 z-40 flex items-center gap-2.5 rounded-ctl border border-line2 bg-panel px-4 py-3 shadow-2xl backdrop-blur-md text-[12.5px] animate-in fade-in slide-in-from-top-2">
      <span
        className={`size-2 rounded-full shrink-0 ${
          toast.type === "ok" ? "bg-ok" : toast.type === "err" ? "bg-err" : "bg-acc"
        }`}
      />
      <span className="font-medium text-fg max-w-[340px] truncate">{toast.message}</span>
      {toast.nodeId && (
        <button
          onClick={() => onOpenLog(toast.nodeId!)}
          className="px-2 py-0.5 rounded text-[11px] font-bold text-acc bg-acc/10 hover:bg-acc/20 transition-colors cursor-pointer shrink-0"
        >
          Xem log →
        </button>
      )}
      <button
        onClick={onDismiss}
        className="ml-1 text-mut hover:text-fg cursor-pointer shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function LinkingBanner() {
  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-acc/40 bg-panel/95 backdrop-blur-md text-[12px] text-acc shadow-lg select-none">
      <LinkSimple size={14} className="animate-pulse" />
      <span>
        Đang nối: bấm vào chấm đối diện để liên kết (Nhấn{" "}
        <kbd className="font-mono bg-panel2 px-1 rounded text-[11px]">Esc</kbd> để hủy)
      </span>
    </div>
  );
}

/** Selection / group toolbar (top-left), or a usage hint when nothing is selected. */
export function SelectionToolbar({
  selectedIds,
  groups,
  nodeCount,
  onCreateGroup,
  onAddToGroup,
  onRemoveFromGroup,
  onClearSelection,
}: {
  selectedIds: string[];
  groups: CanvasGroup[];
  nodeCount: number;
  onCreateGroup: () => void;
  onAddToGroup: (groupId: string) => void;
  onRemoveFromGroup: (groupId: string) => void;
  onClearSelection: () => void;
}) {
  return (
    <div className="absolute left-3 top-3 z-20 flex flex-col gap-1.5">
      {selectedIds.length > 0 && (
        <div className="flex items-center gap-1.5 rounded-ctl border border-acc/45 bg-panel/95 backdrop-blur-md px-2.5 py-1.5 shadow-lg text-[11.5px]">
          <span className="font-bold text-acc">{selectedIds.length} node chọn</span>
          <span className="h-3.5 w-px bg-line2" />
          <button
            type="button"
            onClick={onCreateGroup}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-[6px] bg-acc text-accink font-bold hover:bg-acc2 cursor-pointer"
            title="Tạo nhóm từ node đã chọn (Ctrl+G)"
          >
            <Plus size={11} weight="bold" />
            Tạo nhóm
          </button>
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) onAddToGroup(e.target.value);
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
                if (e.target.value) onRemoveFromGroup(e.target.value);
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
            onClick={onClearSelection}
            className="text-mut hover:text-fg cursor-pointer"
            title="Bỏ chọn (Esc)"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {groups.length === 0 && selectedIds.length === 0 && nodeCount > 0 && (
        <div className="text-[10.5px] text-mut bg-panel/85 border border-line rounded-ctl px-2.5 py-1.5 max-w-[300px] leading-relaxed">
          Kéo chuột trên nền để <strong className="text-fg">quét chọn</strong> node · Giữ{" "}
          <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Shift</kbd> + click để chọn
          từng node · Ctrl+G để gom nhóm.
        </div>
      )}
    </div>
  );
}

/** Xuất bộ dựng phim — gom file thật vào một thư mục cho HyperFrames desktop */
export function DeliveryButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute right-3 top-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-ctl border border-line2 bg-panel/90 backdrop-blur-md text-[12px] font-semibold text-dim hover:text-fg hover:border-acc/60 hover:bg-panel2 shadow-lg transition-all cursor-pointer group"
      title="Xuất plate + clip + cutout thành thư mục cho HyperFrames desktop"
    >
      <DownloadSimple size={15} weight="bold" className="text-acc group-hover:scale-110 transition-transform" />
      <span>Xuất bộ dựng phim</span>
    </button>
  );
}

/** Floating Left Assets Drawer Toggle */
export function AssetDrawerToggle({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute left-3 top-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-ctl border border-line2 bg-panel/90 backdrop-blur-md text-[12px] font-semibold text-dim hover:text-fg hover:border-acc/60 hover:bg-panel2 shadow-lg transition-all cursor-pointer group"
      title="Mở Kho Assets [Phím tắt: A]"
    >
      <FolderSimple size={15} weight="bold" className="text-acc group-hover:scale-110 transition-transform" />
      <span>Kho Assets</span>
      <span className="text-[10px] text-mut font-mono bg-panel2 px-1 rounded">A</span>
    </button>
  );
}

export function ZoomControls({
  zoom,
  setView,
}: {
  zoom: number;
  setView: Dispatch<SetStateAction<View>>;
}) {
  return (
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
      <span className="text-[11px] font-mono text-mut px-1">{Math.round(zoom * 100)}%</span>
    </div>
  );
}

export function NavigationHint() {
  return (
    <div className="absolute right-3 bottom-3 z-20 text-[10.5px] text-mut bg-panel/85 border border-line rounded-ctl px-2.5 py-1.5 max-w-[340px] leading-relaxed">
      Kéo nền để <strong className="text-fg">quét chọn</strong> ·{" "}
      <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Shift</kbd>+click chọn từng
      node · Giữ <kbd className="font-mono bg-panel2 px-1 rounded text-[10px]">Space</kbd> hoặc
      chuột giữa để <strong className="text-fg">di chuyển canvas</strong>.
    </div>
  );
}

export function FileDropOverlay() {
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-acc/5 pointer-events-none">
      <span className="text-[13px] font-semibold text-acc">Thả ảnh để tạo node Ảnh tham chiếu</span>
    </div>
  );
}

export function EmptyCanvasHint() {
  return (
    <div className="absolute inset-0 grid place-items-center pointer-events-none">
      <div className="flex flex-col items-center gap-2 text-mut">
        <FlowArrow size={34} weight="thin" />
        <p className="text-[12.5px] font-medium">Canvas trống</p>
        <p className="text-[11px]">
          Thêm <span className="text-acc">Node Ảnh</span> hoặc <span className="text-acc">Node Video</span> để bắt đầu workflow.
        </p>
      </div>
    </div>
  );
}

/**
 * Tooltip xem nhanh ảnh tham chiếu — portal ở cấp panel nên không bị
 * strip chip (overflow) cắt mất.
 */
export function RefHoverTooltip({ info }: { info: HoverRefInfo }) {
  return (
    <div
      className="fixed z-[70] pointer-events-none"
      style={{
        left: Math.min(info.x, window.innerWidth - 190),
        top: Math.min(info.y + 8, window.innerHeight - 150),
      }}
    >
      <div className="w-44 rounded-ctl border border-line2 bg-panel p-1.5 shadow-2xl">
        {info.src.fileUrl ? (
          <img
            src={info.src.fileUrl}
            alt=""
            className="w-full h-40 object-contain rounded bg-ink"
          />
        ) : (
          <div className="w-full h-40 grid place-items-center rounded bg-ink text-mut text-[10px]">
            Chưa có ảnh kết quả
          </div>
        )}
        <div className="mt-1.5 flex items-center gap-1.5">
          <OrderBadge index={info.index} size="xs" />
          <span className="text-[10px] text-dim truncate" title={info.src.fileName ?? ""}>
            {info.src.type === "ref"
              ? (info.src.fileName ?? info.src.id)
              : info.src.label || info.src.id}
          </span>
        </div>
      </div>
    </div>
  );
}

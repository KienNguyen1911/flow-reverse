import { CheckCircle, FilmSlate, Image as ImageIcon, Info, ListDashes, Play, Trash, UploadSimple, VideoCamera, Warning, X } from "@phosphor-icons/react";
import type { Job } from "../../types";
import type { CanvasDrawerNode, DrawerTab } from "./types";
import { Spinner } from "../ui";

/** Header: node icon + title and its run-status badge. */
interface HeaderProps {
  node: CanvasDrawerNode;
  hasError: boolean;
  onClose: () => void;
}

export function DrawerHeader({ node, hasError, onClose }: HeaderProps) {
  const nodeTitle =
    node.label ||
    (node.type === "ref"
      ? "Ảnh tham chiếu"
      : node.type === "image"
        ? "Node Ảnh"
        : node.type === "video"
          ? "Node Video"
          : "Trích xuất Frame Cuối");

  const nodeIcon =
    node.type === "ref" ? (
      <UploadSimple size={15} />
    ) : node.type === "image" ? (
      <ImageIcon size={15} />
    ) : node.type === "video" ? (
      <VideoCamera size={15} />
    ) : (
      <FilmSlate size={15} />
    );

  return (
    <header className="flex items-center justify-between px-4 sm:px-5 h-14 border-b border-line2 bg-panel2 shrink-0">
      <div className="flex items-center gap-2.5 truncate">
        <span
          className={`grid place-items-center size-7 rounded-ctl shrink-0 ${
            node.type === "ref" || node.type === "image"
              ? "bg-acc/15 text-acc"
              : node.type === "video"
                ? "bg-ok/15 text-ok"
                : "bg-purple-500/15 text-purple-400"
          }`}
        >
          {nodeIcon}
        </span>
        <div className="flex flex-col truncate">
          <span className="text-[13px] font-bold text-fg truncate">{nodeTitle}</span>
          <span className="text-[10px] font-mono text-mut truncate">{node.id}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {node.status === "running" ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-acc/40 bg-acc/10 text-acc text-[11px] font-semibold">
            <Spinner size={11} />
            Đang chạy
          </span>
        ) : node.status === "queued" ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-line2 bg-panel text-dim text-[11px] font-semibold">
            Trong hàng đợi
          </span>
        ) : node.status === "succeeded" ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-ok/40 bg-ok/10 text-ok text-[11px] font-semibold">
            <CheckCircle size={12} weight="fill" />
            Thành công
          </span>
        ) : hasError ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-err/40 bg-err/10 text-err text-[11px] font-semibold">
            <Warning size={12} weight="fill" />
            {node.status === "rejected" ? "Bị từ chối" : node.status === "skipped" ? "Bỏ qua" : "Thất bại"}
          </span>
        ) : null}

        <button
          onClick={onClose}
          className="grid place-items-center size-7 rounded-ctl hover:bg-panel border border-transparent hover:border-line2 text-mut hover:text-fg transition-colors cursor-pointer"
          title="Đóng (Esc)"
        >
          <X size={15} />
        </button>
      </div>
    </header>
  );
}

/** Tab strip (error tab only when the node failed; result tab only once there is media). */
interface TabsProps {
  node: CanvasDrawerNode;
  job: Job | null;
  hasError: boolean;
  activeTab: DrawerTab;
  onTabChange: (tab: DrawerTab) => void;
}

export function DrawerTabs({ node, job, hasError, activeTab, onTabChange }: TabsProps) {
  return (
    <div className="flex items-center gap-1 px-4 border-b border-line2 bg-panel shrink-0 text-[11.5px] font-semibold">
      {hasError && (
        <button
          onClick={() => onTabChange("error")}
          className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
            activeTab === "error"
              ? "border-err text-err font-bold"
              : "border-transparent text-dim hover:text-fg"
          }`}
        >
          <Warning size={13} weight="fill" className="text-err" />
          <span>Lỗi & Giải pháp</span>
        </button>
      )}

      <button
        onClick={() => onTabChange("logs")}
        className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
          activeTab === "logs"
            ? "border-acc text-acc font-bold"
            : "border-transparent text-dim hover:text-fg"
        }`}
      >
        <ListDashes size={13} />
        <span>Nhật ký (Logs)</span>
        {job?.events && job.events.length > 0 && (
          <span className="size-4 rounded-full bg-panel2 border border-line2 text-[9px] font-mono grid place-items-center text-mut">
            {job.events.length}
          </span>
        )}
      </button>

      <button
        onClick={() => onTabChange("config")}
        className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
          activeTab === "config"
            ? "border-acc text-acc font-bold"
            : "border-transparent text-dim hover:text-fg"
        }`}
      >
        <Info size={13} />
        <span>Cấu hình</span>
      </button>

      {(node.fileUrl || node.videoUrl) && (
        <button
          onClick={() => onTabChange("preview")}
          className={`h-9 px-3 border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
            activeTab === "preview"
              ? "border-ok text-ok font-bold"
              : "border-transparent text-dim hover:text-fg"
          }`}
        >
          <CheckCircle size={13} weight="fill" className="text-ok" />
          <span>Kết quả</span>
        </button>
      )}
    </div>
  );
}

/** Footer actions: delete, stop (while running), re-run and close. */
interface FooterProps {
  node: CanvasDrawerNode;
  isRunning: boolean;
  stopping: boolean;
  onStopRetry: () => Promise<void>;
  onRunNode: (id: string, dry: boolean) => void;
  onRemoveNode: (id: string) => void;
  onClose: () => void;
}

export function DrawerFooter({ node, isRunning, stopping, onStopRetry, onRunNode, onRemoveNode, onClose }: FooterProps) {
  return (
    <footer className="p-4 border-t border-line2 bg-panel2 shrink-0 flex items-center justify-between gap-2">
      <button
        onClick={() => onRemoveNode(node.id)}
        className="inline-flex items-center gap-1 px-3 h-8 rounded-ctl text-err hover:bg-err/10 border border-transparent hover:border-err/20 text-[11.5px] font-semibold cursor-pointer transition-colors"
      >
        <Trash size={13} />
        <span>Xóa node</span>
      </button>

      <div className="flex items-center gap-2">
        {isRunning && node.jobId && (
          <button
            onClick={() => void onStopRetry()}
            disabled={stopping}
            className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-err/40 bg-err/10 hover:bg-err/20 text-err text-[11.5px] font-semibold cursor-pointer transition-colors disabled:opacity-50"
            title="Dừng node đang chạy (hủy cả thời gian chờ retry)"
          >
            <X size={12} weight="bold" />
            <span>{stopping ? "Đang dừng…" : "Dừng"}</span>
          </button>
        )}
        <button
          onClick={() => onRunNode(node.id, false)}
          className="inline-flex items-center gap-1.5 px-4 h-8 rounded-ctl bg-acc hover:bg-acc2 text-accink text-[12px] font-bold cursor-pointer transition-colors shadow-sm"
        >
          <Play size={11} weight="fill" />
          <span>Chạy lại</span>
        </button>
        <button
          onClick={onClose}
          className="px-3.5 h-8 rounded-ctl border border-line2 hover:border-line bg-panel text-dim hover:text-fg text-[12px] font-semibold cursor-pointer transition-colors"
        >
          Đóng
        </button>
      </div>
    </footer>
  );
}

import { ArrowClockwise, CheckCircle, Clock, FilmStrip, Hourglass, Queue, SidebarSimple } from "@phosphor-icons/react";
import type { Dispatch, SetStateAction } from "react";
import type { DockTab, ViewMode } from "./types";

interface Props {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  historyCount: number;
  runningCount: number;
  queuedCount: number;
  doneCount: number;
  totalJobCount: number;
  setDockTab: (tab: DockTab) => void;
  isStudioCollapsed: boolean;
  onToggleCollapsed: () => void;
  jobsDrawerOpen: boolean;
  setJobsDrawerOpen: Dispatch<SetStateAction<boolean>>;
  onRefresh: () => void;
}

/** Top bar: Studio/History switcher, live job counters and layout controls. */
export function WorkspaceToolbar({
  viewMode,
  setViewMode,
  historyCount,
  runningCount,
  queuedCount,
  doneCount,
  totalJobCount,
  setDockTab,
  isStudioCollapsed,
  onToggleCollapsed,
  jobsDrawerOpen,
  setJobsDrawerOpen,
  onRefresh,
}: Props) {
  return (
    <div className="rounded-panel border border-line bg-panel p-2.5 sm:px-4 sm:py-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
      {/* Left: View Switcher */}
      <div className="flex items-center gap-1.5 bg-panel2 p-1 rounded-ctl border border-line">
        <button
          onClick={() => setViewMode("studio")}
          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-ctl text-[12px] font-semibold transition-all cursor-pointer ${
            viewMode === "studio"
              ? "bg-panel text-acc border border-line2 shadow-xs"
              : "text-dim hover:text-fg"
          }`}
        >
          <FilmStrip size={15} weight={viewMode === "studio" ? "fill" : "regular"} />
          <span>Studio & Giám sát</span>
        </button>
        <button
          onClick={() => setViewMode("history")}
          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-ctl text-[12px] font-semibold transition-all cursor-pointer ${
            viewMode === "history"
              ? "bg-panel text-acc border border-line2 shadow-xs"
              : "text-dim hover:text-fg"
          }`}
        >
          <Clock size={15} weight={viewMode === "history" ? "fill" : "regular"} />
          <span>Thư viện Lịch sử ({historyCount})</span>
        </button>
      </div>

      {/* Center: Live Pipeline Status Counters */}
      <div className="flex items-center gap-2 overflow-x-auto text-[11.5px] font-mono">
        <button
          onClick={() => {
            setViewMode("studio");
            setDockTab("running");
            setJobsDrawerOpen(true);
          }}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-all cursor-pointer ${
            runningCount > 0
              ? "border-acc/40 bg-acc/10 text-acc"
              : "border-line2 bg-panel2/50 text-mut hover:text-fg"
          }`}
          title="Số job đang chạy render video"
        >
          <span
            className={`size-2 rounded-full bg-acc ${
              runningCount > 0 ? "animate-pulse" : ""
            }`}
          />
          <span className="font-sans font-medium">Đang chạy:</span>
          <span className="font-bold">{runningCount}</span>
        </button>

        <button
          onClick={() => {
            setViewMode("studio");
            setDockTab("queued");
            setJobsDrawerOpen(true);
          }}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-all cursor-pointer ${
            queuedCount > 0
              ? "border-line2 bg-panel2 text-dim hover:text-fg"
              : "border-line bg-panel2/30 text-mut"
          }`}
          title="Số job trong hàng đợi"
        >
          <Hourglass size={13} className="text-mut" />
          <span className="font-sans font-medium">Hàng đợi:</span>
          <span className="font-bold">{queuedCount}</span>
        </button>

        <button
          onClick={() => {
            setViewMode("studio");
            setDockTab("done");
            setJobsDrawerOpen(true);
          }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-ok/20 bg-ok/5 text-ok/90 hover:border-ok/40 transition-all cursor-pointer"
          title="Số job đã hoàn thành phiên làm việc"
        >
          <CheckCircle size={13} weight="fill" className="text-ok" />
          <span className="font-sans font-medium">Đã xong:</span>
          <span className="font-bold">{doneCount}</span>
        </button>
      </div>

      {/* Right: Studio layout controls */}
      <div className="flex items-center gap-2">
        {viewMode === "studio" && (
          <button
            onClick={() => onToggleCollapsed()}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-ctl border text-[11.5px] font-medium transition-colors cursor-pointer ${
              isStudioCollapsed
                ? "border-acc/40 bg-acc/10 text-acc"
                : "border-line2 bg-panel2 text-mut hover:text-fg"
            }`}
            title={isStudioCollapsed ? "Mở rộng bảng Setup Studio" : "Thu gọn bảng Setup để xem video rộng hơn"}
          >
            <SidebarSimple size={15} />
            <span>{isStudioCollapsed ? "Hiện Setup" : "Thu gọn Setup"}</span>
          </button>
        )}

        <button
          onClick={() => setJobsDrawerOpen((o) => !o)}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-ctl border text-[11.5px] font-medium transition-colors cursor-pointer ${
            jobsDrawerOpen
              ? "border-acc/40 bg-acc/10 text-acc"
              : "border-line2 bg-panel2 text-mut hover:text-fg"
          }`}
          title="Mở/đóng danh sách Jobs"
        >
          <Queue size={15} />
          <span>{`Jobs (${totalJobCount})`}</span>
        </button>

        <button
          onClick={() => {
            onRefresh();
          }}
          className="inline-grid place-items-center size-8 rounded-ctl border border-line2 bg-panel2 text-dim hover:text-fg transition-colors cursor-pointer"
          title="Làm mới trạng thái jobs & lịch sử"
        >
          <ArrowClockwise size={15} />
        </button>
      </div>
    </div>
  );
}

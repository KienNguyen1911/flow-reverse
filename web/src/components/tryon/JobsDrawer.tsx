import { Queue, X } from "@phosphor-icons/react";
import type { Job } from "../../types";
import type { DockTab } from "./types";
import { formatRelativeTime } from "./format";

interface Props {
  open: boolean;
  onClose: () => void;
  dockTab: DockTab;
  onDockTabChange: (tab: DockTab) => void;
  tryonJobs: Job[];
  runningJobs: Job[];
  queuedJobs: Job[];
  doneJobs: Job[];
  inspectedJobId: string | null;
  onSelectJob: (job: Job) => void;
  onReuse: (job: Job) => void;
}

/** Slide-over list of try-on jobs, filterable by state. */
export function JobsDrawer({
  open,
  onClose,
  dockTab,
  onDockTabChange,
  tryonJobs,
  runningJobs,
  queuedJobs,
  doneJobs,
  inspectedJobId,
  onSelectJob,
  onReuse,
}: Props) {
  const drawerJobs =
    dockTab === "running" ? runningJobs : dockTab === "queued" ? queuedJobs : dockTab === "done" ? doneJobs : tryonJobs;

  return (
    <aside
      className={`fixed right-0 top-0 bottom-0 z-40 w-[360px] max-w-[92vw] bg-panel border-l border-line2 shadow-2xl flex flex-col transition-transform duration-200 ${
        open ? "translate-x-0" : "translate-x-full invisible"
      }`}
      aria-hidden={!open}
    >
      <div className="flex items-center justify-between px-3.5 py-3 border-b border-line">
        <span className="text-[13px] font-bold text-fg flex items-center gap-2">
          <Queue size={16} className="text-acc" />
          Jobs Video Thử Đồ
        </span>
        <button
          onClick={() => onClose()}
          className="size-7 grid place-items-center rounded-ctl text-mut hover:text-fg hover:bg-panel2 cursor-pointer"
          title="Đóng"
        >
          <X size={15} />
        </button>
      </div>

      <div className="flex items-center gap-1 px-3 py-2 border-b border-line text-[11.5px] overflow-x-auto">
        {(
          [
            ["all", `Tất cả (${tryonJobs.length})`],
            ["running", `Đang chạy (${runningJobs.length})`],
            ["queued", `Hàng đợi (${queuedJobs.length})`],
            ["done", `Đã xong (${doneJobs.length})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => onDockTabChange(key)}
            className={`px-2.5 py-1 rounded-ctl font-semibold whitespace-nowrap transition-colors cursor-pointer ${
              dockTab === key ? "bg-acc/15 text-acc border border-acc/30" : "text-dim hover:text-fg"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="slim-scroll flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {drawerJobs.map((job) => {
          const isSelected = inspectedJobId === job.id;
          const p1 = (job.params as Record<string, string>)?.video_prompt_1 || "";
          const ar = (job.params as Record<string, string>)?.aspect_ratio || "9:16";
          return (
            <div
              key={job.id}
              onClick={() => onSelectJob(job)}
              className={`p-2.5 rounded-ctl border text-[11px] flex flex-col gap-1.5 cursor-pointer transition-all ${
                isSelected
                  ? "border-acc bg-acc/10 shadow-xs"
                  : "border-line bg-panel2/60 hover:bg-panel2 hover:border-line2"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-fg font-semibold truncate">{job.id}</span>
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[9.5px] font-bold uppercase shrink-0 ${
                    job.state === "running"
                      ? "bg-acc/20 text-acc animate-pulse"
                      : job.state === "queued"
                      ? "bg-line2 text-dim"
                      : job.state === "succeeded"
                      ? "bg-ok/20 text-ok"
                      : "bg-err/20 text-err"
                  }`}
                >
                  {job.state}
                </span>
              </div>
              <p className="text-dim line-clamp-2 text-[10.5px] leading-snug">
                {p1 || "(Không có mô tả prompt)"}
              </p>
              <div className="flex items-center justify-between text-[10px] text-mut font-mono pt-1 border-t border-line/60">
                <span>{ar}</span>
                <span>{formatRelativeTime(job.created_ms)}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onReuse(job);
                  }}
                  className="text-acc hover:underline font-sans cursor-pointer"
                  title="Tái sử dụng prompt này"
                >
                  Tái sử dụng
                </button>
              </div>
            </div>
          );
        })}
        {drawerJobs.length === 0 && (
          <div className="py-10 text-center text-mut text-[11.5px]">Không có job nào trong mục này.</div>
        )}
      </div>
    </aside>
  );
}

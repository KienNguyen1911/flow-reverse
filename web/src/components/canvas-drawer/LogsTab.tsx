import { useMemo, useState, type RefObject } from "react";
import { Copy, Terminal, X } from "@phosphor-icons/react";
import type { Job, JobEvent } from "../../types";
import { isWaitingRetry } from "./errorDiagnosis";
import type { CanvasDrawerNode } from "./types";
import { Spinner } from "../ui";

const KIND_CLS: Record<string, string> = {
  step: "text-dim border-line2 bg-panel2",
  info: "text-dim border-line2 bg-panel2",
  capture: "text-acc border-acc/30 bg-acc/10",
  fired: "text-acc border-acc/30 bg-acc/10",
  response: "text-acc border-acc/30 bg-acc/10",
  download: "text-ok border-ok/30 bg-ok/10",
  done: "text-ok border-ok/30 bg-ok/10",
  warn: "text-warn border-warn/30 bg-warn/10",
  retry: "text-warn border-warn/30 bg-warn/10",
  error: "text-err border-err/30 bg-err/10",
  debug: "text-mut border-line bg-panel2",
};

function hhmmss(ts: number) {
  return new Date(ts).toTimeString().slice(0, 8);
}

interface Props {
  node: CanvasDrawerNode;
  job: Job | null;
  loadingJob: boolean;
  isRunning: boolean;
  stopping: boolean;
  onStopRetry: () => Promise<void>;
  scrollRef: RefObject<HTMLDivElement | null>;
}

/** Logs tab: anti-abuse retry banner, job id, copy-all and the event terminal. */
export function LogsTab({ node, job, loadingJob, isRunning, stopping, onStopRetry, scrollRef }: Props) {
  const [copiedLogs, setCopiedLogs] = useState(false);
  const waitingRetry = useMemo(() => isWaitingRetry(job?.events), [job?.events]);

  const copyAllLogs = () => {
    if (!job?.events || job.events.length === 0) return;
    const lines = job.events.map((e) => {
      const time = hhmmss(e.ts_ms);
      const dataStr = e.data && Object.keys(e.data).length > 0 ? ` ${JSON.stringify(e.data)}` : "";
      return `[${time}] [${e.kind}] ${e.message}${dataStr}`;
    });
    navigator.clipboard.writeText(lines.join("\n"));
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  return (
    <div className="flex flex-col gap-3 flex-1">
      {waitingRetry && isRunning && (
        <div className="rounded-ctl border border-warn/40 bg-warn/10 p-3 flex items-center justify-between gap-3">
          <div className="flex items-start gap-2 min-w-0">
            <Spinner size={13} className="text-warn mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-[11.5px] font-bold text-warn">
                Đang chờ để tự động thử lại (anti-abuse)
              </p>
              <p className="text-[11px] text-dim leading-relaxed">
                PUBLIC_ERROR_UNUSUAL_ACTIVITY là lỗi tạm thời — node sẽ tự chạy lại sau khi hết thời gian chờ.
              </p>
            </div>
          </div>
          <button
            onClick={() => void onStopRetry()}
            disabled={stopping}
            className="shrink-0 inline-flex items-center gap-1 px-2.5 h-7 rounded-ctl border border-err/40 bg-err/10 hover:bg-err/20 text-err text-[11px] font-semibold cursor-pointer transition-colors disabled:opacity-50"
          >
            <X size={12} />
            <span>{stopping ? "Đang dừng…" : "Dừng chờ"}</span>
          </button>
        </div>
      )}

      {/* Job summary bar */}
      <div className="flex items-center justify-between text-[11px] text-mut pb-1">
        <div className="flex items-center gap-2 truncate">
          <Terminal size={13} className="text-acc" />
          <span className="font-mono text-dim truncate">{node.jobId ?? "Chưa có Job ID"}</span>
        </div>
        {job?.events && job.events.length > 0 && (
          <button
            onClick={copyAllLogs}
            className="inline-flex items-center gap-1 text-[11px] text-dim hover:text-fg cursor-pointer transition-colors"
          >
            <Copy size={12} />
            <span>{copiedLogs ? "Đã chép!" : "Sao chép log"}</span>
          </button>
        )}
      </div>

      {/* Logs terminal box */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-[300px] max-h-[500px] overflow-y-auto rounded-ctl border border-line2 bg-ink p-3 font-mono text-[11px] leading-relaxed select-text slim-scroll flex flex-col gap-1.5"
      >
        {loadingJob && !job ? (
          <div className="grid place-items-center h-32 text-mut">
            <Spinner size={16} />
            <span className="text-[11px] mt-2">Đang tải nhật ký...</span>
          </div>
        ) : !job || !job.events || job.events.length === 0 ? (
          <div className="grid place-items-center h-32 text-mut text-center">
            <p className="text-[11.5px]">Chưa có sự kiện thực thi nào.</p>
            <p className="text-[10px] mt-1">Bấm "Chạy node" để bắt đầu ghi nhật ký.</p>
          </div>
        ) : (
          job.events.map((e: JobEvent, idx: number) => {
            const cls = KIND_CLS[e.kind] || "text-dim border-line bg-panel2";
            return (
              <div key={idx} className="flex items-start gap-2 hover:bg-panel2/30 px-1 py-0.5 rounded">
                <span className="text-mut text-[10px] shrink-0 pt-0.5">{hhmmss(e.ts_ms)}</span>
                <span
                  className={`px-1.5 py-0.2 rounded border text-[9.5px] uppercase font-bold shrink-0 ${cls}`}
                >
                  {e.kind}
                </span>
                <span className="text-fg/90 flex-1 break-words">{e.message}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

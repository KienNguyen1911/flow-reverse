import { ArrowCounterClockwise, Check, Play, Warning } from "@phosphor-icons/react";
import type { RefObject } from "react";
import type { Job } from "../../types";
import type { StepView } from "./types";
import { Spinner } from "../ui";

interface Props {
  inspectedJob: Job | null;
  activeSteps: { id: number }[];
  stepStatuses: StepView[];
  logScrollRef: RefObject<HTMLDivElement | null>;
  onResume: (stepId: number, sanitize?: boolean) => void;
}

/** Pipeline stepper (with resume/re-run actions) plus the live event log while a job is running/queued. */
export function StepProgress({ inspectedJob, activeSteps, stepStatuses, logScrollRef, onResume }: Props) {
  return (
    <div className="flex flex-col gap-2 pt-1">
      <div
        className={`grid grid-cols-2 ${
          activeSteps.length > 2 ? "sm:grid-cols-4" : "sm:grid-cols-2"
        } gap-2`}
      >
        {stepStatuses.map((s) => {
          const isRunning = s.status === "running";
          const isDone = s.status === "succeeded";
          const isFailed = s.status === "failed";
          const canResumeHere =
            inspectedJob?.state !== "running" &&
            inspectedJob?.state !== "queued" &&
            (isFailed ||
              isDone ||
              (s.status === "pending" &&
                stepStatuses.some((prev) => prev.id === s.id - 1 && prev.status === "succeeded")));

          return (
            <div
              key={s.id}
              className={`p-2.5 rounded-ctl border text-[11px] flex flex-col justify-between transition-all ${
                isFailed
                  ? "border-err bg-err/10 text-fg shadow-xs shadow-err/10"
                  : isRunning
                  ? "border-acc bg-acc/10 text-fg shadow-xs shadow-acc/10"
                  : isDone
                  ? "border-ok/35 bg-ok/5 text-fg"
                  : "border-line2 bg-panel2/50 text-mut"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-1">
                  <span className="font-mono text-[10px] font-bold">0{s.id}</span>
                  {isDone ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-ok">
                      <Check size={11} weight="bold" />
                      <span>Đã xong</span>
                    </span>
                  ) : isFailed ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-err">
                      <Warning size={11} weight="fill" />
                      <span>Bị lỗi</span>
                    </span>
                  ) : isRunning ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-acc">
                      <Spinner size={11} className="text-acc" />
                      <span>Đang chạy</span>
                    </span>
                  ) : (
                    <span className="text-[9.5px] text-mut">Chờ xử lý</span>
                  )}
                </div>
                <div className="font-semibold mt-1 truncate">{s.label}</div>
                <div className="text-[9.5px] text-mut truncate mt-0.5">{s.desc}</div>
              </div>

              {canResumeHere && (
                <button
                  type="button"
                  onClick={() => onResume(s.id, false)}
                  className={`mt-2 w-full h-6 rounded text-[10px] font-bold flex items-center justify-center gap-1 transition-colors cursor-pointer ${
                    isFailed
                      ? "bg-err text-white hover:bg-err/90"
                      : s.status === "pending"
                      ? "bg-acc text-accink hover:bg-acc2"
                      : "border border-line2 bg-panel2/80 text-dim hover:text-fg hover:border-acc/50"
                  }`}
                  title={
                    isDone
                      ? `Chạy lại từ Bước ${s.id} (${s.label})`
                      : `Tiếp tục chạy từ Bước ${s.id} (${s.label}) — giữ nguyên kết quả các bước trước`
                  }
                >
                  {isDone ? (
                    <>
                      <ArrowCounterClockwise size={10} weight="bold" />
                      <span>{`Chạy lại Bước ${s.id}`}</span>
                    </>
                  ) : (
                    <>
                      <Play size={10} weight="fill" />
                      <span>{`Chạy tiếp Bước ${s.id}`}</span>
                    </>
                  )}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Live events log box when running/queued */}
      {inspectedJob &&
        (inspectedJob.state === "running" || inspectedJob.state === "queued") &&
        inspectedJob.events &&
        inspectedJob.events.length > 0 && (
          <div className="mt-1 flex flex-col gap-1">
            <div className="flex items-center justify-between text-[10.5px] text-mut">
              <span>Nhật ký thời gian thực ({inspectedJob.events.length} sự kiện)</span>
              <span className="font-mono">{inspectedJob.id}</span>
            </div>
            <div
              ref={logScrollRef}
              className="slim-scroll max-h-32 overflow-y-auto rounded-ctl bg-ink/80 border border-line p-2 font-mono text-[10.5px] leading-relaxed flex flex-col gap-1"
            >
              {inspectedJob.events.map((ev, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-mut shrink-0">
                    {new Date(ev.ts_ms).toTimeString().slice(0, 8)}
                  </span>
                  <span
                    className={`shrink-0 font-bold ${
                      ev.kind === "error"
                        ? "text-err"
                        : ev.kind === "step"
                        ? "text-acc"
                        : ev.kind === "done"
                        ? "text-ok"
                        : "text-dim"
                    }`}
                  >
                    [{ev.kind}]
                  </span>
                  <span className="text-fg/90">{ev.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
    </div>
  );
}

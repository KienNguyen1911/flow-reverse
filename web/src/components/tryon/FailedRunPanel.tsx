import { CheckCircle, Copy, DownloadSimple, MagicWand, Play, Warning } from "@phosphor-icons/react";
import type { Job, TryOnRunManifest } from "../../types";
import type { ReuseSource, StepView } from "./types";

interface Props {
  inspectedJob: Job | null;
  linkedRunManifest: TryOnRunManifest | null;
  activeSteps: { id: number }[];
  failedStepInfo: StepView | null;
  onResume: (stepId: number, sanitize?: boolean) => void;
  onReuse: (run: ReuseSource) => void;
}

/** Diagnostic + recovery panel for failed runs: error, resume actions, partial artifacts and event log. */
export function FailedRunPanel({ inspectedJob, linkedRunManifest, activeSteps, failedStepInfo, onResume, onReuse }: Props) {
  return (
    <div className="flex flex-col gap-3 pt-1">
      <div className="rounded-ctl border border-err/30 bg-err/5 p-3.5 flex flex-col gap-2.5">
        <div className="flex items-start gap-2.5">
          <Warning size={18} weight="fill" className="text-err shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-[13px] font-bold text-err">
                {failedStepInfo
                  ? `Pipeline dừng tại Bước ${failedStepInfo.id}/${activeSteps.length}: ${failedStepInfo.label}`
                  : "Quá trình tạo Video gặp lỗi trên Google Flow"}
              </h4>
              {linkedRunManifest?.run_id && (
                <span className="px-2 py-0.5 rounded bg-panel2 border border-line text-[10.5px] font-mono text-dim">
                  {linkedRunManifest.run_id}
                </span>
              )}
            </div>
            <p className="text-[11.5px] font-mono text-fg/90 mt-1 break-words">
              {inspectedJob?.error ||
                linkedRunManifest?.error ||
                "Không nhận được phản hồi video từ Google Flow."}
            </p>
          </div>
        </div>

        <div className="rounded bg-panel2/80 border border-line p-2.5 text-[11px] text-dim leading-relaxed flex flex-col gap-1">
          <span className="font-semibold text-fg">
            💡 Chế độ Resume thông minh (Không chạy lại từ đầu):
          </span>
          <span>
            • Các bước đã hoàn thành (đánh dấu <strong className="text-ok">✓ Đã xong</strong> trên thanh tiến trình phía trên) đã được lưu an toàn trong thư mục run.
          </span>
          <span>
            • Khi bấm <strong>Tiếp tục chạy từ Bước {failedStepInfo?.id || 1}</strong>, hệ thống sẽ{" "}
            <strong className="text-acc">bỏ qua các bước trước đó</strong> (ví dụ: giữ nguyên Video 1 &amp; Last Frame đã tạo thành công) và chỉ chạy tiếp từ bước bị gián đoạn.
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            onClick={() => onResume(failedStepInfo?.id || 1, false)}
            className="inline-flex items-center gap-1.5 px-3.5 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer shadow-xs"
          >
            <Play size={14} weight="fill" />
            <span>
              {failedStepInfo
                ? `Tiếp tục chạy từ Bước ${failedStepInfo.id}: ${failedStepInfo.label}`
                : "Tiếp tục chạy Pipeline"}
            </span>
          </button>

          <button
            onClick={() => onResume(failedStepInfo?.id || 1, true)}
            className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-acc/40 bg-acc/10 text-acc text-[11.5px] font-semibold hover:bg-acc/20 transition-colors cursor-pointer"
            title="Làm sạch các từ khóa nhạy cảm trong Prompt rồi chạy tiếp từ bước bị lỗi"
          >
            <MagicWand size={14} weight="bold" />
            <span>{`Làm sạch Prompt & Chạy tiếp Bước ${failedStepInfo?.id || 1}`}</span>
          </button>

          <button
            onClick={() => onReuse((linkedRunManifest || inspectedJob)!)}
            className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-semibold text-dim hover:text-fg transition-colors cursor-pointer"
          >
            <Copy size={13} />
            <span>Nạp lại vào cột Setup</span>
          </button>
        </div>
      </div>

      {/* Partial Artifacts Preview (e.g., Video 1 & Last Frame already completed before Step 3 failed) */}
      {linkedRunManifest &&
        (linkedRunManifest.video_1_url ||
          linkedRunManifest.last_frame_url ||
          linkedRunManifest.first_frame_url) && (
          <div className="rounded-ctl border border-line2 bg-panel2/60 p-3 flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                <CheckCircle size={14} weight="fill" className="text-ok" />
                <span>Kết quả các bước đã hoàn thành trước khi dừng ({linkedRunManifest.run_id})</span>
              </span>
              <span className="text-[10.5px] text-mut">Đã lưu sẵn — không cần tạo lại</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {linkedRunManifest.first_frame_url && (
                <div className="p-2 rounded bg-panel border border-line flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-dim">
                    <span>First Frame</span>
                    <a
                      href={linkedRunManifest.first_frame_url}
                      download="first_frame.png"
                      className="text-mut hover:text-fg"
                    >
                      <DownloadSimple size={12} />
                    </a>
                  </div>
                  <div className="rounded overflow-hidden bg-black flex items-center justify-center">
                    <img
                      src={linkedRunManifest.first_frame_url}
                      alt="First frame"
                      className="max-h-[260px] w-auto max-w-full object-contain"
                    />
                  </div>
                </div>
              )}
              {linkedRunManifest.video_1_url && (
                <div className="p-2 rounded bg-panel border border-ok/30 flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-ok">
                    <span>✓ Video 1 (0-8s) đã xong</span>
                    <a
                      href={linkedRunManifest.video_1_url}
                      download="video_1.mp4"
                      className="text-mut hover:text-fg"
                    >
                      <DownloadSimple size={12} />
                    </a>
                  </div>
                  <div className="rounded overflow-hidden bg-black flex items-center justify-center">
                    <video
                      controls
                      src={linkedRunManifest.video_1_url}
                      className="max-h-[260px] w-auto max-w-full object-contain"
                      playsInline
                    />
                  </div>
                </div>
              )}
              {linkedRunManifest.last_frame_url && (
                <div className="p-2 rounded bg-panel border border-ok/30 flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-ok">
                    <span>✓ Last Frame Video 1</span>
                    <a
                      href={linkedRunManifest.last_frame_url}
                      download="last_frame_video_1.png"
                      className="text-mut hover:text-fg"
                    >
                      <DownloadSimple size={12} />
                    </a>
                  </div>
                  <div className="rounded overflow-hidden bg-black flex items-center justify-center">
                    <img
                      src={linkedRunManifest.last_frame_url}
                      alt="Last frame"
                      className="max-h-[260px] w-auto max-w-full object-contain"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

      {/* Event Logs of the Failed Job */}
      {inspectedJob?.events && inspectedJob.events.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-[10.5px] text-mut">
            <span>Nhật ký chi tiết của Job ({inspectedJob.events.length} sự kiện)</span>
            <span className="font-mono">{inspectedJob.id}</span>
          </div>
          <div className="slim-scroll max-h-48 overflow-y-auto rounded-ctl bg-ink/80 border border-line p-2.5 font-mono text-[10.5px] leading-relaxed flex flex-col gap-1">
            {inspectedJob.events
              .filter((ev) => ev.kind !== "debug")
              .map((ev, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-mut shrink-0">
                    {new Date(ev.ts_ms).toTimeString().slice(0, 8)}
                  </span>
                  <span
                    className={`shrink-0 font-bold ${
                      ev.kind === "error"
                        ? "text-err"
                        : ev.kind === "warn"
                        ? "text-warn"
                        : ev.kind === "step"
                        ? "text-acc"
                        : "text-dim"
                    }`}
                  >
                    [{ev.kind}]
                  </span>
                  <span className="text-fg/90 break-words">{ev.message}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

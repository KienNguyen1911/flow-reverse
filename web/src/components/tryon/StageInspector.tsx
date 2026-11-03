import { CheckCircle, Copy, DownloadSimple, FilmStrip, Play, VideoCamera, Warning } from "@phosphor-icons/react";
import type { RefObject } from "react";
import type { Job, TryOnRunManifest } from "../../types";
import { FailedRunPanel } from "./FailedRunPanel";
import { ResultViewer } from "./ResultViewer";
import { StepProgress } from "./StepProgress";
import type { ResultTab, ReuseSource } from "./types";
import type { TryOnPipeline } from "./useTryOnPipeline";
import { formatDuration, formatRelativeTime } from "./format";
import { Chip, Panel, Spinner } from "../ui";

interface Props {
  inspectedJob: Job | null;
  selectedResultRun: TryOnRunManifest | null;
  pipeline: TryOnPipeline;
  resultTab: ResultTab;
  onResultTabChange: (tab: ResultTab) => void;
  copiedKey: string | null;
  onCopyPrompt: (text: string, key: string) => void;
  logScrollRef: RefObject<HTMLDivElement | null>;
  onResume: (stepId: number, sanitize?: boolean) => void;
  onReuse: (run: ReuseSource) => void;
}

/** Right pane of the studio: inspected job/run header, stepper and the result / failure / idle body. */
export function StageInspector({
  inspectedJob,
  selectedResultRun,
  pipeline,
  resultTab,
  onResultTabChange,
  copiedKey,
  onCopyPrompt,
  logScrollRef,
  onResume,
  onReuse,
}: Props) {
  const { activeSteps, linkedRunManifest, currentStep, stepStatuses, failedStepInfo, activeResult } = pipeline;

  return (
    <Panel className="p-3.5 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={`size-8 rounded-full grid place-items-center shrink-0 ${
              activeResult
                ? "bg-ok/15 text-ok"
                : inspectedJob?.state === "running"
                ? "bg-acc/15 text-acc animate-pulse"
                : inspectedJob?.state === "failed" || inspectedJob?.state === "rejected"
                ? "bg-err/15 text-err"
                : inspectedJob?.state === "queued"
                ? "bg-mut/15 text-dim"
                : "bg-line2 text-mut"
            }`}
          >
            {activeResult ? (
              <CheckCircle size={18} weight="fill" />
            ) : inspectedJob?.state === "running" ? (
              <Spinner size={16} />
            ) : inspectedJob?.state === "failed" || inspectedJob?.state === "rejected" ? (
              <Warning size={18} weight="fill" />
            ) : (
              <FilmStrip size={16} />
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-[13.5px] font-bold text-fg truncate">
                {activeResult
                  ? `Kết quả Video: ${activeResult.run_id}`
                  : inspectedJob
                  ? `Job: ${inspectedJob.id}`
                  : "Studio Sẵn Sàng"}
              </h3>
              {activeResult && selectedResultRun && (
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-line2 text-mut font-medium">
                  Từ lịch sử
                </span>
              )}
              {inspectedJob?.state === "running" && (
                <Chip tone="acc" live>
                  {`Đang render bước ${currentStep}/${activeSteps.length}`}
                </Chip>
              )}
              {inspectedJob?.state === "queued" && (
                <Chip tone="neutral">Trong hàng đợi</Chip>
              )}
              {(inspectedJob?.state === "failed" ||
                inspectedJob?.state === "rejected" ||
                (selectedResultRun && selectedResultRun.status !== "succeeded")) && (
                <Chip tone="err">
                  {failedStepInfo
                    ? `Lỗi tại Bước ${failedStepInfo.id}/${activeSteps.length}: ${failedStepInfo.label}`
                    : "Thất bại trên Flow"}
                </Chip>
              )}
            </div>
            <p className="text-[11px] font-mono text-mut truncate mt-0.5">
              {activeResult ? (
                <>
                  Thời gian render: {formatDuration(activeResult.elapsed_s)}
                  {activeResult.dry_run && " · [Dry-run]"}
                  {activeResult.account_id && ` · Tài khoản: ${activeResult.account_id}`}
                </>
              ) : inspectedJob ? (
                <>
                  Khởi tạo: {formatRelativeTime(inspectedJob.created_ms)}
                  {inspectedJob.started_ms &&
                    ` · Thời lượng: ${formatDuration(
                      ((inspectedJob.finished_ms || Date.now()) - inspectedJob.started_ms) / 1000
                    )}`}
                  {linkedRunManifest?.run_id && ` · Run: ${linkedRunManifest.run_id}`}
                </>
              ) : selectedResultRun ? (
                <>
                  Run: {selectedResultRun.run_id} · Thời lượng: {formatDuration(selectedResultRun.elapsed_s)}
                </>
              ) : (
                "Hãy setup ở cột trái và bấm Tạo Video Thật hoặc chọn từ danh sách Jobs / Lịch sử bên dưới."
              )}
            </p>
          </div>
        </div>

        {/* Actions for currently inspected item */}
        <div className="flex items-center gap-2">
          {failedStepInfo && inspectedJob?.state !== "running" && (
            <button
              onClick={() => onResume(failedStepInfo.id, false)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer shadow-xs"
              title={`Chạy tiếp pipeline từ Bước ${failedStepInfo.id} (${failedStepInfo.label}) mà không chạy lại các bước trước`}
            >
              <Play size={13} weight="fill" />
              <span>{`Chạy tiếp Bước ${failedStepInfo.id}`}</span>
            </button>
          )}

          {(activeResult || inspectedJob || selectedResultRun) && (
            <button
              onClick={() => onReuse((activeResult || selectedResultRun || inspectedJob)!)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-semibold text-dim hover:text-fg hover:border-acc/50 transition-colors cursor-pointer"
              title="Sao chép toàn bộ prompt và ảnh mẫu sang cột Setup để chạy tiếp"
            >
              <Copy size={13} />
              <span>Tái sử dụng Prompt</span>
            </button>
          )}

          {activeResult?.final_video_url && (
            <a
              href={activeResult.final_video_url}
              download={`${activeResult.run_id}_${activeResult.single_video || !activeResult.video_2_url ? "8s" : "16s"}.mp4`}
              className="inline-flex items-center gap-1.5 rounded-ctl bg-acc text-accink px-3 h-8 text-[12px] font-bold hover:bg-acc2 transition-colors cursor-pointer"
            >
              <DownloadSimple size={14} weight="bold" />
              <span>
                {activeResult.single_video || !activeResult.video_2_url
                  ? "Tải Video 8s"
                  : "Tải Video 16s"}
              </span>
            </a>
          )}
        </div>
      </div>

      {/* Stepper (Shown for running, queued, failed/rejected, and completed jobs/runs) */}
      {(inspectedJob || selectedResultRun) && (
        <StepProgress
          inspectedJob={inspectedJob}
          activeSteps={activeSteps}
          stepStatuses={stepStatuses}
          logScrollRef={logScrollRef}
          onResume={onResume}
        />
      )}

      {/* Video Result Viewer with Sub-tabs */}
      {activeResult ? (
        <ResultViewer
          activeResult={activeResult}
          resultTab={resultTab}
          onResultTabChange={onResultTabChange}
          copiedKey={copiedKey}
          onCopyPrompt={onCopyPrompt}
        />
      ) : (inspectedJob && (inspectedJob.state === "failed" || inspectedJob.state === "rejected")) ||
        (selectedResultRun && selectedResultRun.status !== "succeeded") ? (
        /* Failed Job Diagnostic & Recovery Panel */
        <FailedRunPanel
          inspectedJob={inspectedJob}
          linkedRunManifest={linkedRunManifest}
          activeSteps={activeSteps}
          failedStepInfo={failedStepInfo}
          onResume={onResume}
          onReuse={onReuse}
        />
      ) : !inspectedJob || inspectedJob.state === "succeeded" ? (
        /* Idle Welcome Screen */
        <div className="p-8 text-center text-mut flex flex-col items-center justify-center min-h-[260px]">
          <VideoCamera size={36} className="opacity-25 mb-2.5" />
          <h4 className="text-[13.5px] font-semibold text-dim">
            Chưa chọn video kết quả nào
          </h4>
          <p className="text-[11.5px] text-mut max-w-[380px] mt-1 leading-relaxed">
            Bạn có thể chọn một run từ tab <strong>Thư viện Lịch sử</strong> hoặc mở <strong>Jobs</strong> bên phải để xem lại video 16s, hoặc bấm <strong>Tạo Video Thật</strong> ở cột trái để bắt đầu lượt chạy mới.
          </p>
        </div>
      ) : null}
    </Panel>
  );
}

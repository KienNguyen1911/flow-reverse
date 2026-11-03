import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useJob, useJobs, useTryOnRuns } from "../hooks";
import type { Job, PoolInfo, Project, TryOnRunManifest } from "../types";
import { ConfirmModal } from "./tryon/ConfirmModal";
import { HistoryGallery, useHistoryFilter } from "./tryon/HistoryGallery";
import { JobsDrawer } from "./tryon/JobsDrawer";
import { sanitizePromptClient } from "./tryon/format";
import { extractReuseSettings, isAspectRatio } from "./tryon/runSettings";
import { SetupStudio } from "./tryon/SetupStudio";
import { StageInspector } from "./tryon/StageInspector";
import { ToastBanner, useToast } from "./tryon/toast";
import type { DockTab, ResultTab, ReuseSource, ViewMode } from "./tryon/types";
import { useTryOnForm } from "./tryon/useTryOnForm";
import { useTryOnPipeline } from "./tryon/useTryOnPipeline";
import { WorkspaceToolbar } from "./tryon/WorkspaceToolbar";

interface Props {
  mode?: "single" | "chain";
  projects: Project[];
  selectedProjectId: string | null;
  busy: boolean;
  pool: PoolInfo | null;
  activeJob: Job | null;
  activeJobId?: string | null;
  onSelectActiveJobId?: (id: string) => void;
  onStartJob: (promise: Promise<{ job_id: string }>) => void;
}

export function TryOnPanel({
  mode = "chain",
  projects,
  selectedProjectId,
  busy,
  activeJob,
  activeJobId,
  onSelectActiveJobId,
  onStartJob,
}: Props) {
  const isSingleMode = mode === "single";
  // Global jobs polling
  const { jobs: allJobs, refresh: refreshJobs } = useJobs(2500);
  const { runs: historyRuns, loading: historyLoading, refresh: refreshRuns } = useTryOnRuns();

  // Filter jobs specific to auto_tryon
  const tryonJobs = useMemo(
    () => allJobs.filter((j) => j.kind === "auto_tryon"),
    [allJobs]
  );

  const queuedJobs = useMemo(
    () => tryonJobs.filter((j) => j.state === "queued"),
    [tryonJobs]
  );
  const runningJobs = useMemo(
    () => tryonJobs.filter((j) => j.state === "running"),
    [tryonJobs]
  );
  const doneJobs = useMemo(
    () => tryonJobs.filter((j) => j.state === "succeeded" || j.state === "failed" || j.state === "rejected"),
    [tryonJobs]
  );

  // Selected job for deep inspection (defaults to active running job, or latest job)
  const [inspectedJobId, setInspectedJobId] = useState<string | null>(() => activeJobId || null);

  // Sync with prop activeJobId when changed outside
  useEffect(() => {
    if (activeJobId && activeJobId !== inspectedJobId) {
      setInspectedJobId(activeJobId);
    }
  }, [activeJobId]);

  // Hook to track the inspected job with full events log
  const terminalCallback = useMemo(
    () => (j: Job) => {
      refreshJobs();
      refreshRuns();
    },
    [refreshJobs, refreshRuns]
  );

  const inspectedJob = useJob(inspectedJobId, terminalCallback);

  // UI View Layout State
  const [viewMode, setViewMode] = useState<ViewMode>("studio");
  const [isStudioCollapsed, setIsStudioCollapsed] = useState(false);
  const [dockTab, setDockTab] = useState<DockTab>("all");
  const [jobsDrawerOpen, setJobsDrawerOpen] = useState(false);
  const [resultTab, setResultTab] = useState<ResultTab>("final");
  const history = useHistoryFilter(historyRuns);

  // Active result inspected (can be from a completed job or selected history run)
  const [selectedResultRun, setSelectedResultRun] = useState<TryOnRunManifest | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const { toast, showToast, dismissToast } = useToast();

  const form = useTryOnForm({ selectedProjectId, showToast });
  const {
    firstFrame,
    setFirstFrame,
    videoPrompt1,
    setVideoPrompt1,
    videoPrompt2,
    setVideoPrompt2,
    targetProjectId,
    autoStitch,
    removeWatermark,
    aspectRatio,
    setAspectRatio,
  } = form;

  const logScrollRef = useRef<HTMLDivElement>(null);

  // When inspected job finishes with a result, auto-link it
  useEffect(() => {
    if (inspectedJob?.state === "succeeded" && inspectedJob.result) {
      const res = inspectedJob.result as unknown as TryOnRunManifest;
      if (res.run_id) {
        setSelectedResultRun(res);
      }
    }
  }, [inspectedJob?.state, inspectedJob?.result]);

  // Auto-scroll logs
  useEffect(() => {
    const el = logScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [inspectedJob?.events?.length]);

  const pipeline = useTryOnPipeline({ inspectedJob, selectedResultRun, historyRuns, isSingleMode });
  const { activeSteps, linkedRunManifest } = pipeline;

  // Resume pipeline from a specific step (skipping already-completed steps)
  const handleResumeFromStep = async (stepId: number, sanitize = false) => {
    const params = (inspectedJob?.params || {}) as Record<string, unknown>;
    const runId = linkedRunManifest?.run_id || undefined;
    const rawFfPath =
      linkedRunManifest?.first_frame_path ||
      (typeof params.first_frame_path === "string" ? params.first_frame_path : "") ||
      firstFrame?.path ||
      "";

    if (!rawFfPath && !runId) {
      showToast("Không tìm thấy ảnh First Frame của lượt chạy này để tiếp tục.", "err");
      return;
    }

    const rawP1 =
      linkedRunManifest?.video_prompt_1 ||
      (typeof params.video_prompt_1 === "string" ? params.video_prompt_1 : "") ||
      videoPrompt1;
    const rawP2 =
      linkedRunManifest?.video_prompt_2 ||
      (typeof params.video_prompt_2 === "string" ? params.video_prompt_2 : "") ||
      videoPrompt2;

    const p1 = sanitize ? sanitizePromptClient(rawP1) : rawP1;
    const p2 = sanitize ? sanitizePromptClient(rawP2) : rawP2;
    const ar =
      (linkedRunManifest?.aspect_ratio as "9:16" | "16:9") ||
      (typeof params.aspect_ratio === "string" ? (params.aspect_ratio as "9:16" | "16:9") : aspectRatio) ||
      "9:16";
    const projId =
      (typeof params.project_id === "string" ? params.project_id : "") ||
      targetProjectId.trim() ||
      undefined;
    const singleRun = Boolean(
      linkedRunManifest?.single_video ??
        (typeof params.single_video === "boolean" ? params.single_video : isSingleMode)
    );

    if (p1) setVideoPrompt1(p1);
    if (p2) setVideoPrompt2(p2);

    const payload = {
      first_frame_path: rawFfPath || undefined,
      project_id: projId,
      dry_run: false,
      confirm: true,
      auto_stitch: singleRun ? false : autoStitch,
      remove_watermark: removeWatermark,
      aspect_ratio: ar,
      video_prompt_1: p1.trim() || undefined,
      video_prompt_2: singleRun ? undefined : p2.trim() || undefined,
      single_video: singleRun,
      resume_run_id: runId,
      start_from_step: stepId,
      // Also encode resume token in image_prompt so live servers without restart still parse it in hot-reloaded pipeline
      image_prompt: runId ? `__resume__:${runId}:${stepId}` : undefined,
    };

    try {
      const promise = api.tryonStart(payload);
      onStartJob(promise);
      const res = await promise;
      setInspectedJobId(res.job_id);
      onSelectActiveJobId?.(res.job_id);
      setSelectedResultRun(null);
      refreshJobs();
      setDockTab("running");
      const stepLabel = activeSteps.find((s) => s.id === stepId)?.label || `Bước ${stepId}`;
      showToast(
        `Đã chạy tiếp Pipeline từ Bước ${stepId} (${stepLabel}) — giữ nguyên các bước trước đã xong!`,
        "ok"
      );
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Lỗi khi chạy tiếp pipeline", "err");
    }
  };

  // Execution triggers
  const executeWorkflow = async (dryRun: boolean) => {
    if (!firstFrame) {
      showToast("Vui lòng tải lên ảnh First Frame trước khi tạo video.", "err");
      return;
    }

    const singleRun = isSingleMode || !videoPrompt2.trim();
    const payload = {
      first_frame_path: firstFrame.path,
      project_id: targetProjectId.trim() || undefined,
      dry_run: dryRun,
      confirm: !dryRun,
      auto_stitch: singleRun ? false : autoStitch,
      remove_watermark: removeWatermark,
      aspect_ratio: aspectRatio,
      video_prompt_1: videoPrompt1.trim() || undefined,
      video_prompt_2: singleRun ? undefined : videoPrompt2.trim() || undefined,
      single_video: singleRun,
    };

    try {
      const promise = api.tryonStart(payload);
      onStartJob(promise);
      const res = await promise;
      setInspectedJobId(res.job_id);
      onSelectActiveJobId?.(res.job_id);
      setSelectedResultRun(null);
      refreshJobs();
      showToast(
        dryRun ? "Đã gửi job kiểm tra (dry-run) vào hàng đợi!" : "Đã thêm job tạo video thật vào hàng đợi!",
        "ok"
      );
      // Auto-switch dock to running or queued
      setDockTab("running");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Lỗi khi khởi chạy job", "err");
    }
  };

  const handleCopyPrompt = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    showToast("Đã sao chép prompt vào bộ nhớ tạm", "info");
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Reuse prompt & setup from a previous run or job
  const handleReuseSettings = (run: ReuseSource) => {
    const { prompt1: p1, prompt2: p2, firstFramePath: ffPath, firstFrameUrl: ffUrl, aspectRatio: ar, runId } =
      extractReuseSettings(run);

    if (p1) setVideoPrompt1(p1);
    if (p2) setVideoPrompt2(p2);
    if (isAspectRatio(ar)) setAspectRatio(ar);

    if (ffPath) {
      setFirstFrame({
        path: ffPath,
        filename: ffPath.split(/[\\/]/).pop() || "first_frame.png",
        url: ffUrl || `/api/tryon/files/${runId}/${ffPath.split(/[\\/]/).pop()}`,
      });
    }

    setViewMode("studio");
    setIsStudioCollapsed(false);
    showToast("Đã nạp kịch bản & cấu hình vào Studio!", "ok");
  };

  const handleSelectJob = (job: Job) => {
    setInspectedJobId(job.id);
    onSelectActiveJobId?.(job.id);
    setViewMode("studio");
    if (job.result && (job.result as unknown as TryOnRunManifest).run_id) {
      setSelectedResultRun(job.result as unknown as TryOnRunManifest);
    } else {
      setSelectedResultRun(null);
    }
  };

  return (
    <div className="flex flex-col gap-3 min-h-[calc(100vh-140px)]">
      <ToastBanner toast={toast} onDismiss={dismissToast} />

      <WorkspaceToolbar
        viewMode={viewMode}
        setViewMode={setViewMode}
        historyCount={historyRuns.length}
        runningCount={runningJobs.length}
        queuedCount={queuedJobs.length}
        doneCount={doneJobs.length}
        totalJobCount={tryonJobs.length}
        setDockTab={setDockTab}
        isStudioCollapsed={isStudioCollapsed}
        onToggleCollapsed={() => setIsStudioCollapsed(!isStudioCollapsed)}
        jobsDrawerOpen={jobsDrawerOpen}
        setJobsDrawerOpen={setJobsDrawerOpen}
        onRefresh={() => {
          refreshJobs();
          refreshRuns();
          showToast("Đã đồng bộ trạng thái mới nhất", "info");
        }}
      />

      {viewMode === "studio" ? (
        <div className="flex flex-col gap-3 flex-1 min-w-0">
          {/* Studio Split: Left Setup + Right Stage Inspector */}
          <div className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)] items-start">
            <SetupStudio
              form={form}
              projects={projects}
              isSingleMode={isSingleMode}
              isCollapsed={isStudioCollapsed}
              onExpand={() => setIsStudioCollapsed(false)}
              onOpenConfirm={() => setConfirmModalOpen(true)}
              showToast={showToast}
            />

            <div className="flex flex-col gap-3 min-w-0">
              <StageInspector
                inspectedJob={inspectedJob}
                selectedResultRun={selectedResultRun}
                pipeline={pipeline}
                resultTab={resultTab}
                onResultTabChange={setResultTab}
                copiedKey={copiedKey}
                onCopyPrompt={handleCopyPrompt}
                logScrollRef={logScrollRef}
                onResume={handleResumeFromStep}
                onReuse={handleReuseSettings}
              />
            </div>
          </div>
        </div>
      ) : (
        <HistoryGallery
          runs={historyRuns}
          filter={history}
          onRefresh={() => refreshRuns()}
          onViewRun={(run) => {
            setSelectedResultRun(run);
            setViewMode("studio");
            setResultTab("final");
          }}
          onReuse={handleReuseSettings}
        />
      )}

      <JobsDrawer
        open={jobsDrawerOpen}
        onClose={() => setJobsDrawerOpen(false)}
        dockTab={dockTab}
        onDockTabChange={setDockTab}
        tryonJobs={tryonJobs}
        runningJobs={runningJobs}
        queuedJobs={queuedJobs}
        doneJobs={doneJobs}
        inspectedJobId={inspectedJobId}
        onSelectJob={handleSelectJob}
        onReuse={handleReuseSettings}
      />

      {confirmModalOpen && (
        <ConfirmModal
          isSingleRun={isSingleMode || !videoPrompt2.trim()}
          onCancel={() => setConfirmModalOpen(false)}
          onConfirm={() => {
            setConfirmModalOpen(false);
            executeWorkflow(false);
          }}
        />
      )}
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowClockwise,
  ArrowCounterClockwise,
  ArrowsIn,
  ArrowsOut,
  CaretDown,
  CaretRight,
  CaretUp,
  Check,
  CheckCircle,
  Clock,
  Copy,
  DownloadSimple,
  Eye,
  FilmStrip,
  Hourglass,
  Image as ImageIcon,
  MagicWand,
  MagnifyingGlass,
  Play,
  Plus,
  Queue,
  SidebarSimple,
  Sparkle,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import { useJob, useJobs, useTryOnRuns } from "../hooks";
import type { Job, PoolInfo, Project, TryOnRunManifest } from "../types";
import { Btn, Chip, Field, IconBtn, Panel, Spinner } from "./ui";

const SAMPLE_FIRST_FRAME_PATH = "assets/sample_first_frame.png";

const STEPS_CHAIN = [
  { id: 1, label: "Tạo Video 1 (8s)", desc: "Upload First Frame & render Video 1" },
  { id: 2, label: "Trích xuất Last Frame", desc: "FFmpeg cắt frame chính xác 100%" },
  { id: 3, label: "Tạo Video 2 (8s)", desc: "Upload Last Frame & render Video 2" },
  { id: 4, label: "Ghép hoàn chỉnh 16s", desc: "Nối liền mạch 2 video không giật" },
];

const STEPS_SINGLE = [
  { id: 1, label: "Tạo Video (8s)", desc: "Upload First Frame & render Video 8s" },
  { id: 2, label: "Hậu kỳ & Xóa Watermark", desc: "Làm sạch watermark & xuất MP4" },
];

const PRESETS_V1 = [
  {
    label: "👗 Xoay dáng tự nhiên",
    prompt:
      "A photorealistic young woman wearing the outfit, turns gently to showcase the dress, elegant natural movement, soft studio lighting, high details, 8 seconds",
  },
  {
    label: "🚶‍♀️ Bước đi nhìn camera",
    prompt:
      "A young woman walking slowly forward towards the camera, smiling naturally, fabric flowing softly, cinematic depth of field, 8 seconds",
  },
];

const PRESETS_V2 = [
  {
    label: "✨ Xoay 180° khoe lưng",
    prompt:
      "Continuing seamlessly from the last frame, the young woman turns 180 degrees to showcase the back details of the garment, then looks over her shoulder with a graceful smile, smooth motion, 8 seconds",
  },
  {
    label: "📸 Cận cảnh tà áo & nụ cười",
    prompt:
      "Continuing smoothly from the last frame, the young woman steps closer to camera, adjusting the outfit sleeve, confident lifestyle fashion pose, 8 seconds",
  },
];

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return "0s";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

function formatRelativeTime(ms?: number | null): string {
  if (!ms) return "";
  const diffSec = Math.floor((Date.now() - ms) / 1000);
  if (diffSec < 60) return `${diffSec}s trước`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m trước`;
  return `${Math.floor(diffSec / 3600)}h trước`;
}

function sanitizePromptClient(raw: string): string {
  if (!raw) return "";
  let s = raw
    .replace(/\b(of\s+)?(the\s+)?exact\s+(young\s+)?(korean\s+|asian\s+)?(woman|girl|model|lady)(\s+from\s+the\s+reference\s+(image|photo))?\b/gi, "of the fashion model")
    .replace(/\b(young\s+)?(korean|asian|japanese|chinese)\s+(woman|girl|model|lady)\b/gi, "fashion model")
    .replace(/\bfrom\s+the\s+reference\s+(image|photo)(\s+pose)?\b/gi, "in the scene")
    .replace(/\b(strictly\s+)?lock(ed)?\s+facial\s+(identity|features|structure)(\s+and\s+hairstyle)?\b/gi, "natural expression")
    .replace(/\b(strictly\s+)?maintain(ing)?\s+(exact\s+)?facial\s+(identity|features)\b/gi, "natural expression")
    .replace(/\b(celebrity|idol|actress|k-pop|famous\s+person)\b/gi, "model")
    .replace(/Camera\s*&\s*Realism:[\s\S]*$/i, "Smooth natural movement, realistic fabric drape, soft lighting, 24fps, 8 seconds.")
    .replace(/-\s*0s\s*to\s*2s\s*\([^)]*\):\s*/gi, "")
    .replace(/-\s*2s\s*to\s*6s\s*\([^)]*\):\s*/gi, " ")
    .replace(/-\s*6s\s*to\s*8s\s*\([^)]*\):\s*/gi, " ");
  return s.replace(/\s{2,}/g, " ").trim();
}

interface UploadedFile {
  path: string;
  filename: string;
  url: string;
  size?: number;
}

interface ToastInfo {
  id: number;
  message: string;
  type: "ok" | "info" | "err";
}

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

  // Setup form states
  const [firstFrame, setFirstFrame] = useState<UploadedFile | null>(null);
  const [firstFrameUploading, setFirstFrameUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const [videoPrompt1, setVideoPrompt1] = useState(
    "A photorealistic young woman wearing the outfit, turns gently to showcase the dress, elegant natural movement, soft studio lighting, high details, 8 seconds"
  );
  const [videoPrompt2, setVideoPrompt2] = useState(
    "Continuing seamlessly from the last frame, the young woman turns 180 degrees to showcase the back details of the garment, then looks over her shoulder with a graceful smile, smooth motion, 8 seconds"
  );

  const [targetProjectId, setTargetProjectId] = useState<string>(selectedProjectId || "");
  const [autoStitch, setAutoStitch] = useState(true);
  const [removeWatermark, setRemoveWatermark] = useState<boolean>(
    () => (localStorage.getItem("fb_tryon_rm_wm") ?? "1") !== "0"
  );
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9">("9:16");

  // UI View Layout State
  const [viewMode, setViewMode] = useState<"studio" | "history">("studio");
  const [isStudioCollapsed, setIsStudioCollapsed] = useState(false);
  const [dockTab, setDockTab] = useState<"all" | "running" | "queued" | "done">("all");
  const [jobsDrawerOpen, setJobsDrawerOpen] = useState(false);
  const [resultTab, setResultTab] = useState<"final" | "subvideos" | "frames" | "prompts">("final");
  const [historySearch, setHistorySearch] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState<"all" | "succeeded" | "failed">("all");

  // Active result inspected (can be from a completed job or selected history run)
  const [selectedResultRun, setSelectedResultRun] = useState<TryOnRunManifest | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [toast, setToast] = useState<ToastInfo | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const logScrollRef = useRef<HTMLDivElement>(null);

  const showToast = (message: string, type: "ok" | "info" | "err" = "ok") => {
    const id = Date.now();
    setToast({ id, message, type });
    setTimeout(() => {
      setToast((cur) => (cur?.id === id ? null : cur));
    }, 3200);
  };

  // Keep target project in sync with TopBar
  useEffect(() => {
    if (selectedProjectId && !targetProjectId) {
      setTargetProjectId(selectedProjectId);
    }
  }, [selectedProjectId, targetProjectId]);

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

  const isJobSingle = useMemo(() => {
    if (!inspectedJob) return isSingleMode;
    const p = inspectedJob.params as Record<string, unknown> | undefined;
    if (p && typeof p.single_video === "boolean") return p.single_video;
    return isSingleMode;
  }, [inspectedJob, isSingleMode]);

  const activeSteps = isJobSingle ? STEPS_SINGLE : STEPS_CHAIN;

  // Resolve any run manifest associated with selectedResultRun or inspectedJob (even if failed)
  const linkedRunManifest: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun) return selectedResultRun;
    if (!inspectedJob) return null;

    const jobRes = inspectedJob.result as unknown as TryOnRunManifest | undefined;
    let detectedRunId = jobRes?.run_id || "";

    if (!detectedRunId && inspectedJob.events) {
      for (const ev of inspectedJob.events) {
        const m = ev.message.match(/\b(tryon_\d{8}_\d{6})\b/);
        if (m) {
          detectedRunId = m[1];
          break;
        }
      }
    }

    const fromHistory = detectedRunId
      ? historyRuns.find((r) => r.run_id === detectedRunId) || null
      : null;

    if (fromHistory && jobRes?.run_id) {
      return { ...fromHistory, ...jobRes, steps: jobRes.steps?.length ? jobRes.steps : fromHistory.steps };
    }
    if (fromHistory) return fromHistory;
    if (jobRes?.run_id) return jobRes;
    return null;
  }, [selectedResultRun, inspectedJob, historyRuns]);

  // Determine step reached from job event logs
  const reachedStepFromEvents = useMemo(() => {
    if (!inspectedJob) return 0;
    const events = inspectedJob.events || [];
    let step = 1;
    for (const ev of events) {
      const msg = ev.message.toLowerCase();
      if (isJobSingle) {
        if (msg.includes("xóa watermark") || msg.includes("hoàn tất")) {
          step = Math.max(step, 2);
        }
      } else {
        if (msg.includes("nối") || msg.includes("ghép") || msg.includes("bước 4/4") || msg.includes("bước 8")) {
          step = Math.max(step, 4);
        } else if (msg.includes("video 2") || msg.includes("bước 3/4") || msg.includes("bước 7")) {
          step = Math.max(step, 3);
        } else if (msg.includes("last frame") || msg.includes("trích xuất") || msg.includes("bước 2/4") || msg.includes("bước 6")) {
          step = Math.max(step, 2);
        } else if (msg.includes("video 1") || msg.includes("bước 1/4") || msg.includes("bước 5")) {
          step = Math.max(step, 1);
        }
      }
    }
    return step;
  }, [inspectedJob, isJobSingle]);

  // Determine current pipeline step
  const currentStep = useMemo(() => {
    if (linkedRunManifest?.status === "succeeded" || inspectedJob?.state === "succeeded") {
      return isJobSingle ? 2 : 4;
    }
    if (linkedRunManifest?.failed_step) {
      return linkedRunManifest.failed_step;
    }
    if (linkedRunManifest?.current_step) {
      return linkedRunManifest.current_step;
    }
    if (!inspectedJob) return 0;
    return reachedStepFromEvents || 1;
  }, [inspectedJob, linkedRunManifest, isJobSingle, reachedStepFromEvents]);

  // Compute detailed status for each step in activeSteps
  const stepStatuses = useMemo(() => {
    const isFailed =
      (selectedResultRun && selectedResultRun.status !== "succeeded") ||
      (!selectedResultRun && (inspectedJob?.state === "failed" || inspectedJob?.state === "rejected"));
    const isSucceeded =
      selectedResultRun?.status === "succeeded" ||
      (!selectedResultRun && inspectedJob?.state === "succeeded");
    const isRunning = !selectedResultRun && inspectedJob?.state === "running";

    const failStepId =
      linkedRunManifest?.failed_step ||
      (isFailed ? Math.max(1, reachedStepFromEvents || 1) : null);

    return activeSteps.map((s) => {
      const manifestStep = linkedRunManifest?.steps?.find((ms) => ms.id === s.id);
      if (manifestStep && (isFailed || isSucceeded || selectedResultRun)) {
        return {
          ...s,
          status: manifestStep.status as "pending" | "running" | "succeeded" | "failed",
          error: manifestStep.error || null,
        };
      }
      if (isSucceeded) {
        return { ...s, status: "succeeded" as const, error: null };
      }
      if (isRunning) {
        if (s.id < currentStep) return { ...s, status: "succeeded" as const, error: null };
        if (s.id === currentStep) return { ...s, status: "running" as const, error: null };
        return { ...s, status: "pending" as const, error: null };
      }
      if (isFailed && failStepId !== null) {
        if (s.id < failStepId) return { ...s, status: "succeeded" as const, error: null };
        if (s.id === failStepId) {
          return {
            ...s,
            status: "failed" as const,
            error: inspectedJob?.error || linkedRunManifest?.error || null,
          };
        }
        return { ...s, status: "pending" as const, error: null };
      }
      return { ...s, status: "pending" as const, error: null };
    });
  }, [activeSteps, linkedRunManifest, selectedResultRun, inspectedJob, currentStep, reachedStepFromEvents]);

  const failedStepInfo = useMemo(() => {
    return stepStatuses.find((s) => s.status === "failed") || null;
  }, [stepStatuses]);

  // Active result to display in full completed viewer (only when succeeded, or when user explicitly inspects a completed run)
  const activeResult: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun && selectedResultRun.status === "succeeded") return selectedResultRun;
    if (
      !selectedResultRun &&
      inspectedJob?.state === "succeeded" &&
      linkedRunManifest?.run_id
    ) {
      return linkedRunManifest;
    }
    return null;
  }, [selectedResultRun, inspectedJob?.state, linkedRunManifest]);

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

  // Upload handler
  const handleUploadFile = async (file: File) => {
    setFirstFrameUploading(true);
    try {
      const res = await api.upload(file);
      setFirstFrame({
        path: res.path,
        filename: res.filename,
        url: res.url,
        size: res.size,
      });
      showToast("Tải ảnh First Frame thành công!", "ok");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Tải ảnh thất bại", "err");
    } finally {
      setFirstFrameUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleUseSampleFirstFrame = () => {
    setFirstFrame({
      path: SAMPLE_FIRST_FRAME_PATH,
      filename: "sample_first_frame.png",
      url: `/api/assets/sample_first_frame.png`,
      size: 684203,
    });
    showToast("Đã nạp ảnh mẫu First Frame", "info");
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
  const handleReuseSettings = (run: TryOnRunManifest | Job) => {
    const p1 = "video_prompt_1" in run ? run.video_prompt_1 : (run.params as Record<string, string>)?.video_prompt_1;
    const p2 = "video_prompt_2" in run ? run.video_prompt_2 : (run.params as Record<string, string>)?.video_prompt_2;
    const ffPath = "first_frame_path" in run ? run.first_frame_path : (run.params as Record<string, string>)?.first_frame_path;
    const ffUrl = "first_frame_url" in run ? run.first_frame_url : undefined;
    const ar = (("aspect_ratio" in run ? run.aspect_ratio : (run.params as Record<string, string>)?.aspect_ratio) || "9:16") as "9:16" | "16:9";

    if (p1) setVideoPrompt1(p1);
    if (p2) setVideoPrompt2(p2);
    if (ar === "9:16" || ar === "16:9") setAspectRatio(ar);

    if (ffPath) {
      setFirstFrame({
        path: ffPath,
        filename: ffPath.split(/[\\/]/).pop() || "first_frame.png",
        url: ffUrl || `/api/tryon/files/${"run_id" in run ? run.run_id : ""}/${ffPath.split(/[\\/]/).pop()}`,
      });
    }

    setViewMode("studio");
    setIsStudioCollapsed(false);
    showToast("Đã nạp kịch bản & cấu hình vào Studio!", "ok");
  };

  // Filtered history runs
  const filteredRuns = useMemo(() => {
    return historyRuns.filter((r) => {
      const matchSearch =
        !historySearch ||
        r.run_id.toLowerCase().includes(historySearch.toLowerCase()) ||
        (r.video_prompt_1 && r.video_prompt_1.toLowerCase().includes(historySearch.toLowerCase())) ||
        (r.product_title && r.product_title.toLowerCase().includes(historySearch.toLowerCase()));
      const matchStatus =
        historyStatusFilter === "all" ||
        (historyStatusFilter === "succeeded" && r.status === "succeeded") ||
        (historyStatusFilter === "failed" && r.status !== "succeeded");
      return matchSearch && matchStatus;
    });
  }, [historyRuns, historySearch, historyStatusFilter]);

  const drawerJobs =
    dockTab === "running" ? runningJobs : dockTab === "queued" ? queuedJobs : dockTab === "done" ? doneJobs : tryonJobs;

  return (
    <div className="flex flex-col gap-3 min-h-[calc(100vh-140px)]">
      {/* ================= FLOATING TOAST ================= */}
      {toast && (
        <div className="fixed top-5 right-5 z-50 flex items-center gap-2.5 rounded-ctl border border-line2 bg-panel px-4 py-3 shadow-2xl backdrop-blur-md animate-fade-in text-[12.5px]">
          <span
            className={`size-2 rounded-full ${
              toast.type === "ok" ? "bg-ok" : toast.type === "err" ? "bg-err" : "bg-acc"
            }`}
          />
          <span className="font-medium text-fg">{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-2 text-mut hover:text-fg cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* ================= WORKSPACE TOPBAR & QUICK METRICS ================= */}
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
            <span>Thư viện Lịch sử ({historyRuns.length})</span>
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
              runningJobs.length > 0
                ? "border-acc/40 bg-acc/10 text-acc"
                : "border-line2 bg-panel2/50 text-mut hover:text-fg"
            }`}
            title="Số job đang chạy render video"
          >
            <span
              className={`size-2 rounded-full bg-acc ${
                runningJobs.length > 0 ? "animate-pulse" : ""
              }`}
            />
            <span className="font-sans font-medium">Đang chạy:</span>
            <span className="font-bold">{runningJobs.length}</span>
          </button>

          <button
            onClick={() => {
              setViewMode("studio");
              setDockTab("queued");
              setJobsDrawerOpen(true);
            }}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-all cursor-pointer ${
              queuedJobs.length > 0
                ? "border-line2 bg-panel2 text-dim hover:text-fg"
                : "border-line bg-panel2/30 text-mut"
            }`}
            title="Số job trong hàng đợi"
          >
            <Hourglass size={13} className="text-mut" />
            <span className="font-sans font-medium">Hàng đợi:</span>
            <span className="font-bold">{queuedJobs.length}</span>
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
            <span className="font-bold">{doneJobs.length}</span>
          </button>
        </div>

        {/* Right: Studio layout controls */}
        <div className="flex items-center gap-2">
          {viewMode === "studio" && (
            <button
              onClick={() => setIsStudioCollapsed(!isStudioCollapsed)}
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
            <span>{`Jobs (${tryonJobs.length})`}</span>
          </button>

          <button
            onClick={() => {
              refreshJobs();
              refreshRuns();
              showToast("Đã đồng bộ trạng thái mới nhất", "info");
            }}
            className="inline-grid place-items-center size-8 rounded-ctl border border-line2 bg-panel2 text-dim hover:text-fg transition-colors cursor-pointer"
            title="Làm mới trạng thái jobs & lịch sử"
          >
            <ArrowClockwise size={15} />
          </button>
        </div>
      </div>

      {/* ================= MAIN WORKSPACE BODY ================= */}
      {viewMode === "studio" ? (
        <div className="flex flex-col gap-3 flex-1 min-w-0">
          {/* Studio Split: Left Setup + Right Stage Inspector */}
          <div className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)] items-start">
            {/* ----------------- LEFT PANE: SETUP STUDIO (COLLAPSIBLE) ----------------- */}
            {!isStudioCollapsed ? (
              <div className="w-full lg:w-[390px] xl:w-[410px] flex flex-col gap-3 shrink-0">
                {/* Section 1: Upload First Frame */}
                <Panel
                  className={`p-3.5 flex flex-col gap-3 transition-colors ${
                    isDragging ? "border-acc bg-acc/5" : ""
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    const file = e.dataTransfer.files?.[0];
                    if (file) handleUploadFile(file);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="grid place-items-center size-5 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                        1
                      </span>
                      <h3 className="text-[13px] font-bold text-fg">
                        Ảnh First Frame (Khởi đầu)
                      </h3>
                    </div>
                    <span className="text-[10px] font-medium text-warn bg-warn/10 px-2 py-0.5 rounded-full border border-warn/30">
                      Bắt buộc
                    </span>
                  </div>

                  {firstFrame ? (
                    <div className="relative group rounded-ctl overflow-hidden border border-line2 bg-panel2 p-2.5 flex items-center gap-3">
                      <div className="size-16 rounded-ctl overflow-hidden bg-line border border-line2 shrink-0 flex items-center justify-center">
                        <img
                          src={firstFrame.url}
                          alt="First frame"
                          className="size-full object-cover"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 text-ok text-[11.5px] font-medium">
                          <CheckCircle size={13} weight="fill" />
                          <span>Đã chọn ảnh mẫu</span>
                        </div>
                        <p className="text-[12px] font-semibold text-fg truncate mt-0.5">
                          {firstFrame.filename}
                        </p>
                        <p className="text-[10.5px] font-mono text-mut">
                          {formatBytes(firstFrame.size)}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <button
                            onClick={() => fileInputRef.current?.click()}
                            className="text-[11px] text-acc hover:underline cursor-pointer"
                          >
                            Đổi ảnh
                          </button>
                          <span className="text-line2">|</span>
                          <button
                            onClick={() => setFirstFrame(null)}
                            className="text-[11px] text-err hover:underline cursor-pointer"
                          >
                            Xóa
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className={`border border-dashed rounded-ctl p-4 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
                        isDragging
                          ? "border-acc bg-acc/10 scale-[1.01]"
                          : "border-line2 hover:border-acc/60 bg-panel2/50 hover:bg-panel2"
                      }`}
                    >
                      <div className="size-8 rounded-full bg-acc/10 text-acc grid place-items-center mb-1.5">
                        <UploadSimple size={16} />
                      </div>
                      <p className="text-[12px] font-semibold text-fg">
                        {isDragging ? "Thả ảnh vào đây..." : "Tải lên ảnh First Frame"}
                      </p>
                      <p className="text-[10.5px] text-mut mt-0.5">
                        PNG, JPG, WEBP (mẫu mặc trang phục)
                      </p>
                      {firstFrameUploading && (
                        <div className="flex items-center gap-1.5 mt-2 text-acc text-[11px]">
                          <Spinner size={12} />
                          <span>Đang tải ảnh lên...</span>
                        </div>
                      )}
                    </div>
                  )}

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleUploadFile(f);
                    }}
                  />

                  {/* Sample test button */}
                  <div className="flex items-center justify-between text-[11px] pt-1 border-t border-line">
                    <button
                      type="button"
                      onClick={handleUseSampleFirstFrame}
                      className="inline-flex items-center gap-1.5 text-acc hover:underline cursor-pointer font-medium"
                    >
                      <MagicWand size={12} />
                      <span>Dùng ảnh mẫu test nhanh</span>
                    </button>
                    <span className="text-mut text-[10.5px]">Google Flow 8s</span>
                  </div>
                </Panel>

                {/* Section 2: Motion Prompts */}
                <Panel className="p-3.5 flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="grid place-items-center size-5 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                        2
                      </span>
                      <h3 className="text-[13px] font-bold text-fg">
                        Kịch bản Chuyển động
                      </h3>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setVideoPrompt1((p) => sanitizePromptClient(p));
                          setVideoPrompt2((p) => sanitizePromptClient(p));
                          showToast("Đã lọc bỏ từ nhạy cảm (tránh lỗi người nổi tiếng trên Flow)", "ok");
                        }}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-acc/30 bg-acc/10 text-acc hover:bg-acc/20 text-[10px] font-semibold transition-colors cursor-pointer"
                        title="Loại bỏ các cụm từ dễ bị Google Flow chặn vì hiểu nhầm là người nổi tiếng (như 'exact young Korean woman', 'Strictly lock facial identity'...)"
                      >
                        <MagicWand size={11} />
                        <span>Lọc từ nhạy cảm</span>
                      </button>
                      <Chip tone="acc" className="h-6 text-[10.5px]">
                        {`${isSingleMode || !videoPrompt2.trim() ? "1×8s" : "2×8s"} · ${aspectRatio}`}
                      </Chip>
                    </div>
                  </div>

                  {/* Video 1 Prompt */}
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-[11.5px]">
                      <label className="font-semibold text-fg flex items-center gap-1.5">
                        <VideoCamera size={13} className="text-acc" />
                        <span>{isSingleMode ? "Prompt Chuyển động Video (0 - 8s)" : "Prompt Video 1 (0 - 8s)"}</span>
                      </label>
                      <span className="font-mono text-mut text-[10px]">
                        {videoPrompt1.length} ký tự
                      </span>
                    </div>
                    <textarea
                      rows={isSingleMode ? 5 : 3}
                      value={videoPrompt1}
                      onChange={(e) => setVideoPrompt1(e.target.value)}
                      placeholder="A photorealistic young woman wearing the outfit..."
                      className="w-full rounded-ctl border border-line2 bg-panel2 p-2 text-[11px] font-mono text-fg focus:border-acc outline-none resize-y leading-relaxed"
                    />
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {PRESETS_V1.map((p, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setVideoPrompt1(p.prompt)}
                          className="text-[10px] rounded bg-panel px-1.5 py-0.5 border border-line hover:border-acc/60 text-mut hover:text-fg transition-colors cursor-pointer"
                        >
                          {p.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Video 2 Prompt (Only in chain mode) */}
                  {!isSingleMode && (
                    <div className="flex flex-col gap-1 pt-2 border-t border-line">
                      <div className="flex items-center justify-between text-[11.5px]">
                        <label className="font-semibold text-fg flex items-center gap-1.5">
                          <VideoCamera size={13} className="text-ok" />
                          <span>Prompt Video 2 (8 - 16s)</span>
                        </label>
                        <span className="font-mono text-mut text-[10px]">
                          {videoPrompt2.length} ký tự
                        </span>
                      </div>
                      <textarea
                        rows={3}
                        value={videoPrompt2}
                        onChange={(e) => setVideoPrompt2(e.target.value)}
                        placeholder="Continuing seamlessly from the last frame... (Để trống nếu chỉ muốn tạo 1 video 8s)"
                        className="w-full rounded-ctl border border-line2 bg-panel2 p-2 text-[11px] font-mono text-fg focus:border-acc outline-none resize-y leading-relaxed"
                      />
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {PRESETS_V2.map((p, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => setVideoPrompt2(p.prompt)}
                            className="text-[10px] rounded bg-panel px-1.5 py-0.5 border border-line hover:border-acc/60 text-mut hover:text-fg transition-colors cursor-pointer"
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </Panel>

                {/* Section 3: Project & Settings */}
                <Panel className="p-3.5 flex flex-col gap-2.5">
                  <div className="flex items-center gap-2">
                    <span className="grid place-items-center size-5 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                      3
                    </span>
                    <h3 className="text-[13px] font-bold text-fg">
                      {isSingleMode ? "Cấu hình Tỷ lệ & Xuất bản" : "Cấu hình Tỷ lệ & Nối Video"}
                    </h3>
                  </div>

                  <Field label="Dự án Google Flow">
                    <select
                      value={targetProjectId}
                      onChange={(e) => setTargetProjectId(e.target.value)}
                      className="w-full rounded-ctl border border-line2 bg-panel2 px-2.5 py-1 text-[11.5px] text-fg focus:border-acc outline-none"
                    >
                      <option value="">Tự động chọn tab Flow đang mở</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title || p.id} ({p.id.slice(0, 8)}...)
                        </option>
                      ))}
                    </select>
                  </Field>

                  <div className="grid grid-cols-2 gap-1.5 mt-1">
                    <button
                      type="button"
                      onClick={() => setAspectRatio("9:16")}
                      className={`h-8 rounded-ctl border text-[11px] font-semibold flex items-center justify-center gap-1 transition-all cursor-pointer ${
                        aspectRatio === "9:16"
                          ? "border-acc bg-acc/15 text-acc shadow-xs"
                          : "border-line2 bg-panel2 text-mut hover:text-fg"
                      }`}
                    >
                      <span>📱 9:16 (Dọc Reels/TikTok)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setAspectRatio("16:9")}
                      className={`h-8 rounded-ctl border text-[11px] font-semibold flex items-center justify-center gap-1 transition-all cursor-pointer ${
                        aspectRatio === "16:9"
                          ? "border-acc bg-acc/15 text-acc shadow-xs"
                          : "border-line2 bg-panel2 text-mut hover:text-fg"
                      }`}
                    >
                      <span>🖥️ 16:9 (Ngang Cinema)</span>
                    </button>
                  </div>

                  {!isSingleMode && (
                    <div className="flex items-center gap-2 pt-1 border-t border-line text-[11.5px]">
                      <input
                        type="checkbox"
                        id="autoStitch"
                        checked={autoStitch}
                        onChange={(e) => setAutoStitch(e.target.checked)}
                        className="rounded accent-acc cursor-pointer"
                      />
                      <label htmlFor="autoStitch" className="font-medium text-dim cursor-pointer">
                        Tự động ghép 2 video 8s thành 16s (FFmpeg)
                      </label>
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-1 border-t border-line text-[11.5px]">
                    <input
                      type="checkbox"
                      id="tryonRemoveWatermark"
                      checked={removeWatermark}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setRemoveWatermark(checked);
                        localStorage.setItem("fb_tryon_rm_wm", checked ? "1" : "0");
                      }}
                      className="rounded accent-acc cursor-pointer"
                    />
                    <label
                      htmlFor="tryonRemoveWatermark"
                      className="font-medium text-dim cursor-pointer"
                      title="Tự động xóa ngôi sao 4 cánh (✦) trên First Frame và Video"
                    >
                      Tự động xóa watermark (✦) Ảnh & Video
                    </label>
                  </div>
                </Panel>

                {/* Section 4: Action & Enqueue Buttons */}
                <div className="flex flex-col gap-2">
                  <Btn
                    variant="primary"
                    icon={<Sparkle size={16} weight="fill" />}
                    onClick={() => setConfirmModalOpen(true)}
                    className="h-10 font-bold w-full justify-between px-4 text-[13px]"
                    title="Bắt đầu chạy tạo video thật qua tài khoản Flow"
                  >
                    <span>{isSingleMode ? "Tạo Video 8s Thật" : "Tạo Video Thử Đồ Thật"}</span>
                    <span className="text-[10px] bg-accink/20 px-1.5 py-0.5 rounded text-accink font-bold">
                      {isSingleMode || !videoPrompt2.trim() ? "~1 cr" : "~2 cr"}
                    </span>
                  </Btn>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setFirstFrame(null);
                        setVideoPrompt1(PRESETS_V1[0].prompt);
                        setVideoPrompt2(PRESETS_V2[0].prompt);
                        showToast("Đã đặt lại form tạo mới", "info");
                      }}
                      className="flex-1 h-8 rounded-ctl border border-line2 bg-panel text-[11.5px] text-mut hover:text-fg transition-colors cursor-pointer"
                      title="Làm trống form để setup job khác"
                    >
                      Reset Form
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* Collapsed Studio Mini Rail */
              <div className="hidden lg:flex flex-col items-center gap-3 p-2 rounded-panel border border-line bg-panel w-12 shrink-0">
                <button
                  onClick={() => setIsStudioCollapsed(false)}
                  className="size-8 rounded-ctl bg-acc/10 text-acc grid place-items-center hover:bg-acc/20 cursor-pointer"
                  title="Mở rộng bảng Setup Studio"
                >
                  <SidebarSimple size={16} />
                </button>
                <div className="w-full border-t border-line2 my-1" />
                <button
                  onClick={() => {
                    setIsStudioCollapsed(false);
                    fileInputRef.current?.click();
                  }}
                  className="size-8 rounded-ctl border border-line2 text-dim hover:text-fg grid place-items-center cursor-pointer"
                  title="Tải ảnh First Frame"
                >
                  <UploadSimple size={15} />
                </button>
                <button
                  onClick={() => setConfirmModalOpen(true)}
                  className="size-8 rounded-ctl bg-acc text-accink font-bold grid place-items-center hover:bg-acc2 cursor-pointer"
                  title="Tạo video thật"
                >
                  <Sparkle size={15} weight="fill" />
                </button>
              </div>
            )}

            {/* ----------------- RIGHT PANE: STAGE & MEDIA INSPECTOR ----------------- */}
            <div className="flex flex-col gap-3 min-w-0">
              {/* Inspected Job / Run Header Card */}
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
                        onClick={() => handleResumeFromStep(failedStepInfo.id, false)}
                        className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer shadow-xs"
                        title={`Chạy tiếp pipeline từ Bước ${failedStepInfo.id} (${failedStepInfo.label}) mà không chạy lại các bước trước`}
                      >
                        <Play size={13} weight="fill" />
                        <span>{`Chạy tiếp Bước ${failedStepInfo.id}`}</span>
                      </button>
                    )}

                    {(activeResult || inspectedJob || selectedResultRun) && (
                      <button
                        onClick={() => handleReuseSettings((activeResult || selectedResultRun || inspectedJob)!)}
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
                                onClick={() => handleResumeFromStep(s.id, false)}
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
                )}

                {/* Video Result Viewer with Sub-tabs */}
                {activeResult ? (
                  <div className="flex flex-col gap-3 pt-1">
                    {/* Sub-tabs */}
                    <div className="flex items-center gap-1.5 border-b border-line2 pb-2">
                      <button
                        onClick={() => setResultTab("final")}
                        className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                          resultTab === "final"
                            ? "bg-panel2 text-acc border border-line2"
                            : "text-mut hover:text-fg"
                        }`}
                      >
                        {activeResult.single_video || !activeResult.video_2_url
                          ? "Video 8s Hoàn Chỉnh"
                          : "Video 16s Hoàn Chỉnh"}
                      </button>
                      {!activeResult.single_video && activeResult.video_2_url && (
                        <button
                          onClick={() => setResultTab("subvideos")}
                          className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                            resultTab === "subvideos"
                              ? "bg-panel2 text-acc border border-line2"
                              : "text-mut hover:text-fg"
                          }`}
                        >
                          Video 1 & 2 (8s + 8s)
                        </button>
                      )}
                      <button
                        onClick={() => setResultTab("frames")}
                        className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                          resultTab === "frames"
                            ? "bg-panel2 text-acc border border-line2"
                            : "text-mut hover:text-fg"
                        }`}
                      >
                        {activeResult.single_video || !activeResult.last_frame_url
                          ? "Ảnh First Frame"
                          : "Khung hình First & Last Frame"}
                      </button>
                      <button
                        onClick={() => setResultTab("prompts")}
                        className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                          resultTab === "prompts"
                            ? "bg-panel2 text-acc border border-line2"
                            : "text-mut hover:text-fg"
                        }`}
                      >
                        Kịch Bản Prompts
                      </button>
                    </div>

                    {/* TAB 1: FINAL 16S VIDEO */}
                    {resultTab === "final" && (
                      <div className="flex flex-col items-center justify-center">
                        {activeResult.final_video_url ? (
                          <div className="rounded-panel overflow-hidden bg-black/90 border border-line flex items-center justify-center w-full max-h-[480px]">
                            <video
                              controls
                              src={activeResult.final_video_url}
                              className="max-h-[480px] w-auto max-w-full object-contain"
                              autoPlay
                              muted
                              loop
                              playsInline
                            />
                          </div>
                        ) : (
                          <div className="p-8 text-center text-mut rounded-ctl bg-panel2 w-full">
                            <VideoCamera size={32} className="mx-auto mb-2 opacity-40" />
                            <p className="text-[12.5px] font-medium text-dim">
                              Chưa có file video 16s đã nối hoàn chỉnh.
                            </p>
                            <p className="text-[11px] text-mut mt-1">
                              Kiểm tra các video con 8s ở tab "Video 1 & 2".
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* TAB 2: SUB-VIDEOS */}
                    {resultTab === "subvideos" && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {/* Video 1 */}
                        <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
                          <div className="flex items-center justify-between">
                            <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                              <VideoCamera size={13} className="text-acc" />
                              <span>Video 1 (0-8s)</span>
                            </span>
                            {activeResult.video_1_url && (
                              <a
                                href={activeResult.video_1_url}
                                download="video_1.mp4"
                                className="text-mut hover:text-fg"
                                title="Tải Video 1"
                              >
                                <DownloadSimple size={13} />
                              </a>
                            )}
                          </div>
                          {activeResult.video_1_url ? (
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                              <video
                                controls
                                src={activeResult.video_1_url}
                                className="max-h-[62vh] w-auto max-w-full object-contain"
                                playsInline
                              />
                            </div>
                          ) : (
                            <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                              Chưa có Video 1
                            </div>
                          )}
                        </div>

                        {/* Video 2 */}
                        <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
                          <div className="flex items-center justify-between">
                            <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                              <VideoCamera size={13} className="text-ok" />
                              <span>Video 2 (8-16s)</span>
                            </span>
                            {activeResult.video_2_url && (
                              <a
                                href={activeResult.video_2_url}
                                download="video_2.mp4"
                                className="text-mut hover:text-fg"
                                title="Tải Video 2"
                              >
                                <DownloadSimple size={13} />
                              </a>
                            )}
                          </div>
                          {activeResult.video_2_url ? (
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                              <video
                                controls
                                src={activeResult.video_2_url}
                                className="max-h-[62vh] w-auto max-w-full object-contain"
                                playsInline
                              />
                            </div>
                          ) : (
                            <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                              Chưa có Video 2
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* TAB 3: KEYFRAMES COMPARISON */}
                    {resultTab === "frames" && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {/* First Frame */}
                        <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
                          <div className="flex items-center justify-between">
                            <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                              <ImageIcon size={13} className="text-acc" />
                              <span>First Frame (Khởi đầu Video 1)</span>
                            </span>
                            {activeResult.first_frame_url && (
                              <a
                                href={activeResult.first_frame_url}
                                download="first_frame.png"
                                className="text-mut hover:text-fg"
                                title="Tải First Frame"
                              >
                                <DownloadSimple size={13} />
                              </a>
                            )}
                          </div>
                          {activeResult.first_frame_url ? (
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                              <img
                                src={activeResult.first_frame_url}
                                alt="First Frame"
                                className="max-h-[62vh] w-auto max-w-full object-contain"
                              />
                            </div>
                          ) : (
                            <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                              Không có ảnh First Frame
                            </div>
                          )}
                        </div>

                        {/* Last Frame */}
                        <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
                          <div className="flex items-center justify-between">
                            <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                              <ImageIcon size={13} className="text-ok" />
                              <span>Last Frame Video 1 (FFmpeg cắt)</span>
                            </span>
                            {activeResult.last_frame_url && (
                              <a
                                href={activeResult.last_frame_url}
                                download="last_frame_video_1.png"
                                className="text-mut hover:text-fg"
                                title="Tải Last Frame"
                              >
                                <DownloadSimple size={13} />
                              </a>
                            )}
                          </div>
                          {activeResult.last_frame_url ? (
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                              <img
                                src={activeResult.last_frame_url}
                                alt="Last Frame"
                                className="max-h-[62vh] w-auto max-w-full object-contain"
                              />
                            </div>
                          ) : (
                            <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                              Không có ảnh Last Frame
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* TAB 4: PROMPTS */}
                    {resultTab === "prompts" && (
                      <div className="flex flex-col gap-2.5">
                        <div className="p-2.5 rounded-ctl bg-panel2 border border-line flex flex-col gap-1">
                          <div className="flex items-center justify-between text-[11.5px]">
                            <span className="font-bold text-fg flex items-center gap-1.5">
                              <VideoCamera size={13} className="text-acc" />
                              <span>Video Prompt 1 (0-8s)</span>
                            </span>
                            <button
                              onClick={() => handleCopyPrompt(activeResult.video_prompt_1 || "", "vp1")}
                              className="text-[10.5px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                            >
                              {copiedKey === "vp1" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                              <span>{copiedKey === "vp1" ? "Đã chép" : "Sao chép"}</span>
                            </button>
                          </div>
                          <p className="font-mono text-[11px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                            {activeResult.video_prompt_1 || "(Không có dữ liệu)"}
                          </p>
                        </div>

                        {!activeResult.single_video && activeResult.video_prompt_2 && (
                          <div className="p-2.5 rounded-ctl bg-panel2 border border-line flex flex-col gap-1">
                            <div className="flex items-center justify-between text-[11.5px]">
                              <span className="font-bold text-fg flex items-center gap-1.5">
                                <VideoCamera size={13} className="text-ok" />
                                <span>Video Prompt 2 (8-16s)</span>
                              </span>
                              <button
                                onClick={() => handleCopyPrompt(activeResult.video_prompt_2 || "", "vp2")}
                                className="text-[10.5px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                              >
                                {copiedKey === "vp2" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                                <span>{copiedKey === "vp2" ? "Đã chép" : "Sao chép"}</span>
                              </button>
                            </div>
                            <p className="font-mono text-[11px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                              {activeResult.video_prompt_2 || "(Không có dữ liệu)"}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (inspectedJob && (inspectedJob.state === "failed" || inspectedJob.state === "rejected")) ||
                  (selectedResultRun && selectedResultRun.status !== "succeeded") ? (
                  /* Failed Job Diagnostic & Recovery Panel */
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
                          onClick={() => handleResumeFromStep(failedStepInfo?.id || 1, false)}
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
                          onClick={() => handleResumeFromStep(failedStepInfo?.id || 1, true)}
                          className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-acc/40 bg-acc/10 text-acc text-[11.5px] font-semibold hover:bg-acc/20 transition-colors cursor-pointer"
                          title="Làm sạch các từ khóa nhạy cảm trong Prompt rồi chạy tiếp từ bước bị lỗi"
                        >
                          <MagicWand size={14} weight="bold" />
                          <span>{`Làm sạch Prompt & Chạy tiếp Bước ${failedStepInfo?.id || 1}`}</span>
                        </button>

                        <button
                          onClick={() => handleReuseSettings((linkedRunManifest || inspectedJob)!)}
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
            </div>
          </div>

        </div>
      ) : (
        /* ================= FULL HISTORY GALLERY VIEW ================= */
        <div className="flex flex-col gap-4 flex-1">
          <Panel className="p-4 flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
              <div>
                <h3 className="text-[15px] font-bold text-fg flex items-center gap-2">
                  <Clock size={18} className="text-acc" />
                  <span>Kho Lưu Trữ Lịch Sử Video Thử Đồ</span>
                </h3>
                <p className="text-[12px] text-mut mt-0.5">
                  Tất cả các bản dựng video 16s, khung hình First/Last Frame và kịch bản đã tạo.
                </p>
              </div>

              {/* Search & Filter Controls */}
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <MagnifyingGlass
                    size={14}
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mut"
                  />
                  <input
                    type="text"
                    value={historySearch}
                    onChange={(e) => setHistorySearch(e.target.value)}
                    placeholder="Tìm theo Run ID, prompt..."
                    className="h-8 pl-8 pr-3 rounded-ctl border border-line2 bg-panel2 text-[11.5px] text-fg focus:border-acc outline-none w-48 sm:w-60"
                  />
                  {historySearch && (
                    <button
                      onClick={() => setHistorySearch("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-mut hover:text-fg cursor-pointer"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-1 bg-panel2 p-0.5 rounded-ctl border border-line text-[11.5px]">
                  <button
                    onClick={() => setHistoryStatusFilter("all")}
                    className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                      historyStatusFilter === "all" ? "bg-panel text-fg font-semibold" : "text-mut hover:text-fg"
                    }`}
                  >
                    Tất cả ({historyRuns.length})
                  </button>
                  <button
                    onClick={() => setHistoryStatusFilter("succeeded")}
                    className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                      historyStatusFilter === "succeeded" ? "bg-ok/15 text-ok font-semibold" : "text-mut hover:text-fg"
                    }`}
                  >
                    Thành công
                  </button>
                  <button
                    onClick={() => setHistoryStatusFilter("failed")}
                    className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                      historyStatusFilter === "failed" ? "bg-err/15 text-err font-semibold" : "text-mut hover:text-fg"
                    }`}
                  >
                    Lỗi
                  </button>
                </div>

                <button
                  onClick={() => refreshRuns()}
                  className="size-8 rounded-ctl border border-line2 bg-panel2 text-dim hover:text-fg grid place-items-center cursor-pointer"
                  title="Làm mới lịch sử"
                >
                  <ArrowClockwise size={15} />
                </button>
              </div>
            </div>

            {/* Gallery Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredRuns.map((run) => (
                <div
                  key={run.run_id}
                  className="rounded-ctl border border-line2 bg-panel2/60 hover:bg-panel2 p-3 flex flex-col justify-between gap-3 transition-all hover:border-acc/40 group"
                >
                  <div className="flex flex-col gap-2">
                    {/* Media Thumbnail or Video */}
                    <div className="relative rounded-ctl overflow-hidden bg-black aspect-[3/4] max-h-[260px] border border-line flex items-center justify-center">
                      {run.final_video_url ? (
                        <video
                          src={run.final_video_url}
                          controls
                          className="size-full object-contain"
                          preload="metadata"
                        />
                      ) : run.first_frame_url ? (
                        <img
                          src={run.first_frame_url}
                          alt="First Frame"
                          className="size-full object-contain"
                        />
                      ) : (
                        <div className="text-mut text-[11px] grid place-items-center">
                          Không có media
                        </div>
                      )}

                      <span
                        className={`absolute top-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          run.status === "succeeded"
                            ? "bg-ok/90 text-black shadow-xs"
                            : "bg-err/90 text-white shadow-xs"
                        }`}
                      >
                        {run.status === "succeeded"
                          ? run.single_video || !run.video_2_url
                            ? "8s Hoàn chỉnh"
                            : "16s Hoàn chỉnh"
                          : "Lỗi"}
                      </span>
                    </div>

                    <div>
                      <div className="flex items-center justify-between text-[11px] text-mut font-mono">
                        <span className="font-bold text-fg truncate">{run.run_id}</span>
                        <span>{formatDuration(run.elapsed_s)}</span>
                      </div>
                      <p className="text-[11px] text-dim line-clamp-2 mt-1 leading-snug">
                        {run.video_prompt_1 || "(Không có prompt)"}
                      </p>
                    </div>
                  </div>

                  {/* Actions Toolbar */}
                  <div className="flex items-center justify-between gap-2 pt-2 border-t border-line text-[11.5px]">
                    <button
                      onClick={() => {
                        setSelectedResultRun(run);
                        setViewMode("studio");
                        setResultTab("final");
                      }}
                      className="inline-flex items-center gap-1.5 text-acc hover:underline font-semibold cursor-pointer"
                    >
                      <Eye size={14} />
                      <span>Xem chi tiết</span>
                    </button>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleReuseSettings(run)}
                        className="text-dim hover:text-fg text-[11px] cursor-pointer"
                        title="Tái sử dụng prompt và thiết lập"
                      >
                        Tái sử dụng
                      </button>
                      {run.final_video_url && (
                        <a
                          href={run.final_video_url}
                          download={`${run.run_id}_${run.single_video || !run.video_2_url ? "8s" : "16s"}.mp4`}
                          className="text-dim hover:text-fg p-1 rounded hover:bg-line"
                          title="Tải video"
                        >
                          <DownloadSimple size={14} />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {filteredRuns.length === 0 && (
                <div className="col-span-full py-16 text-center text-mut flex flex-col items-center justify-center">
                  <FilmStrip size={40} className="opacity-30 mb-2" />
                  <p className="text-[13px] font-medium text-dim">
                    Không tìm thấy bản ghi lịch sử nào phù hợp
                  </p>
                  <p className="text-[11.5px] text-mut mt-1">
                    Thử tìm kiếm với từ khóa khác hoặc chuyển sang tab Studio để tạo video mới.
                  </p>
                </div>
              )}
            </div>
          </Panel>
        </div>
      )}

      {/* ================= RIGHT JOBS DRAWER ================= */}
      <aside
        className={`fixed right-0 top-0 bottom-0 z-40 w-[360px] max-w-[92vw] bg-panel border-l border-line2 shadow-2xl flex flex-col transition-transform duration-200 ${
          jobsDrawerOpen ? "translate-x-0" : "translate-x-full invisible"
        }`}
        aria-hidden={!jobsDrawerOpen}
      >
        <div className="flex items-center justify-between px-3.5 py-3 border-b border-line">
          <span className="text-[13px] font-bold text-fg flex items-center gap-2">
            <Queue size={16} className="text-acc" />
            Jobs Video Thử Đồ
          </span>
          <button
            onClick={() => setJobsDrawerOpen(false)}
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
              onClick={() => setDockTab(key)}
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
                onClick={() => {
                  setInspectedJobId(job.id);
                  onSelectActiveJobId?.(job.id);
                  setViewMode("studio");
                  if (job.result && (job.result as unknown as TryOnRunManifest).run_id) {
                    setSelectedResultRun(job.result as unknown as TryOnRunManifest);
                  } else {
                    setSelectedResultRun(null);
                  }
                }}
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
                      handleReuseSettings(job);
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

      {/* ================= CONFIRMATION MODAL ================= */}
      {confirmModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="rounded-panel border border-line2 bg-panel w-full max-w-md p-5 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-warn/15 text-warn grid place-items-center shrink-0">
                <Warning size={22} weight="bold" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-fg">
                  {isSingleMode || !videoPrompt2.trim()
                    ? "Xác nhận tạo Video 8s Thật"
                    : "Xác nhận tạo Video Thử Đồ Thật"}
                </h3>
                <p className="text-[12px] text-mut mt-0.5">Sử dụng Google Flow credit</p>
              </div>
            </div>

            {isSingleMode || !videoPrompt2.trim() ? (
              <div className="rounded-ctl bg-panel2 border border-line p-3 text-[12px] leading-relaxed flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-mut">Video (8 giây, 1080p):</span>
                  <span className="font-mono text-fg">~1 Flow Credit</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-mut">Hậu kỳ & Xóa Watermark (Local):</span>
                  <span className="font-mono text-ok">0 Credit (Local)</span>
                </div>
                <div className="border-t border-line2 pt-1.5 flex items-center justify-between font-bold text-acc">
                  <span>Tổng chi phí ước tính:</span>
                  <span className="font-mono">~1 Credit</span>
                </div>
              </div>
            ) : (
              <div className="rounded-ctl bg-panel2 border border-line p-3 text-[12px] leading-relaxed flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-mut">Video 1 (8 giây):</span>
                  <span className="font-mono text-fg">~1 Flow Credit</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-mut">Trích xuất Last Frame (FFmpeg):</span>
                  <span className="font-mono text-ok">0 Credit (Local)</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-mut">Video 2 (8 giây):</span>
                  <span className="font-mono text-fg">~1 Flow Credit</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-mut">Ghép nối 16s (FFmpeg):</span>
                  <span className="font-mono text-ok">0 Credit (Local)</span>
                </div>
                <div className="border-t border-line2 pt-1.5 flex items-center justify-between font-bold text-acc">
                  <span>Tổng chi phí ước tính:</span>
                  <span className="font-mono">~2 Credits</span>
                </div>
              </div>
            )}

            <p className="text-[11.5px] text-dim leading-relaxed">
              Job sẽ được xếp vào hàng đợi và phân bổ cho tài khoản CloakBrowser khả dụng. Bạn có thể tiếp tục tạo thêm các job khác trong lúc render.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <Btn
                variant="ghost"
                onClick={() => setConfirmModalOpen(false)}
                className="h-9 px-4 text-[12.5px]"
              >
                Hủy bỏ
              </Btn>
              <Btn
                variant="primary"
                icon={<Sparkle size={15} weight="fill" />}
                onClick={() => {
                  setConfirmModalOpen(false);
                  executeWorkflow(false);
                }}
                className="h-9 px-4 text-[12.5px] font-bold"
              >
                Xác nhận tạo Video
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

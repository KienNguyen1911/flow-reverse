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

const STEPS = [
  { id: 1, label: "Tạo Video 1 (8s)", desc: "Upload First Frame & render Video 1" },
  { id: 2, label: "Trích xuất Last Frame", desc: "FFmpeg cắt frame chính xác 100%" },
  { id: 3, label: "Tạo Video 2 (8s)", desc: "Upload Last Frame & render Video 2" },
  { id: 4, label: "Ghép hoàn chỉnh 16s", desc: "Nối liền mạch 2 video không giật" },
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
  projects,
  selectedProjectId,
  busy,
  activeJob,
  activeJobId,
  onSelectActiveJobId,
  onStartJob,
}: Props) {
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
      if (j.state === "succeeded") {
        refreshRuns();
      }
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
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9">("9:16");

  // UI View Layout State
  const [viewMode, setViewMode] = useState<"studio" | "history">("studio");
  const [isStudioCollapsed, setIsStudioCollapsed] = useState(false);
  const [dockTab, setDockTab] = useState<"all" | "running" | "queued" | "done" | "history">("running");
  const [dockHeight, setDockHeight] = useState<"compact" | "normal" | "expanded">("normal");
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

  // Determine current pipeline step (1-4)
  const currentStep = useMemo(() => {
    if (!inspectedJob) return 0;
    if (inspectedJob.state === "succeeded") return 4;
    if (inspectedJob.state === "failed" || inspectedJob.state === "rejected") return 0;

    const events = inspectedJob.events || [];
    let step = 1;
    for (const ev of events) {
      const msg = ev.message.toLowerCase();
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
    return step;
  }, [inspectedJob]);

  // Active result to display
  const activeResult: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun) return selectedResultRun;
    if (inspectedJob?.result && (inspectedJob.result as unknown as TryOnRunManifest).run_id) {
      return inspectedJob.result as unknown as TryOnRunManifest;
    }
    return null;
  }, [selectedResultRun, inspectedJob?.result]);

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

    const payload = {
      first_frame_path: firstFrame.path,
      project_id: targetProjectId.trim() || undefined,
      dry_run: dryRun,
      confirm: !dryRun,
      auto_stitch: autoStitch,
      aspect_ratio: aspectRatio,
      video_prompt_1: videoPrompt1.trim() || undefined,
      video_prompt_2: videoPrompt2.trim() || undefined,
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
                      <Chip tone="acc" className="h-6 text-[10.5px]">{`2×8s · ${aspectRatio}`}</Chip>
                    </div>
                  </div>

                  {/* Video 1 Prompt */}
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-[11.5px]">
                      <label className="font-semibold text-fg flex items-center gap-1.5">
                        <VideoCamera size={13} className="text-acc" />
                        <span>Prompt Video 1 (0 - 8s)</span>
                      </label>
                      <span className="font-mono text-mut text-[10px]">
                        {videoPrompt1.length} ký tự
                      </span>
                    </div>
                    <textarea
                      rows={3}
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

                  {/* Video 2 Prompt */}
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
                      placeholder="Continuing seamlessly from the last frame..."
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
                </Panel>

                {/* Section 3: Project & Settings */}
                <Panel className="p-3.5 flex flex-col gap-2.5">
                  <div className="flex items-center gap-2">
                    <span className="grid place-items-center size-5 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                      3
                    </span>
                    <h3 className="text-[13px] font-bold text-fg">Cấu hình Tỷ lệ & Nối Video</h3>
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
                    <span>Tạo Video Thử Đồ Thật</span>
                    <span className="text-[10px] bg-accink/20 px-1.5 py-0.5 rounded text-accink font-bold">~2 cr</span>
                  </Btn>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => executeWorkflow(true)}
                      className="flex-1 h-8 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-medium text-dim hover:text-fg hover:border-mut/60 transition-colors cursor-pointer"
                      title="Chạy thử nghiệm không trừ credit"
                    >
                      Dry-Run Test
                    </button>
                    <button
                      onClick={() => {
                        setFirstFrame(null);
                        setVideoPrompt1(PRESETS_V1[0].prompt);
                        setVideoPrompt2(PRESETS_V2[0].prompt);
                        showToast("Đã đặt lại form tạo mới", "info");
                      }}
                      className="px-3 h-8 rounded-ctl border border-line2 bg-panel text-[11.5px] text-mut hover:text-fg transition-colors cursor-pointer"
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
                            {`Đang render bước ${currentStep}/4`}
                          </Chip>
                        )}
                        {inspectedJob?.state === "queued" && (
                          <Chip tone="neutral">Trong hàng đợi</Chip>
                        )}
                        {(inspectedJob?.state === "failed" || inspectedJob?.state === "rejected") && (
                          <Chip tone="err">Thất bại trên Flow</Chip>
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
                          </>
                        ) : (
                          "Hãy setup ở cột trái và bấm Tạo Video Thật hoặc chọn từ danh sách Jobs / Lịch sử bên dưới."
                        )}
                      </p>
                    </div>
                  </div>

                  {/* Actions for currently inspected item */}
                  <div className="flex items-center gap-2">
                    {(activeResult || inspectedJob) && (
                      <button
                        onClick={() => handleReuseSettings((activeResult || inspectedJob)!)}
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
                        download={`${activeResult.run_id}_16s.mp4`}
                        className="inline-flex items-center gap-1.5 rounded-ctl bg-acc text-accink px-3 h-8 text-[12px] font-bold hover:bg-acc2 transition-colors cursor-pointer"
                      >
                        <DownloadSimple size={14} weight="bold" />
                        <span>Tải Video 16s</span>
                      </a>
                    )}
                  </div>
                </div>

                {/* 4-Step Stepper (Shown when job is running or viewing a job) */}
                {inspectedJob && (inspectedJob.state === "running" || inspectedJob.state === "queued") && (
                  <div className="flex flex-col gap-2 pt-1">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {STEPS.map((s) => {
                        const isCurrent = inspectedJob.state === "running" && currentStep === s.id;
                        const isDone = inspectedJob.state === "running" && currentStep > s.id;

                        return (
                          <div
                            key={s.id}
                            className={`p-2.5 rounded-ctl border text-[11px] flex flex-col transition-all ${
                              isCurrent
                                ? "border-acc bg-acc/10 text-fg shadow-xs shadow-acc/10"
                                : isDone
                                ? "border-ok/30 bg-ok/5 text-fg"
                                : "border-line2 bg-panel2/50 text-mut"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[10px] font-bold">0{s.id}</span>
                              {isDone ? (
                                <Check size={12} className="text-ok" weight="bold" />
                              ) : isCurrent ? (
                                <Spinner size={12} className="text-acc" />
                              ) : (
                                <span className="size-1.5 rounded-full bg-mut/40" />
                              )}
                            </div>
                            <span className="font-semibold mt-1 truncate">{s.label}</span>
                            <span className="text-[9.5px] text-mut truncate mt-0.5">{s.desc}</span>
                          </div>
                        );
                      })}
                    </div>

                    {/* Live events log box */}
                    {inspectedJob.events && inspectedJob.events.length > 0 && (
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
                        Video 16s Hoàn Chỉnh
                      </button>
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
                      <button
                        onClick={() => setResultTab("frames")}
                        className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                          resultTab === "frames"
                            ? "bg-panel2 text-acc border border-line2"
                            : "text-mut hover:text-fg"
                        }`}
                      >
                        Khung hình First & Last Frame
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
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] max-h-[360px] flex items-center justify-center">
                              <video
                                controls
                                src={activeResult.video_1_url}
                                className="size-full object-cover"
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
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] max-h-[360px] flex items-center justify-center">
                              <video
                                controls
                                src={activeResult.video_2_url}
                                className="size-full object-cover"
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
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] max-h-[360px] flex items-center justify-center">
                              <img
                                src={activeResult.first_frame_url}
                                alt="First Frame"
                                className="size-full object-cover"
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
                            <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] max-h-[360px] flex items-center justify-center">
                              <img
                                src={activeResult.last_frame_url}
                                alt="Last Frame"
                                className="size-full object-cover"
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
                      </div>
                    )}
                  </div>
                ) : inspectedJob && (inspectedJob.state === "failed" || inspectedJob.state === "rejected") ? (
                  /* Failed Job Diagnostic & Recovery Panel */
                  <div className="flex flex-col gap-3 pt-1">
                    <div className="rounded-ctl border border-err/30 bg-err/5 p-3.5 flex flex-col gap-2.5">
                      <div className="flex items-start gap-2.5">
                        <Warning size={18} weight="fill" className="text-err shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <h4 className="text-[13px] font-bold text-err">
                            Quá trình tạo Video gặp lỗi trên Google Flow
                          </h4>
                          <p className="text-[11.5px] font-mono text-fg/90 mt-1 break-words">
                            {inspectedJob.error || "Không nhận được phản hồi video từ Google Flow."}
                          </p>
                        </div>
                      </div>

                      <div className="rounded bg-panel2/80 border border-line p-2.5 text-[11px] text-dim leading-relaxed flex flex-col gap-1">
                        <span className="font-semibold text-fg">💡 Nguyên nhân thường gặp & Cách khắc phục:</span>
                        <span>
                          • <strong>Chính sách người nổi tiếng (Celebrity Filter):</strong> Khi dùng ảnh mẫu thật kèm các cụm từ như{" "}
                          <code className="text-acc">&quot;exact young Korean woman from the reference image&quot;</code> hoặc{" "}
                          <code className="text-acc">&quot;Strictly lock facial identity&quot;</code>, bộ lọc của Flow dễ nhận diện nhầm là người nổi tiếng và chặn tạo video (hoàn lại credit).
                        </span>
                        <span>
                          • <strong>Cơ chế tự động mới:</strong> Hệ thống đã được tích hợp bộ lọc tự động loại bỏ các cụm từ nhạy cảm, tự bấm nút{" "}
                          <strong>Thử lại (Retry)</strong> trên thẻ lỗi của Flow và rút ngắn prompt khi cần.
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <button
                          onClick={() => {
                            handleReuseSettings(inspectedJob);
                            setVideoPrompt1((p) => sanitizePromptClient(p));
                            setVideoPrompt2((p) => sanitizePromptClient(p));
                            showToast("Đã làm sạch Prompt (bỏ từ khóa nhạy cảm) & nạp lại vào Studio!", "ok");
                          }}
                          className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer"
                        >
                          <MagicWand size={14} weight="bold" />
                          <span>Làm sạch Prompt & Nạp vào Studio</span>
                        </button>

                        <button
                          onClick={() => handleReuseSettings(inspectedJob)}
                          className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-semibold text-dim hover:text-fg transition-colors cursor-pointer"
                        >
                          <Copy size={13} />
                          <span>Giữ nguyên Prompt gốc</span>
                        </button>
                      </div>
                    </div>

                    {/* Event Logs of the Failed Job */}
                    {inspectedJob.events && inspectedJob.events.length > 0 && (
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
                      Bạn có thể chọn một run từ <strong>khay Jobs / Lịch sử</strong> bên dưới để xem lại video 16s, hoặc bấm <strong>Tạo Video Thật</strong> ở cột trái để bắt đầu lượt chạy mới.
                    </p>
                  </div>
                ) : null}
              </Panel>
            </div>
          </div>

          {/* ================= BOTTOM DOCKED PIPELINE & HISTORY TRAY ================= */}
          <Panel className="p-3 flex flex-col gap-2.5 mt-1 border-t border-line2">
            {/* Tray Header Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
              <div className="flex items-center gap-1 overflow-x-auto text-[11.5px]">
                <button
                  onClick={() => setDockTab("running")}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl font-semibold transition-colors cursor-pointer ${
                    dockTab === "running"
                      ? "bg-acc/15 text-acc border border-acc/30"
                      : "text-dim hover:text-fg"
                  }`}
                >
                  <span className={`size-1.5 rounded-full bg-acc ${runningJobs.length > 0 ? "animate-pulse" : ""}`} />
                  <span>Đang chạy</span>
                  <span className="font-mono text-[10px] bg-panel px-1 py-0.2 rounded font-bold">
                    {runningJobs.length}
                  </span>
                </button>

                <button
                  onClick={() => setDockTab("queued")}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl font-semibold transition-colors cursor-pointer ${
                    dockTab === "queued"
                      ? "bg-panel2 text-fg border border-line2"
                      : "text-dim hover:text-fg"
                  }`}
                >
                  <Hourglass size={12} />
                  <span>Hàng đợi</span>
                  <span className="font-mono text-[10px] bg-panel px-1 py-0.2 rounded font-bold">
                    {queuedJobs.length}
                  </span>
                </button>

                <button
                  onClick={() => setDockTab("done")}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl font-semibold transition-colors cursor-pointer ${
                    dockTab === "done"
                      ? "bg-ok/15 text-ok border border-ok/30"
                      : "text-dim hover:text-fg"
                  }`}
                >
                  <CheckCircle size={12} weight="fill" />
                  <span>Đã xong</span>
                  <span className="font-mono text-[10px] bg-panel px-1 py-0.2 rounded font-bold">
                    {doneJobs.length}
                  </span>
                </button>

                <button
                  onClick={() => setDockTab("all")}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl font-semibold transition-colors cursor-pointer ${
                    dockTab === "all"
                      ? "bg-panel2 text-fg border border-line2"
                      : "text-dim hover:text-fg"
                  }`}
                >
                  <Queue size={12} />
                  <span>Tất cả Jobs ({tryonJobs.length})</span>
                </button>

                <span className="text-line2 mx-1">|</span>

                <button
                  onClick={() => setDockTab("history")}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl font-semibold transition-colors cursor-pointer ${
                    dockTab === "history"
                      ? "bg-panel2 text-acc border border-line2"
                      : "text-dim hover:text-fg"
                  }`}
                >
                  <Clock size={12} />
                  <span>Lịch sử Runs ({historyRuns.length})</span>
                </button>
              </div>

              {/* Tray Height & Expansion Controls */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() =>
                    setDockHeight((h) =>
                      h === "compact" ? "normal" : h === "normal" ? "expanded" : "compact"
                    )
                  }
                  className="inline-flex items-center gap-1 text-[11px] text-mut hover:text-fg px-2 py-0.5 rounded border border-line hover:border-line2 transition-colors cursor-pointer"
                  title="Thay đổi chiều cao khay danh sách"
                >
                  {dockHeight === "compact" ? (
                    <>
                      <CaretUp size={12} />
                      <span>Mở rộng</span>
                    </>
                  ) : dockHeight === "expanded" ? (
                    <>
                      <CaretDown size={12} />
                      <span>Thu gọn</span>
                    </>
                  ) : (
                    <>
                      <ArrowsOut size={12} />
                      <span>Phóng to</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Tray List Cards */}
            <div
              className={`slim-scroll overflow-y-auto transition-all ${
                dockHeight === "compact"
                  ? "max-h-24"
                  : dockHeight === "expanded"
                  ? "max-h-[380px]"
                  : "max-h-48"
              }`}
            >
              {dockTab !== "history" ? (
                /* Jobs List */
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
                  {(dockTab === "running"
                    ? runningJobs
                    : dockTab === "queued"
                    ? queuedJobs
                    : dockTab === "done"
                    ? doneJobs
                    : tryonJobs
                  ).map((job) => {
                    const isSelected = inspectedJobId === job.id;
                    const p1 = (job.params as Record<string, string>)?.video_prompt_1 || "";
                    const ar = (job.params as Record<string, string>)?.aspect_ratio || "9:16";

                    return (
                      <div
                        key={job.id}
                        onClick={() => {
                          setInspectedJobId(job.id);
                          onSelectActiveJobId?.(job.id);
                          if (job.result && (job.result as unknown as TryOnRunManifest).run_id) {
                            setSelectedResultRun(job.result as unknown as TryOnRunManifest);
                          } else {
                            setSelectedResultRun(null);
                          }
                        }}
                        className={`p-2.5 rounded-ctl border text-[11px] flex flex-col justify-between gap-1.5 cursor-pointer transition-all ${
                          isSelected
                            ? "border-acc bg-acc/10 shadow-xs"
                            : "border-line bg-panel2/60 hover:bg-panel2 hover:border-line2"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-fg font-semibold truncate">
                            {job.id}
                          </span>
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

                  {(dockTab === "running"
                    ? runningJobs
                    : dockTab === "queued"
                    ? queuedJobs
                    : dockTab === "done"
                    ? doneJobs
                    : tryonJobs
                  ).length === 0 && (
                    <div className="col-span-full py-6 text-center text-mut text-[11.5px]">
                      Không có job nào trong mục này. Bấm <strong>Tạo Video Thật</strong> để khởi chạy.
                    </div>
                  )}
                </div>
              ) : (
                /* History Runs Strip */
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
                  {historyRuns.slice(0, 24).map((run) => {
                    const isSelected = selectedResultRun?.run_id === run.run_id;
                    return (
                      <div
                        key={run.run_id}
                        onClick={() => {
                          setSelectedResultRun(run);
                          setResultTab("final");
                        }}
                        className={`p-2.5 rounded-ctl border text-[11px] flex gap-2.5 cursor-pointer transition-all ${
                          isSelected
                            ? "border-acc bg-acc/10 shadow-xs"
                            : "border-line bg-panel2/60 hover:bg-panel2 hover:border-line2"
                        }`}
                      >
                        <div className="size-14 rounded bg-black shrink-0 overflow-hidden border border-line flex items-center justify-center">
                          {run.first_frame_url ? (
                            <img
                              src={run.first_frame_url}
                              alt="Thumbnail"
                              className="size-full object-cover"
                            />
                          ) : (
                            <FilmStrip size={18} className="text-mut" />
                          )}
                        </div>

                        <div className="flex-1 min-w-0 flex flex-col justify-between">
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-mono text-fg font-semibold truncate text-[11px]">
                              {run.run_id}
                            </span>
                            <span
                              className={`size-2 rounded-full shrink-0 ${
                                run.status === "succeeded" ? "bg-ok" : "bg-err"
                              }`}
                            />
                          </div>

                          <p className="text-mut line-clamp-1 text-[10px]">
                            {run.video_prompt_1 || run.product_title || "Video 16s"}
                          </p>

                          <div className="flex items-center justify-between text-[10px] text-mut pt-1">
                            <span className="font-mono">{formatDuration(run.elapsed_s)}</span>
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleReuseSettings(run);
                                }}
                                className="text-acc hover:underline cursor-pointer"
                                title="Lấy prompt này vào Studio"
                              >
                                Dùng lại
                              </button>
                              {run.final_video_url && (
                                <a
                                  href={run.final_video_url}
                                  download={`${run.run_id}_16s.mp4`}
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-dim hover:text-fg"
                                  title="Tải MP4"
                                >
                                  <DownloadSimple size={12} />
                                </a>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {historyRuns.length === 0 && (
                    <div className="col-span-full py-6 text-center text-mut text-[11.5px]">
                      Chưa có lịch sử runs nào được ghi nhận.
                    </div>
                  )}
                </div>
              )}
            </div>
          </Panel>
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
                          className="size-full object-cover"
                          preload="metadata"
                        />
                      ) : run.first_frame_url ? (
                        <img
                          src={run.first_frame_url}
                          alt="First Frame"
                          className="size-full object-cover"
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
                        {run.status === "succeeded" ? "16s Hoàn chỉnh" : "Lỗi"}
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
                          download={`${run.run_id}_16s.mp4`}
                          className="text-dim hover:text-fg p-1 rounded hover:bg-line"
                          title="Tải video 16s"
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

      {/* ================= CONFIRMATION MODAL ================= */}
      {confirmModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="rounded-panel border border-line2 bg-panel w-full max-w-md p-5 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-warn/15 text-warn grid place-items-center shrink-0">
                <Warning size={22} weight="bold" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-fg">Xác nhận tạo Video Thử Đồ Thật</h3>
                <p className="text-[12px] text-mut mt-0.5">Sử dụng Google Flow credit</p>
              </div>
            </div>

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

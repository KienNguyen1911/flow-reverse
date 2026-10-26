import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CheckCircle,
  Copy,
  DownloadSimple,
  FilmStrip,
  Image as ImageIcon,
  MagicWand,
  Sparkle,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { Job, PoolInfo, Project, TryOnRunManifest } from "../types";
import { Btn, Chip, Field, Panel, Spinner } from "./ui";

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

interface UploadedFile {
  path: string;
  filename: string;
  url: string;
  size?: number;
}

interface Props {
  projects: Project[];
  selectedProjectId: string | null;
  busy: boolean;
  pool: PoolInfo | null;
  activeJob: Job | null;
  onStartJob: (promise: Promise<{ job_id: string }>) => void;
}

export function TryOnPanel({
  projects,
  selectedProjectId,
  busy,
  activeJob,
  onStartJob,
}: Props) {
  // Check if active job belongs to this workflow
  const isTryOnJob = activeJob?.kind === "auto_tryon";

  // 1. First Frame image state (required)
  const [firstFrame, setFirstFrame] = useState<UploadedFile | null>(null);
  const [firstFrameUploading, setFirstFrameUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // 2. Video Prompts
  const [videoPrompt1, setVideoPrompt1] = useState(
    "A photorealistic young woman wearing the outfit, turns gently to showcase the dress, elegant natural movement, soft studio lighting, high details, 8 seconds"
  );
  const [videoPrompt2, setVideoPrompt2] = useState(
    "Continuing seamlessly from the last frame, the young woman turns 180 degrees to showcase the back details of the garment, then looks over her shoulder with a graceful smile, smooth motion, 8 seconds"
  );

  // 3. Settings
  const [targetProjectId, setTargetProjectId] = useState<string>(selectedProjectId || "");
  const [autoStitch, setAutoStitch] = useState(true);
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9">("9:16");

  // UI state
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [selectedResultRun, setSelectedResultRun] = useState<TryOnRunManifest | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [resultTab, setResultTab] = useState<"final" | "subvideos" | "frames" | "prompts">("final");

  // File input ref
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logScrollRef = useRef<HTMLDivElement>(null);

  // Keep target project in sync if user selects in TopBar
  useEffect(() => {
    if (selectedProjectId && !targetProjectId) {
      setTargetProjectId(selectedProjectId);
    }
  }, [selectedProjectId, targetProjectId]);

  // When tryon job finishes, auto-select latest run result
  useEffect(() => {
    if (isTryOnJob && activeJob && (activeJob.state === "succeeded" || activeJob.state === "failed")) {
      if (activeJob.result && (activeJob.result as unknown as TryOnRunManifest).run_id) {
        setSelectedResultRun(activeJob.result as unknown as TryOnRunManifest);
      }
    }
  }, [activeJob?.state, activeJob?.result, isTryOnJob]);

  // Auto-scroll logs
  useEffect(() => {
    const el = logScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [activeJob?.events?.length]);

  // Determine current pipeline step (1-4) from events
  const currentStep = useMemo(() => {
    if (!isTryOnJob || !activeJob) return 0;
    if (activeJob.state === "succeeded") return 4;
    if (activeJob.state === "failed" || activeJob.state === "rejected") return 0;

    const events = activeJob.events || [];
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
  }, [activeJob?.events, activeJob?.state, isTryOnJob]);

  // Upload handler
  const handleUploadFile = async (file: File) => {
    setFirstFrameUploading(true);
    setErrorMessage(null);
    try {
      const res = await api.upload(file);
      setFirstFrame({
        path: res.path,
        filename: res.filename,
        url: res.url,
        size: res.size,
      });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Tải ảnh First Frame thất bại");
    } finally {
      setFirstFrameUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Sample First Frame button
  const handleUseSampleFirstFrame = () => {
    setFirstFrame({
      path: SAMPLE_FIRST_FRAME_PATH,
      filename: "sample_first_frame.png",
      url: `/api/assets/sample_first_frame.png`,
      size: 684203,
    });
    setErrorMessage(null);
  };

  // Execution triggers
  const executeWorkflow = (dryRun: boolean) => {
    if (busy) return;
    if (!firstFrame) {
      setErrorMessage("Vui lòng tải lên ảnh First Frame (bắt buộc).");
      return;
    }

    setSelectedResultRun(null);
    setErrorMessage(null);

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

    onStartJob(api.tryonStart(payload));
  };

  const handleCopyPrompt = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // The active result to show (either selected run from history or current job result)
  const activeResult: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun) return selectedResultRun;
    if (isTryOnJob && activeJob?.result && (activeJob.result as unknown as TryOnRunManifest).run_id) {
      return activeJob.result as unknown as TryOnRunManifest;
    }
    return null;
  }, [selectedResultRun, activeJob?.result, isTryOnJob]);

  return (
    <div className="p-4 sm:p-5 flex flex-col gap-6">
      {/* Top Banner error */}
      {errorMessage && (
        <div className="flex items-center justify-between gap-3 rounded-ctl border border-err/30 bg-err/10 px-4 py-2.5 text-[12.5px] text-err">
          <span>{errorMessage}</span>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-err/70 hover:text-err cursor-pointer"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {/* Main Grid: Left Controls / Right Execution & Results */}
      <div className="grid gap-6 lg:grid-cols-[460px_minmax(0,1fr)] items-start">
        {/* ================= LEFT COLUMN ================= */}
        <div className="flex flex-col gap-4">
          {/* Section 1: Upload First Frame Image (Required) */}
          <Panel
            className={`p-4 flex flex-col gap-3.5 transition-colors ${
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
                <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                  1
                </span>
                <h3 className="text-[13.5px] font-bold text-fg">
                  Ảnh First Frame (Khởi đầu Video 1)
                </h3>
              </div>
              <span className="text-[11px] font-medium text-warn bg-warn/10 px-2 py-0.5 rounded-full border border-warn/30">
                Bắt buộc
              </span>
            </div>

            {firstFrame ? (
              <div className="relative group rounded-ctl overflow-hidden border border-line2 bg-panel2 p-3 flex items-center gap-3.5">
                <div className="size-20 rounded-ctl overflow-hidden bg-line border border-line2 shrink-0 flex items-center justify-center">
                  <img
                    src={firstFrame.url}
                    alt="First frame"
                    className="size-full object-cover"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 text-ok text-[12px] font-medium">
                    <CheckCircle size={14} weight="fill" />
                    <span>Đã chọn ảnh First Frame</span>
                  </div>
                  <p className="text-[12.5px] font-semibold text-fg truncate mt-1">
                    {firstFrame.filename}
                  </p>
                  <p className="text-[11px] font-mono text-mut">
                    {formatBytes(firstFrame.size)}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-[11.5px] text-acc hover:underline cursor-pointer"
                    >
                      Thay ảnh
                    </button>
                    <span className="text-line2">|</span>
                    <button
                      onClick={() => setFirstFrame(null)}
                      className="text-[11.5px] text-err hover:underline cursor-pointer"
                    >
                      Xóa
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-ctl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
                  isDragging
                    ? "border-acc bg-acc/10 scale-[1.01]"
                    : "border-line2 hover:border-acc/60 bg-panel2/50 hover:bg-panel2"
                }`}
              >
                <div className="size-10 rounded-full bg-acc/10 text-acc grid place-items-center mb-2">
                  <UploadSimple size={20} />
                </div>
                <p className="text-[13px] font-semibold text-fg">
                  {isDragging ? "Thả ảnh First Frame vào đây..." : "Tải lên ảnh First Frame (người mẫu mặc đồ)"}
                </p>
                <p className="text-[11px] text-mut mt-1">
                  Kéo thả hoặc bấm vào đây để chọn ảnh (PNG, JPG, WEBP)
                </p>
                {firstFrameUploading && (
                  <div className="flex items-center gap-2 mt-3 text-acc text-[12px]">
                    <Spinner size={14} />
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

            {/* Quick sample button */}
            <div className="flex items-center justify-between text-[11.5px] pt-1 border-t border-line">
              <button
                type="button"
                onClick={handleUseSampleFirstFrame}
                className="inline-flex items-center gap-1.5 text-acc hover:underline cursor-pointer font-medium"
              >
                <MagicWand size={13} />
                <span>Dùng ảnh First Frame mẫu (test nhanh)</span>
              </button>
              <span className="text-mut text-[11px]">Google Flow 8s</span>
            </div>
          </Panel>

          {/* Section 2: Prompts Video 1 & Video 2 */}
          <Panel className="p-4 flex flex-col gap-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                  2
                </span>
                <h3 className="text-[13.5px] font-bold text-fg">
                  Kịch bản Chuyển động (Video Prompts)
                </h3>
              </div>
              <Chip tone="acc">{`2 Video × 8s · Tỷ lệ ${aspectRatio}`}</Chip>
            </div>

            {/* Prompt Video 1 */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-[12px]">
                <label className="font-semibold text-fg flex items-center gap-1.5">
                  <VideoCamera size={14} className="text-acc" />
                  <span>Prompt Video 1 (0 - 8s)</span>
                </label>
                <span className="text-mut text-[10.5px]">Khởi đầu từ First Frame</span>
              </div>
              <textarea
                rows={3}
                value={videoPrompt1}
                onChange={(e) => setVideoPrompt1(e.target.value)}
                placeholder="A photorealistic young woman wearing the outfit, turns gently..."
                className="w-full rounded-ctl border border-line2 bg-panel2 p-2.5 text-[11.5px] font-mono text-fg focus:border-acc outline-none resize-y"
              />
              <div className="flex flex-wrap gap-1.5 mt-0.5">
                {PRESETS_V1.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setVideoPrompt1(p.prompt)}
                    className="text-[10.5px] rounded bg-panel px-2 py-0.5 border border-line hover:border-acc/60 text-mut hover:text-fg transition-colors cursor-pointer"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Prompt Video 2 */}
            <div className="flex flex-col gap-1.5 pt-2 border-t border-line">
              <div className="flex items-center justify-between text-[12px]">
                <label className="font-semibold text-fg flex items-center gap-1.5">
                  <VideoCamera size={14} className="text-ok" />
                  <span>Prompt Video 2 (8 - 16s)</span>
                </label>
                <span className="text-mut text-[10.5px]">Nối tiếp từ Last Frame Video 1</span>
              </div>
              <textarea
                rows={3}
                value={videoPrompt2}
                onChange={(e) => setVideoPrompt2(e.target.value)}
                placeholder="Continuing seamlessly from the last frame, turning to show back..."
                className="w-full rounded-ctl border border-line2 bg-panel2 p-2.5 text-[11.5px] font-mono text-fg focus:border-acc outline-none resize-y"
              />
              <div className="flex flex-wrap gap-1.5 mt-0.5">
                {PRESETS_V2.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setVideoPrompt2(p.prompt)}
                    className="text-[10.5px] rounded bg-panel px-2 py-0.5 border border-line hover:border-acc/60 text-mut hover:text-fg transition-colors cursor-pointer"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          </Panel>

          {/* Section 3: Project Selector & Settings */}
          <Panel className="p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                3
              </span>
              <h3 className="text-[13.5px] font-bold text-fg">Cấu hình Dự án & Ghép Video</h3>
            </div>

            <div className="flex flex-col gap-2.5 text-[12px]">
              <Field label="Dự án Google Flow">
                <select
                  value={targetProjectId}
                  onChange={(e) => setTargetProjectId(e.target.value)}
                  className="w-full rounded-ctl border border-line2 bg-panel2 px-3 py-1.5 text-[12px] text-fg focus:border-acc outline-none"
                >
                  <option value="">Tự động dùng dự án đang mở trên tab Flow</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title || p.id} ({p.id.slice(0, 8)}...)
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Tỷ lệ khung hình Video">
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <button
                    type="button"
                    onClick={() => setAspectRatio("9:16")}
                    className={`h-9 rounded-ctl border text-[11.5px] font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      aspectRatio === "9:16"
                        ? "border-acc bg-acc/15 text-acc shadow-sm shadow-acc/10"
                        : "border-line2 bg-panel2 text-mut hover:text-fg"
                    }`}
                  >
                    <span>📱 9:16 (Dọc - TikTok, Reels, Shorts)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setAspectRatio("16:9")}
                    className={`h-9 rounded-ctl border text-[11.5px] font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      aspectRatio === "16:9"
                        ? "border-acc bg-acc/15 text-acc shadow-sm shadow-acc/10"
                        : "border-line2 bg-panel2 text-mut hover:text-fg"
                    }`}
                  >
                    <span>🖥️ 16:9 (Ngang - Cinema, YouTube)</span>
                  </button>
                </div>
              </Field>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="autoStitch"
                  checked={autoStitch}
                  onChange={(e) => setAutoStitch(e.target.checked)}
                  className="rounded accent-acc cursor-pointer"
                />
                <label htmlFor="autoStitch" className="text-[12px] font-medium text-fg cursor-pointer">
                  Tự động ghép 2 video thành Video 16s hoàn chỉnh (FFmpeg)
                </label>
              </div>
            </div>
          </Panel>

          {/* Section 4: Action Button */}
          <div className="flex flex-col gap-2.5">
            <Btn
              variant="primary"
              icon={<Sparkle size={16} weight="fill" />}
              busy={busy}
              disabled={busy}
              onClick={() => setConfirmModalOpen(true)}
              className="h-11 font-semibold w-full"
              title="Thực hiện tạo Video 1, trích xuất Last Frame và tạo Video 2 thật trên Flow"
            >
              <span>Tạo Video thật</span>
              <span className="text-[10px] bg-accink/20 px-1.5 py-0.5 rounded text-accink font-bold">~2 cr</span>
            </Btn>
          </div>
        </div>

        {/* ================= RIGHT COLUMN: EXECUTION & RESULTS ================= */}
        <div className="flex flex-col gap-5 min-w-0">
          {/* Step-by-Step Progress Pipeline (4 steps) */}
          <Panel className="p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <FilmStrip size={18} className="text-acc" weight="bold" />
                <h3 className="text-[13.5px] font-bold text-fg">Tiến trình Workflow 16s</h3>
              </div>
              <div className="flex items-center gap-2">
                {busy && isTryOnJob && (
                  <span className="inline-flex items-center gap-1.5 text-acc text-[12px] font-medium">
                    <Spinner size={12} />
                    <span>Đang xử lý bước {currentStep}/4</span>
                  </span>
                )}
                {isTryOnJob && activeJob?.state === "succeeded" && (
                  <span className="inline-flex items-center gap-1 text-ok text-[12px] font-medium">
                    <CheckCircle size={14} weight="fill" />
                    <span>Hoàn thành xuất sắc</span>
                  </span>
                )}
                {isTryOnJob && activeJob?.state === "failed" && (
                  <span className="inline-flex items-center gap-1 text-err text-[12px] font-medium">
                    <Warning size={14} weight="bold" />
                    <span className="truncate max-w-[200px]" title={activeJob.error || "Thất bại"}>
                      Lỗi: {activeJob.error || "Thất bại"}
                    </span>
                  </span>
                )}
              </div>
            </div>

            {/* 4 Steps Visual Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {STEPS.map((s) => {
                const isCurrent = busy && isTryOnJob && currentStep === s.id;
                const isDone =
                  (busy && isTryOnJob && currentStep > s.id) ||
                  (isTryOnJob && activeJob?.state === "succeeded");

                return (
                  <div
                    key={s.id}
                    className={`p-2.5 rounded-ctl border text-[11.5px] flex flex-col transition-all ${
                      isCurrent
                        ? "border-acc bg-acc/10 text-fg shadow-sm shadow-acc/10"
                        : isDone
                        ? "border-ok/30 bg-ok/5 text-fg"
                        : "border-line2 bg-panel2/50 text-mut"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] font-bold">0{s.id}</span>
                      {isDone ? (
                        <Check size={13} className="text-ok" weight="bold" />
                      ) : isCurrent ? (
                        <Spinner size={12} className="text-acc" />
                      ) : (
                        <span className="size-1.5 rounded-full bg-mut/40" />
                      )}
                    </div>
                    <span className="font-semibold mt-1 leading-snug line-clamp-1">{s.label}</span>
                    <span className="text-[10px] text-mut truncate mt-0.5">{s.desc}</span>
                  </div>
                );
              })}
            </div>

            {/* Live Job Console & Events */}
            {isTryOnJob && activeJob && activeJob.events && activeJob.events.length > 0 && (
              <div className="mt-2 flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-[11px] text-mut">
                  <span>Nhật ký thời gian thực ({activeJob.id})</span>
                  <span>{activeJob.events.length} sự kiện</span>
                </div>
                <div
                  ref={logScrollRef}
                  className="slim-scroll max-h-36 overflow-y-auto rounded-ctl bg-ink/70 border border-line p-2.5 font-mono text-[11px] leading-relaxed flex flex-col gap-1"
                >
                  {activeJob.events.map((ev, i) => (
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
          </Panel>

          {/* ================= RESULT VIEWER ================= */}
          {activeResult ? (
            <Panel className="p-4 sm:p-5 flex flex-col gap-4 border-acc/30">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="size-8 rounded-full bg-ok/15 text-ok grid place-items-center">
                    <CheckCircle size={20} weight="fill" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-[14px] font-bold text-fg">
                        Kết Quả Video Thử Đồ 16 Giây
                      </h3>
                      {selectedResultRun && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-line2 text-mut">
                          <span>Từ lịch sử</span>
                          <button
                            onClick={() => setSelectedResultRun(null)}
                            title="Đóng / Bỏ chọn"
                            className="hover:text-fg cursor-pointer"
                          >
                            <X size={11} />
                          </button>
                        </span>
                      )}
                    </div>
                    <p className="text-[11.5px] font-mono text-mut">
                      Run ID: {activeResult.run_id} · {activeResult.elapsed_s}s
                      {activeResult.dry_run && " · [Dry-run]"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {selectedResultRun && (
                    <Btn
                      variant="ghost"
                      className="h-8 text-[11.5px] px-2.5"
                      onClick={() => setSelectedResultRun(null)}
                    >
                      Bỏ chọn
                    </Btn>
                  )}
                  {activeResult.final_video_url && (
                    <a
                      href={activeResult.final_video_url}
                      download={`${activeResult.run_id}_16s.mp4`}
                      className="inline-flex items-center gap-2 rounded-ctl bg-acc text-accink px-3.5 h-8 text-[12.5px] font-bold hover:bg-acc2 transition-colors"
                    >
                      <DownloadSimple size={15} weight="bold" />
                      <span>Tải Video 16s</span>
                    </a>
                  )}
                </div>
              </div>

              {/* Sub-tabs for Result View */}
              <div className="flex items-center gap-2 border-b border-line2 pb-2">
                <button
                  onClick={() => setResultTab("final")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "final" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  Video 16s Hoàn Chỉnh
                </button>
                <button
                  onClick={() => setResultTab("subvideos")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "subvideos" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  Video 1 & 2 (8s + 8s)
                </button>
                <button
                  onClick={() => setResultTab("frames")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "frames" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  First & Last Frame
                </button>
                <button
                  onClick={() => setResultTab("prompts")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "prompts" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  Kịch Bản Prompts
                </button>
              </div>

              {/* TAB 1: FINAL 16S VIDEO */}
              {resultTab === "final" && (
                <div className="flex flex-col gap-3">
                  {activeResult.final_video_url ? (
                    <div className="rounded-panel overflow-hidden bg-black border border-line max-h-[460px] flex items-center justify-center">
                      <video
                        controls
                        src={activeResult.final_video_url}
                        className="w-full max-h-[460px] object-contain"
                        autoPlay
                        muted
                        loop
                        playsInline
                      />
                    </div>
                  ) : (
                    <div className="p-8 text-center text-mut rounded-ctl bg-panel2">
                      <VideoCamera size={32} className="mx-auto mb-2 opacity-50" />
                      <p className="text-[13px]">Chưa tìm thấy video 16s ghép nối cuối cùng.</p>
                      <p className="text-[11px] text-mut mt-1">
                        Kiểm tra các video con 8s ở tab "Video 1 & 2".
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: SUB-VIDEOS (VIDEO 1 & VIDEO 2) */}
              {resultTab === "subvideos" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Video 1 (8s) */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <VideoCamera size={14} className="text-acc" />
                        <span>Video 1 (0-8s)</span>
                      </span>
                      {activeResult.video_1_url && (
                        <a
                          href={activeResult.video_1_url}
                          download="video_1.mp4"
                          className="text-mut hover:text-fg"
                          title="Tải Video 1"
                        >
                          <DownloadSimple size={14} />
                        </a>
                      )}
                    </div>
                    {activeResult.video_1_url ? (
                      <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] flex items-center justify-center">
                        <video
                          controls
                          src={activeResult.video_1_url}
                          className="size-full object-cover"
                          playsInline
                        />
                      </div>
                    ) : (
                      <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                        Không có video 1
                      </div>
                    )}
                  </div>

                  {/* Video 2 (8s) */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <VideoCamera size={14} className="text-ok" />
                        <span>Video 2 (8-16s)</span>
                      </span>
                      {activeResult.video_2_url && (
                        <a
                          href={activeResult.video_2_url}
                          download="video_2.mp4"
                          className="text-mut hover:text-fg"
                          title="Tải Video 2"
                        >
                          <DownloadSimple size={14} />
                        </a>
                      )}
                    </div>
                    {activeResult.video_2_url ? (
                      <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] flex items-center justify-center">
                        <video
                          controls
                          src={activeResult.video_2_url}
                          className="size-full object-cover"
                          playsInline
                        />
                      </div>
                    ) : (
                      <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                        Không có video 2
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 3: FIRST & LAST FRAME */}
              {resultTab === "frames" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* First Frame Image */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <ImageIcon size={14} className="text-acc" />
                        <span>First Frame (Khởi đầu Video 1)</span>
                      </span>
                      {activeResult.first_frame_url && (
                        <a
                          href={activeResult.first_frame_url}
                          download="first_frame.png"
                          className="text-mut hover:text-fg"
                          title="Tải First Frame"
                        >
                          <DownloadSimple size={14} />
                        </a>
                      )}
                    </div>
                    {activeResult.first_frame_url ? (
                      <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] flex items-center justify-center">
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

                  {/* Last Frame Video 1 */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <ImageIcon size={14} className="text-ok" />
                        <span>Last Frame Video 1 (FFmpeg trích xuất)</span>
                      </span>
                      {activeResult.last_frame_url && (
                        <a
                          href={activeResult.last_frame_url}
                          download="last_frame_video_1.png"
                          className="text-mut hover:text-fg"
                          title="Tải Last Frame"
                        >
                          <DownloadSimple size={14} />
                        </a>
                      )}
                    </div>
                    {activeResult.last_frame_url ? (
                      <div className="rounded-ctl overflow-hidden bg-black border border-line2 aspect-[3/4] flex items-center justify-center">
                        <img
                          src={activeResult.last_frame_url}
                          alt="Last Frame"
                          className="size-full object-cover"
                        />
                      </div>
                    ) : (
                      <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                        Không có last frame
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 4: PROMPTS */}
              {resultTab === "prompts" && (
                <div className="flex flex-col gap-3">
                  {/* Video Prompt 1 */}
                  <div className="p-3 rounded-ctl bg-panel2 border border-line flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <VideoCamera size={14} className="text-acc" />
                        <span>Video Prompt 1 (0-8s)</span>
                      </span>
                      <button
                        onClick={() => handleCopyPrompt(activeResult.video_prompt_1 || "", "vp1")}
                        className="text-[11px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                      >
                        {copiedKey === "vp1" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                        <span>{copiedKey === "vp1" ? "Đã chép" : "Sao chép"}</span>
                      </button>
                    </div>
                    <p className="font-mono text-[11.5px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                      {activeResult.video_prompt_1 || "(Chưa có dữ liệu prompt)"}
                    </p>
                  </div>

                  {/* Video Prompt 2 */}
                  <div className="p-3 rounded-ctl bg-panel2 border border-line flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <VideoCamera size={14} className="text-ok" />
                        <span>Video Prompt 2 (8-16s)</span>
                      </span>
                      <button
                        onClick={() => handleCopyPrompt(activeResult.video_prompt_2 || "", "vp2")}
                        className="text-[11px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                      >
                        {copiedKey === "vp2" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                        <span>{copiedKey === "vp2" ? "Đã chép" : "Sao chép"}</span>
                      </button>
                    </div>
                    <p className="font-mono text-[11.5px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                      {activeResult.video_prompt_2 || "(Chưa có dữ liệu prompt)"}
                    </p>
                  </div>
                </div>
              )}
            </Panel>
          ) : (
            <Panel className="p-8 text-center text-mut flex flex-col items-center justify-center min-h-[300px]">
              <VideoCamera size={44} className="opacity-30 mb-3" />
              <h4 className="text-[14px] font-semibold text-dim">Chưa có kết quả chạy nào</h4>
              <p className="text-[12px] text-mut max-w-[420px] mt-1.5 leading-relaxed">
                Tải lên <strong>Ảnh First Frame</strong> và bấm <strong>Tạo Video thật</strong>. Video 16s cùng hình ảnh các khung hình sẽ xuất hiện trực tiếp tại đây.
              </p>
            </Panel>
          )}
        </div>
      </div>

      {/* ================= CONFIRMATION MODAL FOR REAL RUN ================= */}
      {confirmModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="rounded-panel border border-line2 bg-panel w-full max-w-md p-5 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-warn/15 text-warn grid place-items-center shrink-0">
                <Warning size={22} weight="bold" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-fg">Xác nhận tạo Video Thử Đồ thật</h3>
                <p className="text-[12px] text-mut mt-0.5">Quá trình này sử dụng credit Google Flow</p>
              </div>
            </div>

            <div className="rounded-ctl bg-panel2 border border-line p-3 text-[12px] leading-relaxed flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-mut">Video 1 (8 giây):</span>
                <span className="font-mono text-fg">~1 Flow Credit</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-mut">Video 2 (8 giây):</span>
                <span className="font-mono text-fg">~1 Flow Credit</span>
              </div>
              <div className="border-t border-line2 pt-1.5 flex items-center justify-between font-bold text-acc">
                <span>Tổng chi phí ước tính:</span>
                <span className="font-mono">~2 Credits</span>
              </div>
            </div>

            <p className="text-[11.5px] text-dim leading-relaxed">
              Video 16s sẽ được tự động trích xuất Last Frame từ Video 1 bằng FFmpeg và ghép nối liền mạch sau khi Video 2 render hoàn tất.
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

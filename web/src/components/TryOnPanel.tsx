import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowClockwise,
  ArrowSquareOut,
  CaretDown,
  CaretRight,
  Check,
  CheckCircle,
  Copy,
  DownloadSimple,
  Eye,
  FilmStrip,
  Flask,
  Image as ImageIcon,
  MagicWand,
  Plus,
  Sparkle,
  Trash,
  UploadSimple,
  VideoCamera,
  Warning,
  X,
} from "@phosphor-icons/react";
import { motion, AnimatePresence } from "motion/react";
import { api } from "../api";
import { useTryOnRuns } from "../hooks";
import type { Job, PoolInfo, Project, TryOnRunManifest } from "../types";
import { Btn, Chip, Field, IconBtn, Panel, Spinner } from "./ui";

const DEFAULT_NABI_PATH = "assets/nabi_model.png";
const SAMPLE_GARMENT_PATH = "assets/sample_garment.png";

const STEPS = [
  { id: 1, key: "step_1", label: "Chuẩn bị hình ảnh", desc: "Nabi + Mẫu trang phục" },
  { id: 2, key: "step_2", label: "Gemini Image Prompt", desc: "Nabi Studio phân tích phối đồ" },
  { id: 3, key: "step_3", label: "Flow First Frame", desc: "Tạo ảnh người mẫu mặc đồ" },
  { id: 4, key: "step_4", label: "Gemini Video Prompts", desc: "Sinh 2 kịch bản video 8s" },
  { id: 5, key: "step_5", label: "Flow Video 1 (8s)", desc: "Render cảnh chuyển động 1" },
  { id: 6, key: "step_6", label: "Trích xuất Last Frame", desc: "FFmpeg cắt frame chính xác" },
  { id: 7, key: "step_7", label: "Flow Video 2 (8s)", desc: "Render cảnh nối tiếp 2" },
  { id: 8, key: "step_8", label: "Ghép hoàn chỉnh 16s", desc: "Nối liền mạch không giật" },
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
  pool,
  activeJob,
  onStartJob,
}: Props) {
  // Check if active job belongs to this workflow
  const isTryOnJob = activeJob?.kind === "auto_tryon";

  // Model state
  const [useDefaultModel, setUseDefaultModel] = useState(true);
  const [customModel, setCustomModel] = useState<UploadedFile | null>(null);
  const [modelUploading, setModelUploading] = useState(false);
  const [isDraggingModel, setIsDraggingModel] = useState(false);

  // Transfer / garment image state (required)
  const [garmentImage, setGarmentImage] = useState<UploadedFile | null>(null);
  const [garmentUploading, setGarmentUploading] = useState(false);
  const [isDraggingGarment, setIsDraggingGarment] = useState(false);

  // Extra images state (optional)
  const [extraImages, setExtraImages] = useState<UploadedFile[]>([]);
  const [extraUploading, setExtraUploading] = useState(false);
  const [isDraggingExtra, setIsDraggingExtra] = useState(false);

  // Alternative input: Shopee URL or product dir
  const [showAltInput, setShowAltInput] = useState(false);
  const [shopeeUrl, setShopeeUrl] = useState("");
  const [productDir, setProductDir] = useState("");

  // Advanced prompt overrides
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [overrideImagePrompt, setOverrideImagePrompt] = useState("");
  const [overrideVideoPrompt1, setOverrideVideoPrompt1] = useState("");
  const [overrideVideoPrompt2, setOverrideVideoPrompt2] = useState("");
  const [targetProjectId, setTargetProjectId] = useState<string>(selectedProjectId || "");
  const [autoStitch, setAutoStitch] = useState(true);

  // UI state
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [selectedResultRun, setSelectedResultRun] = useState<TryOnRunManifest | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [resultTab, setResultTab] = useState<"final" | "frames" | "prompts">("final");

  // File input refs
  const modelInputRef = useRef<HTMLInputElement>(null);
  const garmentInputRef = useRef<HTMLInputElement>(null);
  const extraInputRef = useRef<HTMLInputElement>(null);
  const logScrollRef = useRef<HTMLDivElement>(null);

  // Runs history hook
  const { runs, loading: runsLoading, refresh: refreshRuns } = useTryOnRuns();

  // Keep target project in sync if user selects in TopBar
  useEffect(() => {
    if (selectedProjectId && !targetProjectId) {
      setTargetProjectId(selectedProjectId);
    }
  }, [selectedProjectId, targetProjectId]);

  // When tryon job finishes, refresh history and auto-select latest run
  useEffect(() => {
    if (isTryOnJob && activeJob && (activeJob.state === "succeeded" || activeJob.state === "failed")) {
      refreshRuns(true);
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

  // Determine current pipeline step from events
  const currentStep = useMemo(() => {
    if (!isTryOnJob || !activeJob) return 0;
    if (activeJob.state === "succeeded") return 8;
    if (activeJob.state === "failed" || activeJob.state === "rejected") return 0;

    const events = activeJob.events || [];
    let highestStep = 1;
    for (const ev of events) {
      const match = ev.message.match(/bước\s*(\d)/i);
      if (match) {
        const stepNum = parseInt(match[1], 10);
        if (stepNum >= 1 && stepNum <= 8) highestStep = Math.max(highestStep, stepNum);
      } else {
        const msg = ev.message.toLowerCase();
        if (msg.includes("image prompt")) highestStep = Math.max(highestStep, 2);
        else if (msg.includes("first frame")) highestStep = Math.max(highestStep, 3);
        else if (msg.includes("video prompt")) highestStep = Math.max(highestStep, 4);
        else if (msg.includes("video 1")) highestStep = Math.max(highestStep, 5);
        else if (msg.includes("last frame")) highestStep = Math.max(highestStep, 6);
        else if (msg.includes("video 2")) highestStep = Math.max(highestStep, 7);
        else if (msg.includes("nối") || msg.includes("ghép")) highestStep = Math.max(highestStep, 8);
      }
    }
    return highestStep;
  }, [activeJob?.events, activeJob?.state, isTryOnJob]);

  // Upload helper
  const uploadSingleFile = async (
    file: File,
    onSuccess: (uf: UploadedFile) => void,
    setLoading: (l: boolean) => void,
    fallbackError: string,
  ) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.upload(file);
      onSuccess({
        path: res.path,
        filename: res.filename,
        url: res.url,
        size: res.size,
      });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : fallbackError);
    } finally {
      setLoading(false);
    }
  };

  // Upload handlers
  const handleModelFile = (file: File) => {
    uploadSingleFile(
      file,
      (uf) => {
        setCustomModel(uf);
        setUseDefaultModel(false);
      },
      setModelUploading,
      "Tải ảnh người mẫu thất bại",
    );
  };

  const handleGarmentFile = (file: File) => {
    uploadSingleFile(
      file,
      (uf) => setGarmentImage(uf),
      setGarmentUploading,
      "Tải ảnh mẫu mặc thử thất bại",
    );
  };

  const handleExtraFiles = async (files: FileList | File[]) => {
    if (!files || files.length === 0) return;
    setExtraUploading(true);
    setErrorMessage(null);
    try {
      const uploaded: UploadedFile[] = [];
      for (let i = 0; i < files.length; i++) {
        const res = await api.upload(files[i]);
        uploaded.push({
          path: res.path,
          filename: res.filename,
          url: res.url,
          size: res.size,
        });
      }
      setExtraImages((prev) => [...prev, ...uploaded]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Tải ảnh phụ thất bại");
    } finally {
      setExtraUploading(false);
      if (extraInputRef.current) extraInputRef.current.value = "";
    }
  };

  const handleUseSampleGarment = () => {
    setGarmentImage({
      path: SAMPLE_GARMENT_PATH,
      filename: "sample_garment.png",
      url: `/api/assets/sample_garment.png`,
      size: 4599,
    });
    setErrorMessage(null);
  };

  // Validation
  const validateStart = (): boolean => {
    if (!garmentImage && !shopeeUrl && !productDir) {
      setErrorMessage("Vui lòng tải lên ảnh mẫu trang phục mặc thử (bắt buộc).");
      return false;
    }
    setErrorMessage(null);
    return true;
  };

  // Execution triggers
  const executeWorkflow = (dryRun: boolean) => {
    if (busy) return;
    if (!validateStart()) return;

    setSelectedResultRun(null); // Clear selected history view so fresh job result shows up
    setErrorMessage(null);

    const modelPath = useDefaultModel
      ? DEFAULT_NABI_PATH
      : customModel?.path || DEFAULT_NABI_PATH;

    const payload = {
      model_path: modelPath,
      garment_path: garmentImage?.path || undefined,
      transfer_image: garmentImage?.path || undefined,
      extra_images: extraImages.length > 0 ? extraImages.map((x) => x.path) : undefined,
      shopee_url: shopeeUrl.trim() || undefined,
      product_dir: productDir.trim() || undefined,
      project_id: targetProjectId.trim() || undefined,
      dry_run: dryRun,
      confirm: !dryRun,
      auto_stitch: autoStitch,
      image_prompt: overrideImagePrompt.trim() || undefined,
      video_prompt_1: overrideVideoPrompt1.trim() || undefined,
      video_prompt_2: overrideVideoPrompt2.trim() || undefined,
    };

    onStartJob(api.tryonStart(payload));
  };

  const handleCopyPrompt = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // The active result to show (either user-selected run from history or current job result)
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
      <div className="grid gap-6 lg:grid-cols-[440px_minmax(0,1fr)] items-start">
        {/* ================= LEFT COLUMN ================= */}
        <div className="flex flex-col gap-4">
          {/* Card 1: Nabi Model Selector */}
          <Panel
            className={`p-4 flex flex-col gap-3.5 transition-colors ${
              isDraggingModel ? "border-acc bg-acc/5" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDraggingModel(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setIsDraggingModel(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setIsDraggingModel(false);
              const file = e.dataTransfer.files?.[0];
              if (file) handleModelFile(file);
            }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                  1
                </span>
                <h3 className="text-[13.5px] font-bold text-fg">Người mẫu Nabi</h3>
              </div>
              <Chip tone={useDefaultModel ? "acc" : "neutral"}>
                {useDefaultModel ? "Nabi Mặc định" : "Người mẫu riêng"}
              </Chip>
            </div>

            <div className="flex items-center gap-3.5 p-2.5 rounded-ctl bg-panel2 border border-line">
              <div className="size-16 rounded-ctl overflow-hidden bg-line border border-line2 shrink-0 flex items-center justify-center">
                <img
                  src={useDefaultModel ? "/api/assets/nabi_model.png" : customModel?.url || "/api/assets/nabi_model.png"}
                  alt="Nabi Model"
                  className="size-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = "none";
                  }}
                />
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-[12.5px] font-semibold text-fg truncate">
                  {useDefaultModel ? "Nabi Avatar (assets/nabi_model.png)" : customModel?.filename || "Ảnh tùy chỉnh"}
                </p>
                <p className="text-[11px] text-mut truncate mt-0.5">
                  {useDefaultModel
                    ? "Gương mặt & vóc dáng chuẩn của Nabi Studio"
                    : `Kích thước: ${formatBytes(customModel?.size)}`}
                </p>

                <div className="flex items-center gap-2 mt-2">
                  <Btn
                    variant={useDefaultModel ? "solid" : "ghost"}
                    className="h-7 text-[11.5px] px-2.5"
                    onClick={() => setUseDefaultModel(true)}
                  >
                    Mặc định Nabi
                  </Btn>
                  <Btn
                    variant={!useDefaultModel ? "solid" : "ghost"}
                    className="h-7 text-[11.5px] px-2.5"
                    busy={modelUploading}
                    onClick={() => modelInputRef.current?.click()}
                  >
                    Tải ảnh khác
                  </Btn>
                  <input
                    ref={modelInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleModelFile(f);
                      if (modelInputRef.current) modelInputRef.current.value = "";
                    }}
                  />
                </div>
              </div>
            </div>
          </Panel>

          {/* Card 2: Transfer Garment / Outfit (Required) */}
          <Panel className="p-4 flex flex-col gap-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                  2
                </span>
                <h3 className="text-[13.5px] font-bold text-fg">
                  Mẫu mặc thử (Transfer Model / Garment)
                </h3>
              </div>
              <span className="text-[11px] font-medium text-warn bg-warn/10 px-2 py-0.5 rounded-full border border-warn/30">
                Bắt buộc
              </span>
            </div>

            {garmentImage ? (
              <div className="relative group rounded-ctl overflow-hidden border border-line2 bg-panel2 p-3 flex items-center gap-3">
                <div className="size-20 rounded-ctl overflow-hidden bg-line border border-line2 shrink-0">
                  <img
                    src={garmentImage.url}
                    alt="Garment sample"
                    className="size-full object-cover"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 text-ok text-[12px] font-medium">
                    <CheckCircle size={14} weight="fill" />
                    <span>Đã sẵn sàng tạo đồ</span>
                  </div>
                  <p className="text-[12.5px] font-semibold text-fg truncate mt-1">
                    {garmentImage.filename}
                  </p>
                  <p className="text-[11px] font-mono text-mut">
                    {formatBytes(garmentImage.size)}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      onClick={() => garmentInputRef.current?.click()}
                      className="text-[11.5px] text-acc hover:underline cursor-pointer"
                    >
                      Thay ảnh
                    </button>
                    <span className="text-line2">|</span>
                    <button
                      onClick={() => setGarmentImage(null)}
                      className="text-[11.5px] text-err hover:underline cursor-pointer"
                    >
                      Xóa
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div
                onClick={() => garmentInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDraggingGarment(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDraggingGarment(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDraggingGarment(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleGarmentFile(file);
                }}
                className={`border-2 border-dashed rounded-ctl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
                  isDraggingGarment
                    ? "border-acc bg-acc/10 scale-[1.01]"
                    : "border-line2 hover:border-acc/60 bg-panel2/50 hover:bg-panel2"
                }`}
              >
                <div className="size-10 rounded-full bg-acc/10 text-acc grid place-items-center mb-2">
                  <UploadSimple size={20} />
                </div>
                <p className="text-[13px] font-semibold text-fg">
                  {isDraggingGarment ? "Thả ảnh vào đây ngay..." : "Tải lên ảnh trang phục / mẫu mặc thử"}
                </p>
                <p className="text-[11px] text-mut mt-1">
                  Kéo thả hoặc bấm vào đây để chọn ảnh (PNG, JPG, WEBP)
                </p>
                {garmentUploading && (
                  <div className="flex items-center gap-2 mt-3 text-acc text-[12px]">
                    <Spinner size={14} />
                    <span>Đang tải ảnh lên...</span>
                  </div>
                )}
              </div>
            )}
            <input
              ref={garmentInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleGarmentFile(f);
                if (garmentInputRef.current) garmentInputRef.current.value = "";
              }}
            />

            {/* Quick sample garment button & Alternative toggle */}
            <div className="flex items-center justify-between text-[11.5px] pt-1 border-t border-line">
              <button
                type="button"
                onClick={handleUseSampleGarment}
                className="inline-flex items-center gap-1.5 text-acc hover:underline cursor-pointer font-medium"
              >
                <MagicWand size={13} />
                <span>Dùng mẫu áo thử nghiệm (sample_garment.png)</span>
              </button>

              <button
                type="button"
                onClick={() => setShowAltInput(!showAltInput)}
                className="text-dim hover:text-fg flex items-center gap-1 cursor-pointer"
              >
                {showAltInput ? <CaretDown size={12} /> : <CaretRight size={12} />}
                <span>Shopee URL / Thư mục</span>
              </button>
            </div>

            {showAltInput && (
              <div className="mt-1 flex flex-col gap-2 p-3 rounded-ctl bg-panel2 border border-line text-[12px]">
                <Field label="Shopee Affiliate Offer URL">
                  <input
                    type="text"
                    placeholder="https://affiliate.shopee.vn/offer/..."
                    value={shopeeUrl}
                    onChange={(e) => setShopeeUrl(e.target.value)}
                    className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12px] font-mono text-fg focus:border-acc outline-none"
                  />
                </Field>
                <Field label="Đường dẫn thư mục sản phẩm máy chủ">
                  <input
                    type="text"
                    placeholder="out/sample_product"
                    value={productDir}
                    onChange={(e) => setProductDir(e.target.value)}
                    className="w-full rounded-ctl border border-line2 bg-panel px-3 py-1.5 text-[12px] font-mono text-fg focus:border-acc outline-none"
                  />
                </Field>
              </div>
            )}
          </Panel>

          {/* Card 3: Optional Extra Images */}
          <Panel
            className={`p-4 flex flex-col gap-3 transition-colors ${
              isDraggingExtra ? "border-acc bg-acc/5" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDraggingExtra(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setIsDraggingExtra(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setIsDraggingExtra(false);
              const files = e.dataTransfer.files;
              if (files && files.length > 0) handleExtraFiles(files);
            }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="grid place-items-center size-6 rounded-full bg-acc/15 text-acc text-[11px] font-bold">
                  3
                </span>
                <h3 className="text-[13.5px] font-bold text-fg">Ảnh phụ sản phẩm</h3>
              </div>
              <span className="text-[11px] text-mut">Tùy chọn</span>
            </div>

            <p className="text-[11.5px] text-dim">
              Thêm các góc chụp khác, mặt sau hoặc cận cảnh chất liệu vải để Gemini mô tả chân thật hơn.
            </p>

            <div className="flex flex-wrap gap-2">
              {extraImages.map((img, idx) => (
                <div
                  key={img.path + idx}
                  className="relative group size-16 rounded-ctl overflow-hidden border border-line2 bg-panel2"
                >
                  <img src={img.url} alt="Extra" className="size-full object-cover" />
                  <button
                    onClick={() => setExtraImages((prev) => prev.filter((_, i) => i !== idx))}
                    className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-err transition-opacity cursor-pointer"
                  >
                    <Trash size={16} />
                  </button>
                </div>
              ))}

              <button
                type="button"
                onClick={() => extraInputRef.current?.click()}
                disabled={extraUploading}
                className="size-16 rounded-ctl border-2 border-dashed border-line2 hover:border-acc/60 flex flex-col items-center justify-center text-mut hover:text-fg text-[11px] cursor-pointer transition-colors"
              >
                {extraUploading ? <Spinner size={16} /> : <Plus size={16} />}
                <span className="mt-0.5">Thêm ảnh</span>
              </button>
            </div>
            <input
              ref={extraInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                const fs = e.target.files;
                if (fs) handleExtraFiles(fs);
              }}
            />
          </Panel>

          {/* Card 4: Advanced Settings & Custom Prompts */}
          <Panel className="p-4 flex flex-col gap-3">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center justify-between text-[12.5px] font-semibold text-fg cursor-pointer"
            >
              <div className="flex items-center gap-2">
                <span>Tùy chỉnh Nâng cao & Prompt Chỉ định</span>
                <span className="text-[11px] font-normal text-mut">(Tùy chọn)</span>
              </div>
              {showAdvanced ? <CaretDown size={14} /> : <CaretRight size={14} />}
            </button>

            {showAdvanced && (
              <div className="flex flex-col gap-3 pt-2 text-[12px] border-t border-line">
                <Field label="Dự án Google Flow">
                  <select
                    value={targetProjectId}
                    onChange={(e) => setTargetProjectId(e.target.value)}
                    className="w-full rounded-ctl border border-line2 bg-panel2 px-3 py-1.5 text-[12px] text-fg focus:border-acc outline-none"
                  >
                    <option value="">Tự động dò tìm dự án hợp lệ trên account</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title || p.id} ({p.id.slice(0, 8)}...)
                      </option>
                    ))}
                  </select>
                </Field>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="autoStitch"
                    checked={autoStitch}
                    onChange={(e) => setAutoStitch(e.target.checked)}
                    className="rounded accent-acc"
                  />
                  <label htmlFor="autoStitch" className="text-[12px] font-medium text-fg cursor-pointer">
                    Tự động ghép nối video 16s hoàn chỉnh (`final_tryon_video_16s.mp4`)
                  </label>
                </div>

                <Field
                  label="Override Image Prompt"
                  hint="Để trống nếu muốn Gemini Nabi Studio tự sinh theo mẫu áo"
                >
                  <textarea
                    rows={2}
                    value={overrideImagePrompt}
                    onChange={(e) => setOverrideImagePrompt(e.target.value)}
                    placeholder="Full-body portrait of female model Nabi wearing..."
                    className="w-full rounded-ctl border border-line2 bg-panel2 p-2.5 text-[11.5px] font-mono text-fg focus:border-acc outline-none"
                  />
                </Field>

                <Field
                  label="Override Video Prompt 1 (0-8s)"
                  hint="Mô tả chuyển động cho 8 giây đầu tiên"
                >
                  <textarea
                    rows={2}
                    value={overrideVideoPrompt1}
                    onChange={(e) => setOverrideVideoPrompt1(e.target.value)}
                    placeholder="Nabi stands elegantly, camera slow zoom in..."
                    className="w-full rounded-ctl border border-line2 bg-panel2 p-2.5 text-[11.5px] font-mono text-fg focus:border-acc outline-none"
                  />
                </Field>

                <Field
                  label="Override Video Prompt 2 (8-16s)"
                  hint="Mô tả chuyển động cho 8 giây tiếp nối từ Last Frame"
                >
                  <textarea
                    rows={2}
                    value={overrideVideoPrompt2}
                    onChange={(e) => setOverrideVideoPrompt2(e.target.value)}
                    placeholder="Nabi turns slightly to showcase side profile and back..."
                    className="w-full rounded-ctl border border-line2 bg-panel2 p-2.5 text-[11.5px] font-mono text-fg focus:border-acc outline-none"
                  />
                </Field>
              </div>
            )}
          </Panel>

          {/* Action Trigger Buttons */}
          <div className="flex flex-col gap-2.5">
            <div className="grid grid-cols-2 gap-3">
              <Btn
                variant="ghost"
                icon={<Flask size={16} />}
                busy={busy}
                disabled={busy}
                onClick={() => executeWorkflow(true)}
                className="h-11 font-semibold"
                title="Kiểm tra pipeline và các công cụ local mà không tốn credit Google Flow"
              >
                <span>Chạy thử (Dry-run)</span>
                <span className="text-[10px] bg-line px-1.5 py-0.5 rounded text-mut font-mono">0 cr</span>
              </Btn>

              <Btn
                variant="primary"
                icon={<Sparkle size={16} weight="fill" />}
                busy={busy}
                disabled={busy}
                onClick={() => setConfirmModalOpen(true)}
                className="h-11 font-semibold"
                title="Thực hiện tạo ảnh và render video 16s thật trên Google Flow"
              >
                <span>Tạo ảnh & Video thật</span>
                <span className="text-[10px] bg-accink/20 px-1.5 py-0.5 rounded text-accink font-bold">~3 cr</span>
              </Btn>
            </div>

            <p className="text-[11px] text-center text-mut leading-tight">
              Dry-run giả lập mọi bước xử lý và trích xuất video để bạn yên tâm kiểm tra trước khi dùng credit thật.
            </p>
          </div>
        </div>

        {/* ================= RIGHT COLUMN: EXECUTION & RESULT VIEWER ================= */}
        <div className="flex flex-col gap-5 min-w-0">
          {/* Step-by-Step Progress Pipeline */}
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
                    <span>Đang xử lý bước {currentStep}/8</span>
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

            {/* 8 Steps Visual Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {STEPS.map((s) => {
                const isCurrent = busy && isTryOnJob && currentStep === s.id;
                const isDone = (busy && isTryOnJob && currentStep > s.id) || (isTryOnJob && activeJob?.state === "succeeded");

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

            {/* Live Job Console & Events (isolated to tryon jobs) */}
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
                  onClick={() => setResultTab("frames")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "frames" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  Frames & Video Con (8s + 8s)
                </button>
                <button
                  onClick={() => setResultTab("prompts")}
                  className={`px-3 py-1 text-[12px] font-semibold rounded-ctl transition-colors cursor-pointer ${
                    resultTab === "prompts" ? "bg-panel2 text-acc border border-line2" : "text-mut hover:text-fg"
                  }`}
                >
                  Prompts Đã Sinh
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
                        Kiểm tra các video con 8s ở tab "Frames & Video Con".
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: DETAILED FRAMES & SUB-VIDEOS */}
              {resultTab === "frames" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* First Frame Image */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <ImageIcon size={14} className="text-acc" />
                        <span>First Frame (Ảnh Google Flow)</span>
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
                        Không có ảnh
                      </div>
                    )}
                  </div>

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

                  {/* Last Frame Video 1 */}
                  <div className="flex flex-col gap-1.5 p-3 rounded-ctl bg-panel2 border border-line">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg flex items-center gap-1.5">
                        <ImageIcon size={14} className="text-ok" />
                        <span>Last Frame Video 1 (FFmpeg)</span>
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

              {/* TAB 3: PROMPTS */}
              {resultTab === "prompts" && (
                <div className="flex flex-col gap-3">
                  {/* Image Prompt */}
                  <div className="p-3 rounded-ctl bg-panel2 border border-line flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-acc">
                        Image Prompt (Gemini Nabi Studio)
                      </span>
                      <button
                        onClick={() => handleCopyPrompt(activeResult.image_prompt || "", "img")}
                        className="text-[11px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                      >
                        {copiedKey === "img" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                        <span>{copiedKey === "img" ? "Đã chép" : "Sao chép"}</span>
                      </button>
                    </div>
                    <p className="font-mono text-[11.5px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                      {activeResult.image_prompt || "(Chưa có dữ liệu prompt)"}
                    </p>
                  </div>

                  {/* Video Prompt 1 */}
                  <div className="p-3 rounded-ctl bg-panel2 border border-line flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-fg">
                        Video Prompt 1 (0-8s)
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
                      <span className="text-[12px] font-bold text-fg">
                        Video Prompt 2 (8-16s)
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
              <h4 className="text-[14px] font-semibold text-dim">Chưa có kết quả chạy nào được chọn</h4>
              <p className="text-[12px] text-mut max-w-[420px] mt-1.5 leading-relaxed">
                Sau khi bấm <strong>Chạy thử</strong> hoặc <strong>Tạo ảnh & Video thật</strong>, video 16s cùng hình ảnh các bước sẽ xuất hiện trực tiếp tại đây. Bạn cũng có thể xem lại lịch sử các lần chạy phía dưới.
              </p>
            </Panel>
          )}

          {/* ================= RUNS HISTORY ================= */}
          <Panel className="p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-[13px] font-bold text-fg">Lịch sử các lần chạy ({runs.length})</h3>
              </div>
              <button
                onClick={() => refreshRuns()}
                disabled={runsLoading}
                className="inline-flex items-center gap-1 text-[11.5px] text-mut hover:text-fg cursor-pointer transition-colors"
              >
                <ArrowClockwise size={13} className={runsLoading ? "animate-spin" : ""} />
                <span>Làm mới</span>
              </button>
            </div>

            {runs.length === 0 ? (
              <p className="text-[12px] text-mut py-3 text-center">Chưa có lịch sử lần chạy nào.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-[280px] overflow-y-auto slim-scroll pr-1">
                {runs.map((r) => {
                  const isSelected = activeResult?.run_id === r.run_id;
                  return (
                    <div
                      key={r.run_id}
                      onClick={() => setSelectedResultRun(r)}
                      className={`p-2.5 rounded-ctl border text-[11.5px] flex items-center gap-3 cursor-pointer transition-all ${
                        isSelected
                          ? "border-acc bg-acc/10"
                          : "border-line bg-panel2 hover:border-line2 hover:bg-panel2/80"
                      }`}
                    >
                      <div className="size-12 rounded-ctl overflow-hidden bg-black shrink-0 border border-line2 flex items-center justify-center">
                        {r.first_frame_url ? (
                          <img src={r.first_frame_url} alt="" className="size-full object-cover" />
                        ) : (
                          <VideoCamera size={18} className="text-mut" />
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-bold text-fg truncate">{r.run_id}</span>
                          {r.dry_run && (
                            <span className="px-1 py-0.2 rounded text-[9.5px] font-bold bg-line text-mut">
                              DRY
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-mut truncate mt-0.5">
                          {r.product_title || "Affiliate Try-on"}
                        </p>
                        <p className="text-[10px] text-dim font-mono mt-0.5">
                          {r.elapsed_s ? `${r.elapsed_s}s` : ""} · {r.status}
                        </p>
                      </div>

                      <Eye size={16} className="text-mut group-hover:text-fg shrink-0" />
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
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
                <span className="text-mut">First Frame (1 ảnh):</span>
                <span className="font-mono text-fg">~1 Flow Credit</span>
              </div>
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
                <span className="font-mono">~3 Credits</span>
              </div>
            </div>

            <p className="text-[11.5px] text-dim leading-relaxed">
              Video 16s sẽ được tự động trích xuất Last Frame và ghép nối bằng FFmpeg sau khi 2 video hoàn tất. Hãy đảm bảo tài khoản Google Flow của bạn còn đủ credit.
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
                Xác nhận chạy thật
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

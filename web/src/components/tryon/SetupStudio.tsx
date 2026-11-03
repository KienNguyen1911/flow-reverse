import { CheckCircle, MagicWand, SidebarSimple, Sparkle, UploadSimple, VideoCamera } from "@phosphor-icons/react";
import type { Project } from "../../types";
import { PRESETS_V1, PRESETS_V2 } from "./constants";
import type { TryOnForm } from "./useTryOnForm";
import type { ShowToast } from "./types";
import { formatBytes, sanitizePromptClient } from "./format";
import { Btn, Chip, Field, Panel, Spinner } from "../ui";

interface Props {
  form: TryOnForm;
  projects: Project[];
  isSingleMode: boolean;
  isCollapsed: boolean;
  onExpand: () => void;
  onOpenConfirm: () => void;
  showToast: ShowToast;
}

/** Left pane of the studio: first-frame upload, prompts, render options and the submit action (or its collapsed rail). */
export function SetupStudio({ form, projects, isSingleMode, isCollapsed, onExpand, onOpenConfirm, showToast }: Props) {
  const {
    firstFrame,
    setFirstFrame,
    firstFrameUploading,
    isDragging,
    setIsDragging,
    videoPrompt1,
    setVideoPrompt1,
    videoPrompt2,
    setVideoPrompt2,
    targetProjectId,
    setTargetProjectId,
    autoStitch,
    setAutoStitch,
    removeWatermark,
    setRemoveWatermark,
    aspectRatio,
    setAspectRatio,
    fileInputRef,
    handleUploadFile,
    handleUseSampleFirstFrame,
  } = form;

  return !isCollapsed ? (
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
          onClick={() => onOpenConfirm()}
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
        onClick={() => onExpand()}
        className="size-8 rounded-ctl bg-acc/10 text-acc grid place-items-center hover:bg-acc/20 cursor-pointer"
        title="Mở rộng bảng Setup Studio"
      >
        <SidebarSimple size={16} />
      </button>
      <div className="w-full border-t border-line2 my-1" />
      <button
        onClick={() => {
          onExpand();
          fileInputRef.current?.click();
        }}
        className="size-8 rounded-ctl border border-line2 text-dim hover:text-fg grid place-items-center cursor-pointer"
        title="Tải ảnh First Frame"
      >
        <UploadSimple size={15} />
      </button>
      <button
        onClick={() => onOpenConfirm()}
        className="size-8 rounded-ctl bg-acc text-accink font-bold grid place-items-center hover:bg-acc2 cursor-pointer"
        title="Tạo video thật"
      >
        <Sparkle size={15} weight="fill" />
      </button>
    </div>
  );
}

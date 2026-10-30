import { useEffect, useState } from "react";
import {
  ArrowSquareOut,
  Check,
  Copy,
  DownloadSimple,
  FilmSlate,
  Image as ImageIcon,
  Plus,
  Sparkle,
  X,
} from "@phosphor-icons/react";

export interface PreviewMediaItem {
  url: string;
  name: string;
  category: "image" | "video";
  prompt?: string | null;
  resolution?: string | [number, number] | null;
  aspect_ratio?: string | null;
  created_ts?: number | string | null;
  size_bytes?: number;
  duration_s?: number | null;
  seed?: number | null;
}

interface MediaPreviewModalProps {
  item: PreviewMediaItem | null;
  onClose: () => void;
  onInsertToCanvas?: (item: { url: string; name?: string; category?: "image" | "video" }) => void;
}

function fmtTime(ts?: number | string | null): string {
  if (!ts) return "";
  let d: Date;
  if (typeof ts === "number") {
    d = new Date(ts < 10000000000 ? ts * 1000 : ts);
  } else {
    d = new Date(ts);
    if (isNaN(d.getTime())) {
      const num = Number(ts);
      if (!isNaN(num)) d = new Date(num < 10000000000 ? num * 1000 : num);
    }
  }
  if (isNaN(d.getTime())) return String(ts);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function fmtBytes(b?: number): string {
  if (!b || b <= 0) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function cleanDisplayName(name: string): string {
  return name.replace(/^(\d{12,14})_/, "");
}

export function MediaPreviewModal({ item, onClose, onInsertToCanvas }: MediaPreviewModalProps) {
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  useEffect(() => {
    if (!item) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [item, onClose]);

  if (!item) return null;

  const isVideo = item.category === "video";
  const displayName = cleanDisplayName(item.name);
  const resolutionStr = item.resolution
    ? Array.isArray(item.resolution)
      ? `${item.resolution[0]} × ${item.resolution[1]}`
      : String(item.resolution)
    : item.aspect_ratio || null;

  const handleCopyPrompt = () => {
    if (!item.prompt) return;
    navigator.clipboard.writeText(item.prompt).then(() => {
      setCopiedPrompt(true);
      setTimeout(() => setCopiedPrompt(false), 2000);
    }).catch(() => void 0);
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(item.url).then(() => {
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }).catch(() => void 0);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 backdrop-blur-md p-3 sm:p-5 lg:p-7 pointer-events-auto select-none animate-in fade-in duration-150"
      onClick={onClose}
    >
      {/* 2-Column Inspector Container: 1 bên Preview, 1 bên Card Thông tin */}
      <div
        className="relative w-full h-full max-w-7xl max-h-[92vh] bg-panel border border-line2 rounded-2xl shadow-2xl overflow-hidden flex flex-col md:flex-row text-fg animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ===================== CỘT BÊN TRÁI: PREVIEW ẢNH / VIDEO ===================== */}
        <div className="flex-1 min-w-0 bg-[#0a0b0e] flex flex-col relative select-none">
          {/* Floating subtle top bar */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-line2/40 bg-ink/60 backdrop-blur-xs shrink-0 z-10">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-acc animate-pulse" />
              <span className="text-[11px] font-mono text-dim">
                {isVideo ? "Trình phát Video" : "Xem trước độ phân giải cao"}
              </span>
            </div>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-ctl border border-line2 bg-panel2/60 hover:bg-panel3 text-[11px] text-dim hover:text-fg transition-colors"
              title="Mở tệp gốc trong tab mới"
            >
              <ArrowSquareOut size={13} />
              <span>Mở tệp gốc</span>
            </a>
          </div>

          {/* Media Center Stage */}
          <div className="flex-1 min-h-0 flex items-center justify-center p-4 sm:p-6 relative overflow-hidden bg-[radial-gradient(#1e222d_1px,transparent_1px)] [background-size:16px_16px]">
            {isVideo ? (
              <video
                src={item.url}
                controls
                autoPlay
                loop
                playsInline
                className="max-h-full max-w-full rounded-xl shadow-2xl object-contain bg-black border border-line2/50"
              />
            ) : (
              <img
                src={item.url}
                alt={displayName}
                className="max-h-full max-w-full rounded-xl shadow-2xl object-contain select-none border border-line2/50"
              />
            )}
          </div>
        </div>

        {/* ===================== CỘT BÊN PHẢI: CARD THÔNG TIN ẢNH ===================== */}
        <div className="w-full md:w-[380px] lg:w-[420px] bg-panel2 border-t md:border-t-0 md:border-l border-line2 flex flex-col shrink-0">
          {/* Header */}
          <header className="flex items-center justify-between px-5 h-14 border-b border-line2 bg-panel shrink-0">
            <div className="flex items-center gap-2.5 min-w-0 pr-2">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10.5px] font-bold uppercase font-mono tracking-wider shrink-0 ${
                  isVideo
                    ? "bg-purple-500/20 text-purple-300 border border-purple-500/35"
                    : "bg-acc/15 text-acc border border-acc/35"
                }`}
              >
                {isVideo ? <FilmSlate size={12} weight="bold" /> : <ImageIcon size={12} weight="bold" />}
                <span>{item.category}</span>
              </span>
              <h3 className="text-[13px] font-bold text-fg truncate" title={displayName}>
                {displayName}
              </h3>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="size-8 grid place-items-center rounded-ctl border border-line2 bg-panel2 hover:bg-panel3 hover:text-fg text-mut transition-colors cursor-pointer shrink-0"
              title="Đóng (Esc)"
            >
              <X size={16} />
            </button>
          </header>

          {/* Scrollable Information Body */}
          <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 slim-scroll">
            {/* Card: Thông số chi tiết */}
            <div className="rounded-xl border border-line2 bg-panel p-3.5 space-y-2.5 shadow-xs">
              <span className="text-[10.5px] font-bold text-mut uppercase tracking-wider block font-mono">
                Thông số kỹ thuật
              </span>

              <div className="grid grid-cols-2 gap-2 text-[11.5px]">
                {resolutionStr && (
                  <div className="rounded-ctl border border-line2/70 bg-panel2 p-2">
                    <span className="text-[10px] text-mut block font-medium">Độ phân giải / Tỷ lệ</span>
                    <span className="font-mono font-semibold text-fg">{resolutionStr}</span>
                  </div>
                )}

                {item.size_bytes ? (
                  <div className="rounded-ctl border border-line2/70 bg-panel2 p-2">
                    <span className="text-[10px] text-mut block font-medium">Dung lượng</span>
                    <span className="font-mono font-semibold text-fg">{fmtBytes(item.size_bytes)}</span>
                  </div>
                ) : null}

                {item.duration_s ? (
                  <div className="rounded-ctl border border-line2/70 bg-panel2 p-2">
                    <span className="text-[10px] text-mut block font-medium">Thời lượng</span>
                    <span className="font-mono font-semibold text-fg">{item.duration_s}s</span>
                  </div>
                ) : null}

                {item.created_ts ? (
                  <div className="rounded-ctl border border-line2/70 bg-panel2 p-2 col-span-2">
                    <span className="text-[10px] text-mut block font-medium">Thời gian tạo</span>
                    <span className="font-mono text-dim">{fmtTime(item.created_ts)}</span>
                  </div>
                ) : null}

                {item.seed != null && (
                  <div className="rounded-ctl border border-line2/70 bg-panel2 p-2 col-span-2">
                    <span className="text-[10px] text-mut block font-medium">Seed</span>
                    <span className="font-mono text-fg">{item.seed}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Card: Câu lệnh Prompt */}
            <div className="rounded-xl border border-line2 bg-panel p-3.5 space-y-2 shadow-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Sparkle size={13} weight="fill" className="text-acc" />
                  <span className="text-[11px] font-bold text-fg">Câu lệnh Prompt</span>
                </div>
                {item.prompt && (
                  <button
                    type="button"
                    onClick={handleCopyPrompt}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-ctl border border-line2 bg-panel2 hover:bg-panel3 text-[10.5px] font-semibold text-dim hover:text-fg transition-colors cursor-pointer"
                    title="Sao chép toàn bộ prompt"
                  >
                    {copiedPrompt ? (
                      <>
                        <Check size={11} className="text-ok" weight="bold" />
                        <span className="text-ok">Đã chép!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={11} />
                        <span>Sao chép</span>
                      </>
                    )}
                  </button>
                )}
              </div>

              {item.prompt ? (
                <div className="rounded-ctl border border-line2/70 bg-ink/70 p-3 text-[11.5px] font-mono leading-relaxed text-dim/95 select-text break-words max-h-56 overflow-y-auto slim-scroll">
                  {item.prompt}
                </div>
              ) : (
                <div className="rounded-ctl border border-line2/60 bg-panel2/50 p-4 text-center text-mut text-[11.5px] italic">
                  Không có prompt cho tệp này (ảnh tải lên trực tiếp hoặc không sinh từ node prompt).
                </div>
              )}
            </div>
          </div>

          {/* Card Actions Footer */}
          <footer className="p-4 border-t border-line2 bg-panel flex flex-col gap-2 shrink-0">
            {onInsertToCanvas && (
              <button
                type="button"
                onClick={() => {
                  onInsertToCanvas({
                    url: item.url,
                    name: item.prompt || displayName,
                    category: item.category,
                  });
                  onClose();
                }}
                className="w-full h-9 rounded-ctl bg-acc text-accink text-[12px] font-bold hover:bg-acc2 transition-colors flex items-center justify-center gap-1.5 cursor-pointer shadow-sm shadow-acc/10"
              >
                <Plus size={14} weight="bold" />
                <span>Thêm vào Canvas</span>
              </button>
            )}

            <div className="flex items-center gap-2">
              <a
                href={item.url}
                download={item.name}
                className="flex-1 h-8 rounded-ctl border border-line2 bg-panel2 hover:bg-panel3 text-[11.5px] font-semibold text-fg transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                title="Tải tệp về máy"
              >
                <DownloadSimple size={13} />
                <span>Tải về</span>
              </a>

              <button
                type="button"
                onClick={handleCopyUrl}
                className="flex-1 h-8 rounded-ctl border border-line2 bg-panel2 hover:bg-panel3 text-[11.5px] font-semibold text-dim hover:text-fg transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                title="Sao chép đường dẫn URL"
              >
                {copiedUrl ? (
                  <>
                    <Check size={12} className="text-ok" weight="bold" />
                    <span className="text-ok">Đã sao chép</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>Sao chép Link</span>
                  </>
                )}
              </button>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}

import { Check, Copy, CornersOut, DownloadSimple, Image as ImageIcon, Play, Plus, PushPin, Trash, VideoCamera } from "@phosphor-icons/react";
import type { AssetOutputItem, AssetUploadedItem } from "../../types";
import { cleanDisplayName, fmtBytes, fmtTime } from "./format";

/** Draggable thumbnail card for an uploaded image (pin, insert, preview, copy link, delete). */
export function UploadedCard({
  item,
  isPinned,
  isCopied,
  showProjectBadge,
  onTogglePin,
  onInsert,
  onPreview,
  onCopyUrl,
  onDelete,
}: {
  item: AssetUploadedItem;
  isPinned: boolean;
  isCopied: boolean;
  showProjectBadge?: boolean;
  onTogglePin: (e: React.MouseEvent) => void;
  onInsert: () => void;
  onPreview: () => void;
  onCopyUrl: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const displayName = cleanDisplayName(item.name);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(
          "application/flow-asset",
          JSON.stringify({ url: item.url, name: item.name, category: "image" }),
        );
        e.dataTransfer.setData("text/plain", item.url);
      }}
      onClick={onPreview}
      className={`group relative rounded-panel border overflow-hidden bg-panel transition-all duration-150 cursor-pointer flex flex-col hover:shadow-lg ${
        isPinned
          ? "border-acc/60 bg-acc/5 ring-1 ring-acc/30"
          : "border-line2/80 hover:border-acc/50"
      }`}
    >
      {/* Pin badge / action button */}
      <button
        type="button"
        onClick={onTogglePin}
        className={`absolute top-1.5 right-1.5 z-10 size-6 rounded-full grid place-items-center transition-all cursor-pointer ${
          isPinned
            ? "bg-acc text-accink shadow-xs"
            : "bg-black/60 text-white/70 opacity-0 group-hover:opacity-100 hover:text-white hover:bg-black/80"
        }`}
        title={isPinned ? "Bỏ ghim ảnh này" : "Ghim ảnh này lên đầu"}
      >
        <PushPin size={11} weight={isPinned ? "fill" : "bold"} />
      </button>

      {/* Thumbnail area */}
      <div className="aspect-[4/3] bg-ink relative overflow-hidden flex items-center justify-center">
        <img
          src={item.url}
          alt={displayName}
          loading="lazy"
          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
        />

        {showProjectBadge && item.projectName && (
          <span
            className="absolute bottom-1.5 left-1.5 max-w-[85%] truncate px-1.5 py-0.5 rounded bg-black/65 text-[8.5px] font-semibold text-white/85 border border-white/10"
            title={`Project: ${item.projectName}`}
          >
            📁 {item.projectName}
          </span>
        )}

        {/* Hover action overlay */}
        <div className="absolute inset-0 bg-black/55 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5 p-2">
          {/* Quick Insert to Canvas */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onInsert();
            }}
            className="size-7 rounded-full bg-acc text-accink grid place-items-center hover:bg-acc2 transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title="Thêm vào Canvas"
          >
            <Plus size={14} weight="bold" />
          </button>

          {/* Preview */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onPreview();
            }}
            className="size-7 rounded-full bg-white/20 hover:bg-white/30 text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title="Xem ảnh phóng to"
          >
            <CornersOut size={13} />
          </button>

          {/* Copy URL */}
          <button
            type="button"
            onClick={onCopyUrl}
            className="size-7 rounded-full bg-white/20 hover:bg-white/30 text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title={isCopied ? "Đã sao chép link!" : "Sao chép liên kết"}
          >
            {isCopied ? <Check size={13} className="text-acc" /> : <Copy size={13} />}
          </button>

          {/* Delete */}
          <button
            type="button"
            onClick={onDelete}
            className="size-7 rounded-full bg-err/30 hover:bg-err/50 text-err hover:text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title="Xóa ảnh này"
          >
            <Trash size={12} />
          </button>
        </div>
      </div>

      {/* Metadata footer */}
      <div className="p-2 flex flex-col gap-0.5">
        <p className="text-[11px] font-medium text-fg truncate" title={displayName}>
          {displayName}
        </p>
        <div className="flex items-center justify-between text-[9.5px] font-mono text-mut">
          <span>{fmtTime(item.created_ts)}</span>
          {item.size_bytes ? <span>{fmtBytes(item.size_bytes)}</span> : null}
        </div>
      </div>
    </div>
  );
}

/** Draggable thumbnail card for a generated image/video (pin, insert, preview, copy link, download). */
export function OutputCard({
  item,
  isPinned,
  isCopied,
  showProjectBadge,
  onTogglePin,
  onInsert,
  onPreview,
  onCopyUrl,
}: {
  item: AssetOutputItem;
  isPinned: boolean;
  isCopied: boolean;
  showProjectBadge?: boolean;
  onTogglePin: (e: React.MouseEvent) => void;
  onInsert: () => void;
  onPreview: () => void;
  onCopyUrl: (e: React.MouseEvent) => void;
}) {
  const isVideo = item.category === "video";
  const thumbUrl = item.thumbnail_url || item.url;
  const promptText = item.prompt || cleanDisplayName(item.name);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(
          "application/flow-asset",
          JSON.stringify({ url: item.url, name: item.prompt || item.name, category: item.category }),
        );
        e.dataTransfer.setData("text/plain", item.url);
      }}
      onClick={onPreview}
      className={`group relative rounded-panel border overflow-hidden bg-panel transition-all duration-150 cursor-pointer flex flex-col hover:shadow-lg ${
        isPinned ? "border-acc/60 bg-acc/5 ring-1 ring-acc/30" : "border-line2/80 hover:border-acc/60"
      }`}
    >
      {/* Pin toggle */}
      <button
        type="button"
        onClick={onTogglePin}
        className={`absolute top-1.5 right-1.5 z-10 size-6 rounded-full grid place-items-center transition-all cursor-pointer ${
          isPinned
            ? "bg-acc text-accink shadow-xs"
            : "bg-black/60 text-white/70 opacity-0 group-hover:opacity-100 hover:text-white hover:bg-black/80"
        }`}
        title={isPinned ? "Bỏ ghim kết quả này" : "Ghim kết quả này (hiện ở mọi project)"}
      >
        <PushPin size={11} weight={isPinned ? "fill" : "bold"} />
      </button>

      {/* Category badge */}
      <div className="absolute top-1.5 left-1.5 z-10">
        <span
          className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase font-mono flex items-center gap-1 shadow-xs ${
            isVideo
              ? "bg-purple-900/80 text-purple-200 border border-purple-500/40"
              : "bg-blue-900/80 text-blue-200 border border-blue-500/40"
          }`}
        >
          {isVideo ? <VideoCamera size={10} weight="fill" /> : <ImageIcon size={10} />}
          <span>{isVideo ? (item.duration_s ? `${item.duration_s}s` : "Video") : "Ảnh"}</span>
        </span>
      </div>

      {/* Thumbnail area */}
      <div className="aspect-[4/3] bg-ink relative overflow-hidden flex items-center justify-center">
        {isVideo && !item.thumbnail_url ? (
          <video
            src={item.url}
            muted
            preload="metadata"
            className="w-full h-full object-cover"
          />
        ) : (
          <img
            src={thumbUrl}
            alt={item.name}
            loading="lazy"
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
          />
        )}

        {/* Video Play overlay icon */}
        {isVideo && (
          <div className="absolute inset-0 grid place-items-center pointer-events-none group-hover:opacity-0 transition-opacity">
            <div className="size-8 rounded-full bg-black/60 backdrop-blur-xs grid place-items-center text-white/90 shadow-md">
              <Play size={14} weight="fill" className="ml-0.5" />
            </div>
          </div>
        )}

        {showProjectBadge && item.projectName && (
          <span
            className="absolute bottom-1.5 left-1.5 max-w-[85%] truncate px-1.5 py-0.5 rounded bg-black/65 text-[8.5px] font-semibold text-white/85 border border-white/10"
            title={`Project: ${item.projectName}`}
          >
            📁 {item.projectName}
          </span>
        )}

        {/* Hover action overlay */}
        <div className="absolute inset-0 bg-black/55 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5 p-2">
          {/* Quick Insert to Canvas */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onInsert();
            }}
            className="size-7 rounded-full bg-acc text-accink grid place-items-center hover:bg-acc2 transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title="Thêm vào Canvas"
          >
            <Plus size={14} weight="bold" />
          </button>

          {/* Preview / Play */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onPreview();
            }}
            className="size-7 rounded-full bg-white/20 hover:bg-white/30 text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title={isVideo ? "Xem video" : "Xem ảnh phóng to"}
          >
            {isVideo ? <Play size={12} weight="fill" /> : <CornersOut size={13} />}
          </button>

          {/* Copy URL */}
          <button
            type="button"
            onClick={onCopyUrl}
            className="size-7 rounded-full bg-white/20 hover:bg-white/30 text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title={isCopied ? "Đã sao chép link!" : "Sao chép liên kết"}
          >
            {isCopied ? <Check size={13} className="text-acc" /> : <Copy size={13} />}
          </button>

          {/* Direct Download */}
          <a
            href={item.url}
            download={item.name}
            onClick={(e) => e.stopPropagation()}
            className="size-7 rounded-full bg-white/20 hover:bg-white/30 text-white grid place-items-center transition-transform hover:scale-110 active:scale-95 shadow-md cursor-pointer"
            title="Tải về"
          >
            <DownloadSimple size={13} />
          </a>
        </div>
      </div>

      {/* Metadata footer */}
      <div className="p-2 flex flex-col gap-1">
        <p className="text-[10.5px] leading-snug text-dim line-clamp-2" title={promptText}>
          {promptText}
        </p>
        <div className="flex items-center justify-between text-[9px] font-mono text-mut">
          <span>{fmtTime(item.created_ts)}</span>
          {item.resolution ? (
            <span>
              {Array.isArray(item.resolution)
                ? `${item.resolution[0]}x${item.resolution[1]}`
                : item.resolution}
            </span>
          ) : isVideo && item.duration_s ? (
            <span>{item.duration_s}s</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

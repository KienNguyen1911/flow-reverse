import { useState } from "react";
import { ArrowsOut, DownloadSimple } from "@phosphor-icons/react";
import type { PreviewMediaItem } from "../../MediaPreviewModal";
import type { CanvasNode } from "../types";

/**
 * Result Preview — với Node Video, Video và Ảnh khung dùng chung MỘT khung
 * có tab chuyển đổi nhỏ, thay vì hai khung xếp dọc (giảm nửa chiều cao).
 * Chỉ render khi thực sự có media: một <video> rỗng vẫn chiếm 300×150 và
 * hiện khung đen "0:00" — đó là lỗi UI khi node chưa có kết quả.
 */
export function NodeResultPreview({
  n,
  onPreviewMedia,
}: {
  n: CanvasNode;
  onPreviewMedia?: (item: PreviewMediaItem) => void;
}) {
  const isImg = n.type === "image";
  const isVid = n.type === "video";
  const isLastFrame = n.type === "last_frame";

  const [mediaTab, setMediaTab] = useState<"video" | "frame">("video");
  /** URL đã 404/không giải mã được — ẩn khung thay vì hiện icon ảnh hỏng. */
  const [brokenMedia, setBrokenMedia] = useState<Record<string, boolean>>({});
  const markBroken = (url?: string | null) => {
    if (!url) return;
    setBrokenMedia((cur) => (cur[url] ? cur : { ...cur, [url]: true }));
  };

  const hasImage = !!(n.fileUrl && (isImg || isLastFrame) && !brokenMedia[n.fileUrl]);
  const hasVideo = isVid && !!n.videoUrl && !brokenMedia[n.videoUrl];
  const hasFrame = isVid && !!n.frameUrl && !brokenMedia[n.frameUrl];
  const showVideo = hasVideo && (mediaTab === "video" || !hasFrame);
  if (!hasImage && !hasVideo && !hasFrame) return null;
  return (
    <div className="rounded-ctl overflow-hidden border border-line2 bg-panel2 relative group">
      {hasVideo && hasFrame && (
        <div className="absolute top-1.5 left-1.5 z-10 flex items-center gap-0.5 rounded-full border border-line2 bg-ink/85 p-0.5 backdrop-blur-sm">
          {([
            { key: "video", label: "Video" },
            { key: "frame", label: "Ảnh khung" },
          ] as const).map((tb) => (
            <button
              key={tb.key}
              type="button"
              onClick={() => setMediaTab(tb.key)}
              className={`h-[18px] px-1.5 rounded-full text-[9px] font-bold transition-colors cursor-pointer ${
                mediaTab === tb.key ? "bg-acc text-accink" : "text-dim hover:text-fg"
              }`}
            >
              {tb.label}
            </button>
          ))}
        </div>
      )}
      {hasImage ? (
        <img
          src={n.fileUrl!}
          alt="Kết quả"
          onError={() => markBroken(n.fileUrl)}
          className="w-full max-h-40 object-contain cursor-pointer hover:opacity-95 transition-opacity"
          onClick={() =>
            onPreviewMedia?.({
              url: n.fileUrl!,
              name: n.label || (isImg ? "Node Ảnh" : "Frame Cuối"),
              category: "image",
              prompt: n.prompt,
              resolution: n.aspectRatio,
              aspect_ratio: n.aspectRatio,
              seed: n.seed,
            })
          }
          title="Bấm để xem ảnh to với kích thước đầy đủ"
        />
      ) : showVideo ? (
        <video
          src={n.videoUrl!}
          controls
          onError={() => markBroken(n.videoUrl)}
          className="w-full max-h-40"
        />
      ) : (
        <img
          src={n.frameUrl!}
          alt="Ảnh khung"
          onError={() => markBroken(n.frameUrl)}
          className="w-full max-h-40 object-contain cursor-pointer hover:opacity-95 transition-opacity bg-ink/40"
          onClick={() =>
            onPreviewMedia?.({
              url: n.frameUrl!,
              name: `${n.label || "Video"} - Khung hình (First Frame)`,
              category: "image",
            })
          }
          title="Ảnh khung đã dùng / tự tạo — bấm để xem to"
        />
      )}
      <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
        <button
          type="button"
          onClick={() =>
            onPreviewMedia?.({
              url: showVideo ? n.videoUrl! : hasImage ? n.fileUrl! : n.frameUrl!,
              name: n.label || (isImg ? "Node Ảnh" : isVid ? "Node Video" : "Frame Cuối"),
              category: showVideo ? "video" : "image",
              prompt: n.prompt,
              resolution: isVid ? n.resolution : n.aspectRatio,
              aspect_ratio: isVid ? n.videoRatio : n.aspectRatio,
              seed: n.seed,
              duration_s: showVideo ? 8 : undefined,
            })
          }
          className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
          title="Xem ảnh to / phóng to chi tiết"
        >
          <ArrowsOut size={13} weight="bold" />
        </button>
        <a
          href={showVideo ? n.videoUrl! : hasImage ? n.fileUrl! : n.frameUrl!}
          download
          className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
          title="Tải xuống"
        >
          <DownloadSimple size={13} />
        </a>
      </div>
    </div>
  );
}

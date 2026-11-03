import { DownloadSimple } from "@phosphor-icons/react";
import type { CanvasDrawerNode } from "./types";

/** Result tab: plays the generated video or shows the generated image with a download link. */
export function PreviewTab({ node }: { node: CanvasDrawerNode }) {
  return (
    <div className="flex flex-col gap-3">
      {node.type === "video" && node.videoUrl ? (
        <div className="rounded-panel border border-line2 bg-panel2 overflow-hidden">
          <video src={node.videoUrl} controls autoPlay loop className="w-full max-h-[360px]" />
          <div className="p-3 flex items-center justify-between border-t border-line2">
            <span className="text-[11px] font-mono text-mut truncate">{node.videoUrl}</span>
            <a
              href={node.videoUrl}
              download
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[11px] cursor-pointer"
            >
              <DownloadSimple size={13} />
              <span>Tải video</span>
            </a>
          </div>
        </div>
      ) : node.fileUrl ? (
        <div className="rounded-panel border border-line2 bg-panel2 overflow-hidden">
          <img
            src={node.fileUrl}
            alt="Kết quả"
            className="w-full max-h-[360px] object-contain bg-black/20"
          />
          <div className="p-3 flex items-center justify-between border-t border-line2">
            <span className="text-[11px] font-mono text-mut truncate">{node.fileUrl}</span>
            <a
              href={node.fileUrl}
              download
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[11px] cursor-pointer"
            >
              <DownloadSimple size={13} />
              <span>Tải ảnh</span>
            </a>
          </div>
        </div>
      ) : (
        <div className="grid place-items-center h-32 text-mut text-center">
          <span className="text-[11.5px]">Chưa có kết quả để hiển thị.</span>
        </div>
      )}
    </div>
  );
}

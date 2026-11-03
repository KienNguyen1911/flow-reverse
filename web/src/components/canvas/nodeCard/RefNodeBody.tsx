import { useRef, useState } from "react";
import { ArrowsOut, UploadSimple } from "@phosphor-icons/react";
import { Spinner } from "../../ui";
import type { PreviewMediaItem } from "../../MediaPreviewModal";
import type { CanvasNode } from "../types";

/** Reference-image node: click / drop an image to upload it. */
export function RefNodeBody({
  n,
  onUpload,
  onPreviewMedia,
}: {
  n: CanvasNode;
  onUpload: (file: File) => void;
  onPreviewMedia?: (item: PreviewMediaItem) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const pickFile = (f?: File | null) => {
    if (f) onUpload(f);
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          pickFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setDragOver(false);
          pickFile(e.dataTransfer.files?.[0]);
        }}
        className={`rounded-ctl border border-dashed bg-panel2 overflow-hidden transition-colors relative group ${
          dragOver ? "border-acc bg-acc/10" : "border-line2 hover:border-acc/60"
        }`}
      >
        {n.fileUrl ? (
          <>
            <img
              src={n.fileUrl}
              alt="Ảnh tham chiếu"
              onClick={() => fileInputRef.current?.click()}
              className="w-full max-h-44 object-contain cursor-pointer hover:opacity-95 transition-opacity"
              title="Bấm để thay đổi ảnh"
            />
            <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onPreviewMedia?.({
                    url: n.fileUrl!,
                    name: n.fileName || n.label || "Ảnh tham chiếu",
                    category: "image",
                  });
                }}
                className="grid place-items-center size-7 rounded-ctl bg-ink/80 border border-line2 text-dim hover:text-acc cursor-pointer shadow-sm transition-colors"
                title="Xem ảnh to"
              >
                <ArrowsOut size={13} weight="bold" />
              </button>
            </div>
          </>
        ) : (
          <div
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-col items-center gap-1.5 py-7 text-mut cursor-pointer"
            title="Bấm hoặc kéo-thả ảnh vào đây"
          >
            {n.status === "queued" ? <Spinner size={18} /> : <UploadSimple size={22} />}
            <span className="text-[11px] font-medium">
              {n.status === "queued" ? "Đang upload…" : "Bấm hoặc kéo-thả ảnh"}
            </span>
            <span className="text-[10px]">PNG / JPG / WebP</span>
          </div>
        )}
      </div>
      {n.fileUrl && (
        <p className="text-[10px] text-mut truncate" title={n.fileName ?? ""}>
          {n.fileName ?? "ảnh đã upload"} — bấm ảnh để thay
        </p>
      )}
    </>
  );
}

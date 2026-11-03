import { useEffect, useRef, useState } from "react";
import {
  ArrowsCounterClockwise,
  FolderSimple,
  PushPin,
  UploadSimple,
  FilmSlate,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { AssetOutputItem, AssetUploadedItem } from "../types";
import { Spinner } from "./ui";
import { MediaPreviewModal, type PreviewMediaItem } from "./MediaPreviewModal";
import { cleanDisplayName } from "./asset-drawer/format";
import { OutputTab } from "./asset-drawer/OutputTab";
import { UploadedTab } from "./asset-drawer/UploadedTab";
import { useAssetFilters } from "./asset-drawer/useAssetFilters";

export interface AssetDrawerProps {
  open: boolean;
  onClose: () => void;
  uploaded: AssetUploadedItem[];
  outputs: AssetOutputItem[];
  loadingUploaded: boolean;
  loadingOutputs: boolean;
  onRefreshUploaded: () => void;
  onRefreshOutputs: () => void;
  onInsertToCanvas: (item: { url: string; name?: string; category?: "image" | "video" }) => void;
  /** Active workspace project used to bind new uploads. */
  projectId?: string | null;
  activeProjectName?: string | null;
  scope: "project" | "all";
  onScopeChange: (scope: "project" | "all") => void;
  onTogglePin: (
    item: AssetUploadedItem | AssetOutputItem,
    pinned: boolean,
    kind: "upload" | "output" | "gallery",
  ) => void;
}

export function AssetDrawer({
  open,
  onClose,
  uploaded,
  outputs,
  loadingUploaded,
  loadingOutputs,
  onRefreshUploaded,
  onRefreshOutputs,
  onInsertToCanvas,
  projectId,
  activeProjectName,
  scope,
  onScopeChange,
  onTogglePin,
}: AssetDrawerProps) {
  // Tab state: "uploaded" vs "output"
  const [activeTab, setActiveTab] = useState<"uploaded" | "output">("uploaded");

  // Uploading state inside drawer
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Copied indicator
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Preview modal for image / video
  const [previewItem, setPreviewItem] = useState<PreviewMediaItem | null>(null);

  const filters = useAssetFilters(uploaded, outputs);
  const { pinnedCount } = filters;

  // Keyboard shortcut: Escape to close
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (previewItem) {
          setPreviewItem(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose, previewItem]);

  // Toggle pin (server-side so pins follow the asset across projects)
  const handleTogglePin = (
    item: AssetUploadedItem | AssetOutputItem,
    pinned: boolean,
    e?: React.MouseEvent,
  ) => {
    e?.stopPropagation();
    const key = item.key || "";
    const kind: "upload" | "output" | "gallery" = key.startsWith("gallery:")
      ? "gallery"
      : key.startsWith("output:") || "run_id" in item
        ? "output"
        : "upload";
    onTogglePin(item, !pinned, kind);
  };

  // Copy URL to clipboard
  const handleCopyUrl = (url: string, id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const fullUrl = url.startsWith("http") ? url : `${window.location.origin}${url}`;
    void navigator.clipboard.writeText(fullUrl);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  // Delete uploaded file
  const handleDeleteUploaded = async (item: AssetUploadedItem, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!window.confirm(`Xóa ảnh "${cleanDisplayName(item.name)}"?`)) return;
    try {
      await api.deleteUploadedAsset(item.name);
      onRefreshUploaded();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Xóa thất bại");
    }
  };

  // Handle direct file upload inside drawer
  const handleFileUpload = async (files: FileList | File[]) => {
    const file = files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setUploadError("Chỉ hỗ trợ file ảnh (.png, .jpg, .jpeg, .webp)");
      return;
    }
    setIsUploading(true);
    setUploadError(null);
    try {
      await api.upload(file, projectId ?? null);
      onRefreshUploaded();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Tải lên thất bại");
    } finally {
      setIsUploading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden pointer-events-none select-none">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px] pointer-events-auto transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Left Drawer Panel */}
      <aside className="absolute top-0 bottom-0 left-0 w-[420px] max-w-[92vw] bg-panel border-r border-line2 shadow-2xl flex flex-col pointer-events-auto animate-in slide-in-from-left duration-250 ease-out z-10 text-fg">
        {/* Drawer Header */}
        <header className="flex items-center justify-between px-4 h-14 border-b border-line2 bg-panel2/90 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="size-7 rounded-[7px] bg-acc/15 border border-acc/35 grid place-items-center text-acc shadow-sm shadow-acc/10">
              <FolderSimple size={16} weight="fill" />
            </div>
            <div>
              <h2 className="text-[13.5px] font-bold tracking-tight text-fg flex items-center gap-2">
                Kho Assets
                <span className="text-[11px] font-mono text-mut font-normal">
                  ({uploaded.length + outputs.length})
                </span>
              </h2>
              <p className="text-[10px] text-mut font-medium">
                {scope === "project" ? `📁 ${activeProjectName || "Project này"}` : "🌐 Tất cả project"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Refresh button with text and icon */}
            <button
              type="button"
              onClick={() => {
                onRefreshUploaded();
                onRefreshOutputs();
              }}
              disabled={loadingUploaded || loadingOutputs}
              className="inline-flex items-center gap-1.5 px-2.5 h-8 rounded-ctl border border-line2 bg-panel hover:bg-panel3 text-fg hover:border-acc/50 text-[11px] font-semibold transition-colors cursor-pointer disabled:opacity-40"
              title="Làm mới toàn bộ ảnh đã tải lên & kết quả sinh"
            >
              <ArrowsCounterClockwise
                size={13}
                className={loadingUploaded || loadingOutputs ? "animate-spin text-acc" : "text-acc"}
              />
              <span>Làm mới</span>
            </button>

            {/* Quick Upload button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="inline-flex items-center gap-1 px-2.5 h-8 rounded-ctl bg-acc/15 border border-acc/40 text-acc text-[11px] font-bold hover:bg-acc/25 transition-colors cursor-pointer"
              title="Tải ảnh mới từ máy tính"
            >
              {isUploading ? <Spinner size={12} /> : <UploadSimple size={13} weight="bold" />}
              <span>Tải lên</span>
            </button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) void handleFileUpload(e.target.files);
                e.target.value = "";
              }}
            />

            {/* Close button */}
            <button
              type="button"
              onClick={onClose}
              className="size-8 grid place-items-center rounded-ctl border border-transparent hover:border-line2 hover:bg-panel3 text-mut hover:text-fg transition-colors cursor-pointer"
              title="Đóng (Esc)"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {/* 2 Main Tabs: Uploaded vs Output */}
        <div className="flex border-b border-line2 bg-panel shrink-0 px-3 pt-2 gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("uploaded")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 text-[12px] font-bold rounded-t-ctl border-b-2 transition-all cursor-pointer ${
              activeTab === "uploaded"
                ? "border-acc text-acc bg-acc/5"
                : "border-transparent text-dim hover:text-fg hover:bg-panel2"
            }`}
          >
            <UploadSimple size={14} weight={activeTab === "uploaded" ? "bold" : "regular"} />
            <span>Đã tải lên</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                activeTab === "uploaded"
                  ? "bg-acc/20 text-acc"
                  : "bg-line2 text-mut"
              }`}
            >
              {uploaded.length}
            </span>
            {pinnedCount > 0 && (
              <span className="text-[10px] text-acc flex items-center gap-0.5" title={`${pinnedCount} asset đã ghim (hiển thị ở mọi project)`}>
                <PushPin size={10} weight="fill" />
                <span>{pinnedCount}</span>
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("output")}
            className={`flex-1 flex items-center justify-center gap-2 py-2 text-[12px] font-bold rounded-t-ctl border-b-2 transition-all cursor-pointer ${
              activeTab === "output"
                ? "border-acc text-acc bg-acc/5"
                : "border-transparent text-dim hover:text-fg hover:bg-panel2"
            }`}
          >
            <FilmSlate size={14} weight={activeTab === "output" ? "bold" : "regular"} />
            <span>Kết quả sinh</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                activeTab === "output"
                  ? "bg-acc/20 text-acc"
                  : "bg-line2 text-mut"
              }`}
            >
              {outputs.length}
            </span>
          </button>
        </div>

        {/* Project scope toggle */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-line2 bg-panel shrink-0">
          <span className="text-[9.5px] uppercase font-mono tracking-wider text-mut shrink-0">Phạm vi</span>
          <div className="flex flex-1 items-center gap-0.5 rounded-ctl border border-line2 bg-panel2 p-0.5">
            <button
              type="button"
              onClick={() => onScopeChange("project")}
              className={`flex-1 flex items-center justify-center gap-1 py-1 rounded-[5px] text-[10.5px] font-bold transition-colors cursor-pointer ${
                scope === "project"
                  ? "bg-acc text-accink shadow-xs"
                  : "text-dim hover:text-fg hover:bg-panel"
              }`}
              title="Chỉ hiện assets của project đang mở (asset đã ghim vẫn hiện)"
            >
              📁 Project này
            </button>
            <button
              type="button"
              onClick={() => onScopeChange("all")}
              className={`flex-1 flex items-center justify-center gap-1 py-1 rounded-[5px] text-[10.5px] font-bold transition-colors cursor-pointer ${
                scope === "all"
                  ? "bg-acc text-accink shadow-xs"
                  : "text-dim hover:text-fg hover:bg-panel"
              }`}
              title="Hiện assets của tất cả project"
            >
              🌐 Tất cả Project
            </button>
          </div>
        </div>

        {/* TAB 1: UPLOADED */}
        {activeTab === "uploaded" && (
          <UploadedTab
            filters={filters}
            uploaded={uploaded}
            loading={loadingUploaded}
            uploadError={uploadError}
            onClearUploadError={() => setUploadError(null)}
            onFiles={handleFileUpload}
            onBrowse={() => fileInputRef.current?.click()}
            copiedId={copiedId}
            scope={scope}
            onTogglePin={handleTogglePin}
            onCopyUrl={handleCopyUrl}
            onDeleteUploaded={handleDeleteUploaded}
            onInsertToCanvas={onInsertToCanvas}
            onPreview={setPreviewItem}
          />
        )}

        {/* TAB 2: OUTPUT */}
        {activeTab === "output" && (
          <OutputTab
            filters={filters}
            outputs={outputs}
            loading={loadingOutputs}
            copiedId={copiedId}
            scope={scope}
            onTogglePin={handleTogglePin}
            onCopyUrl={handleCopyUrl}
            onInsertToCanvas={onInsertToCanvas}
            onPreview={setPreviewItem}
          />
        )}

        {/* Footer / Drag-Drop tip */}
        <footer className="p-2.5 border-t border-line2 bg-panel2/60 text-center shrink-0">
          <p className="text-[10px] text-mut">
            <span className="font-semibold text-dim">Mẹo:</span> Kéo thả trực tiếp ảnh từ bảng này vào Canvas để thêm node tham chiếu.
          </p>
        </footer>
      </aside>

      {/* Full-view Lightbox / Video Modal */}
      <MediaPreviewModal
        item={previewItem}
        onClose={() => setPreviewItem(null)}
        onInsertToCanvas={onInsertToCanvas}
      />
    </div>
  );
}

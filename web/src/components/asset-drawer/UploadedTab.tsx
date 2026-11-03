import { Image as ImageIcon, MagnifyingGlass, PushPin, SortAscending, SortDescending, UploadSimple, X } from "@phosphor-icons/react";
import type { AssetOutputItem, AssetUploadedItem } from "../../types";
import type { AssetDrawerProps } from "../AssetDrawer";
import type { PreviewMediaItem } from "../MediaPreviewModal";
import { UploadedCard } from "./AssetCards";
import type { AssetFilters } from "./useAssetFilters";
import { Spinner } from "../ui";

interface Props {
  filters: AssetFilters;
  uploaded: AssetUploadedItem[];
  loading: boolean;
  uploadError: string | null;
  onClearUploadError: () => void;
  onFiles: (files: FileList | File[]) => Promise<void>;
  onBrowse: () => void;
  copiedId: string | null;
  scope: "project" | "all";
  onTogglePin: (item: AssetUploadedItem | AssetOutputItem, pinned: boolean, e?: React.MouseEvent) => void;
  onCopyUrl: (url: string, id: string, e?: React.MouseEvent) => void;
  onDeleteUploaded: (item: AssetUploadedItem, e?: React.MouseEvent) => Promise<void>;
  onInsertToCanvas: AssetDrawerProps["onInsertToCanvas"];
  onPreview: (item: PreviewMediaItem) => void;
}

/** "Đã tải lên" tab: search + sort bar, upload dropzone/error banner and the pinned/regular card grids. */
export function UploadedTab({
  filters,
  uploaded,
  loading,
  uploadError,
  onClearUploadError,
  onFiles,
  onBrowse,
  copiedId,
  scope,
  onTogglePin,
  onCopyUrl,
  onDeleteUploaded,
  onInsertToCanvas,
  onPreview,
}: Props) {
  const { searchUpload, setSearchUpload, uploadSort, setUploadSort, processedUploaded, pinnedCount } = filters;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Filter & Sort Bar */}
      <div className="p-3 border-b border-line2/70 bg-panel2/50 flex flex-col gap-2 shrink-0">
        {/* Search input */}
        <div className="relative">
          <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mut pointer-events-none" />
          <input
            type="text"
            value={searchUpload}
            onChange={(e) => setSearchUpload(e.target.value)}
            placeholder="Tìm kiếm ảnh đã tải lên..."
            className="w-full h-8 pl-8 pr-7 rounded-ctl border border-line2 bg-panel text-[11.5px] text-fg placeholder:text-mut focus:outline-none focus:border-acc/70"
          />
          {searchUpload && (
            <button
              type="button"
              onClick={() => setSearchUpload("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-mut hover:text-fg"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Controls row: Sort by time + Upload Dropzone Hint */}
        <div className="flex items-center justify-between text-[11px] text-mut">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-mut">Sắp xếp:</span>
            <button
              type="button"
              onClick={() => setUploadSort((s) => (s === "newest" ? "oldest" : "newest"))}
              className="inline-flex items-center gap-1 px-2 h-6 rounded-ctl border border-line2 bg-panel text-[10.5px] font-medium text-dim hover:text-fg hover:border-mut/60 transition-colors cursor-pointer"
              title="Đổi thứ tự sắp xếp thời gian"
            >
              {uploadSort === "newest" ? (
                <>
                  <SortDescending size={12} className="text-acc" />
                  <span>Mới nhất trước</span>
                </>
              ) : (
                <>
                  <SortAscending size={12} className="text-acc" />
                  <span>Cũ nhất trước</span>
                </>
              )}
            </button>
          </div>

          <span className="text-[10px] font-mono">
            {processedUploaded.all.length} ảnh
            {pinnedCount > 0 && ` • ${pinnedCount} ghim`}
          </span>
        </div>
      </div>

      {/* Error banner if upload failed */}
      {uploadError && (
        <div className="px-3 py-1.5 bg-err/10 border-b border-err/30 text-err text-[11px] flex items-center justify-between">
          <span>{uploadError}</span>
          <button type="button" onClick={() => onClearUploadError()} className="text-err hover:text-white">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Compact Drag-and-drop Upload Target */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer.files) void onFiles(e.dataTransfer.files);
        }}
        onClick={() => onBrowse()}
        className="mx-3 mt-3 p-3 rounded-ctl border border-dashed border-line2 hover:border-acc/60 bg-panel2/40 hover:bg-acc/5 text-center cursor-pointer transition-colors group shrink-0"
      >
        <div className="flex items-center justify-center gap-2 text-dim group-hover:text-acc transition-colors">
          <UploadSimple size={15} />
          <span className="text-[11px] font-semibold">Kéo thả ảnh hoặc bấm để tải lên</span>
        </div>
        <p className="text-[10px] text-mut mt-0.5">Hỗ trợ PNG, JPG, WebP (tối đa 50MB)</p>
      </div>

      {/* Uploaded List View (2-column visual grid) */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 min-h-0">
        {loading && uploaded.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-mut gap-2">
            <Spinner size={20} />
            <span className="text-[11px]">Đang tải danh sách ảnh...</span>
          </div>
        ) : processedUploaded.all.length === 0 ? (
          <div className="text-center py-16 px-4 text-mut">
            <ImageIcon size={32} className="mx-auto mb-2 opacity-40" />
            <p className="text-[12px] font-medium text-dim">Chưa có ảnh nào được tải lên</p>
            <p className="text-[10.5px] text-mut mt-1">Kéo thả hoặc bấm nút tải lên ở trên để bắt đầu</p>
          </div>
        ) : (
          <>
            {/* Pinned Section (if any pinned) */}
            {processedUploaded.pinned.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-2 px-1 text-[11px] font-bold text-acc tracking-tight uppercase font-mono">
                  <PushPin size={12} weight="fill" />
                  <span>Đã ghim ({processedUploaded.pinned.length})</span>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {processedUploaded.pinned.map((item) => (
                    <UploadedCard
                      key={item.id}
                      item={item}
                      isPinned={true}
                      isCopied={copiedId === item.id}
                      showProjectBadge={scope === "all"}
                      onTogglePin={(e) => onTogglePin(item, true, e)}
                      onInsert={() => onInsertToCanvas({ url: item.url, name: item.name, category: "image" })}
                      onPreview={() =>
                        onPreview({
                          url: item.url,
                          name: item.name,
                          category: "image",
                          created_ts: item.created_ts,
                          size_bytes: item.size_bytes,
                        })
                      }
                      onCopyUrl={(e) => onCopyUrl(item.url, item.id, e)}
                      onDelete={(e) => onDeleteUploaded(item, e)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Regular Section */}
            <div>
              {processedUploaded.pinned.length > 0 && (
                <div className="flex items-center gap-1.5 mb-2 px-1 text-[10.5px] font-medium text-mut tracking-tight uppercase font-mono">
                  <span>Tất cả ảnh ({processedUploaded.regular.length})</span>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2.5">
                {processedUploaded.regular.map((item) => (
                  <UploadedCard
                    key={item.id}
                    item={item}
                    isPinned={false}
                    isCopied={copiedId === item.id}
                    showProjectBadge={scope === "all"}
                    onTogglePin={(e) => onTogglePin(item, false, e)}
                    onInsert={() => onInsertToCanvas({ url: item.url, name: item.name, category: "image" })}
                    onPreview={() =>
                      onPreview({
                        url: item.url,
                        name: item.name,
                        category: "image",
                        created_ts: item.created_ts,
                        size_bytes: item.size_bytes,
                      })
                    }
                    onCopyUrl={(e) => onCopyUrl(item.url, item.id, e)}
                    onDelete={(e) => onDeleteUploaded(item, e)}
                  />
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

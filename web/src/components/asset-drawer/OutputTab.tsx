import { FilmSlate, Image as ImageIcon, MagnifyingGlass, PushPin, SortAscending, SortDescending, VideoCamera, X } from "@phosphor-icons/react";
import type { AssetOutputItem, AssetUploadedItem } from "../../types";
import type { AssetDrawerProps } from "../AssetDrawer";
import type { PreviewMediaItem } from "../MediaPreviewModal";
import { OutputCard } from "./AssetCards";
import type { AssetFilters } from "./useAssetFilters";
import { Spinner } from "../ui";

interface Props {
  filters: AssetFilters;
  outputs: AssetOutputItem[];
  loading: boolean;
  copiedId: string | null;
  scope: "project" | "all";
  onTogglePin: (item: AssetUploadedItem | AssetOutputItem, pinned: boolean, e?: React.MouseEvent) => void;
  onCopyUrl: (url: string, id: string, e?: React.MouseEvent) => void;
  onInsertToCanvas: AssetDrawerProps["onInsertToCanvas"];
  onPreview: (item: PreviewMediaItem) => void;
}

/** "Kết quả sinh" tab: category pills, search + sort bar and the pinned/regular output card grids. */
export function OutputTab({ filters, outputs, loading, copiedId, scope, onTogglePin, onCopyUrl, onInsertToCanvas, onPreview }: Props) {
  const {
    categoryFilter,
    setCategoryFilter,
    searchOutput,
    setSearchOutput,
    outputSort,
    setOutputSort,
    processedOutputs,
    outputCounts,
  } = filters;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Filter & Sort Bar */}
      <div className="p-3 border-b border-line2/70 bg-panel2/50 flex flex-col gap-2 shrink-0">
        {/* Category Filter Pills: All / Image / Video */}
        <div className="flex items-center gap-1.5 bg-panel p-1 rounded-ctl border border-line2">
          <button
            type="button"
            onClick={() => setCategoryFilter("all")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-[5px] transition-colors cursor-pointer flex items-center justify-center gap-1 ${
              categoryFilter === "all"
                ? "bg-acc text-accink shadow-xs"
                : "text-dim hover:text-fg hover:bg-panel2"
            }`}
          >
            <span>Tất cả</span>
            <span className="text-[10px] opacity-80 font-mono">({outputCounts.all})</span>
          </button>

          <button
            type="button"
            onClick={() => setCategoryFilter("image")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-[5px] transition-colors cursor-pointer flex items-center justify-center gap-1 ${
              categoryFilter === "image"
                ? "bg-acc text-accink shadow-xs"
                : "text-dim hover:text-fg hover:bg-panel2"
            }`}
          >
            <ImageIcon size={12} />
            <span>Ảnh</span>
            <span className="text-[10px] opacity-80 font-mono">({outputCounts.image})</span>
          </button>

          <button
            type="button"
            onClick={() => setCategoryFilter("video")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-[5px] transition-colors cursor-pointer flex items-center justify-center gap-1 ${
              categoryFilter === "video"
                ? "bg-acc text-accink shadow-xs"
                : "text-dim hover:text-fg hover:bg-panel2"
            }`}
          >
            <VideoCamera size={12} />
            <span>Video</span>
            <span className="text-[10px] opacity-80 font-mono">({outputCounts.video})</span>
          </button>
        </div>

        {/* Search input */}
        <div className="relative">
          <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mut pointer-events-none" />
          <input
            type="text"
            value={searchOutput}
            onChange={(e) => setSearchOutput(e.target.value)}
            placeholder="Tìm theo prompt hoặc tên kết quả..."
            className="w-full h-8 pl-8 pr-7 rounded-ctl border border-line2 bg-panel text-[11.5px] text-fg placeholder:text-mut focus:outline-none focus:border-acc/70"
          />
          {searchOutput && (
            <button
              type="button"
              onClick={() => setSearchOutput("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-mut hover:text-fg"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Sort row: Sort by time */}
        <div className="flex items-center justify-between text-[11px] text-mut">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-mut">Sắp xếp:</span>
            <button
              type="button"
              onClick={() => setOutputSort((s) => (s === "newest" ? "oldest" : "newest"))}
              className="inline-flex items-center gap-1 px-2 h-6 rounded-ctl border border-line2 bg-panel text-[10.5px] font-medium text-dim hover:text-fg hover:border-mut/60 transition-colors cursor-pointer"
              title="Đổi thứ tự sắp xếp thời gian"
            >
              {outputSort === "newest" ? (
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
            {processedOutputs.all.length} mục
          </span>
        </div>
      </div>

      {/* Output List View (2-column visual grid) */}
      <div className="flex-1 overflow-y-auto p-3 min-h-0">
        {loading && outputs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-mut gap-2">
            <Spinner size={20} />
            <span className="text-[11px]">Đang tải danh sách kết quả...</span>
          </div>
        ) : processedOutputs.all.length === 0 ? (
          <div className="text-center py-16 px-4 text-mut">
            <FilmSlate size={32} className="mx-auto mb-2 opacity-40" />
            <p className="text-[12px] font-medium text-dim">Không có kết quả nào</p>
            <p className="text-[10.5px] text-mut mt-1">
              {categoryFilter !== "all"
                ? `Không có ${categoryFilter === "video" ? "video" : "ảnh"} phù hợp bộ lọc`
                : "Chạy workflow hoặc playground để sinh kết quả ảnh/video"}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {processedOutputs.pinned.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-2 px-1 text-[11px] font-bold text-acc tracking-tight uppercase font-mono">
                  <PushPin size={12} weight="fill" />
                  <span>Đã ghim ({processedOutputs.pinned.length})</span>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {processedOutputs.pinned.map((item) => (
                    <OutputCard
                      key={item.id}
                      item={item}
                      isPinned={true}
                      isCopied={copiedId === item.id}
                      showProjectBadge={scope === "all"}
                      onTogglePin={(e) => onTogglePin(item, true, e)}
                      onInsert={() =>
                        onInsertToCanvas({
                          url: item.url,
                          name: item.prompt || item.name,
                          category: item.category,
                        })
                      }
                      onPreview={() =>
                        onPreview({
                          url: item.url,
                          name: item.name,
                          category: item.category,
                          prompt: item.prompt,
                          resolution: item.resolution,
                          created_ts: item.created_ts,
                          size_bytes: item.size_bytes,
                          duration_s: item.duration_s,
                        })
                      }
                      onCopyUrl={(e) => onCopyUrl(item.url, item.id, e)}
                    />
                  ))}
                </div>
              </div>
            )}
            <div>
              {processedOutputs.pinned.length > 0 && (
                <div className="flex items-center gap-1.5 mb-2 px-1 text-[10.5px] font-medium text-mut tracking-tight uppercase font-mono">
                  <span>Tất cả kết quả ({processedOutputs.regular.length})</span>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2.5">
                {processedOutputs.regular.map((item) => (
                  <OutputCard
                    key={item.id}
                    item={item}
                    isPinned={false}
                    isCopied={copiedId === item.id}
                    showProjectBadge={scope === "all"}
                    onTogglePin={(e) => onTogglePin(item, false, e)}
                    onInsert={() =>
                      onInsertToCanvas({
                        url: item.url,
                        name: item.prompt || item.name,
                        category: item.category,
                      })
                    }
                    onPreview={() =>
                      onPreview({
                        url: item.url,
                        name: item.name,
                        category: item.category,
                        prompt: item.prompt,
                        resolution: item.resolution,
                        created_ts: item.created_ts,
                        size_bytes: item.size_bytes,
                        duration_s: item.duration_s,
                      })
                    }
                    onCopyUrl={(e) => onCopyUrl(item.url, item.id, e)}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

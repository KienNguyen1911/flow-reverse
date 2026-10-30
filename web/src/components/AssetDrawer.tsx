import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowsCounterClockwise,
  Check,
  Copy,
  CornersOut,
  DownloadSimple,
  Eye,
  FilmSlate,
  FolderSimple,
  Image as ImageIcon,
  MagnifyingGlass,
  Play,
  Plus,
  PushPin,
  PushPinSlash,
  SortAscending,
  SortDescending,
  Trash,
  UploadSimple,
  VideoCamera,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { AssetOutputItem, AssetUploadedItem } from "../types";
import { Spinner } from "./ui";
import { MediaPreviewModal, type PreviewMediaItem } from "./MediaPreviewModal";

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
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}`;
}

function getTimestamp(ts?: number | string | null): number {
  if (!ts) return 0;
  if (typeof ts === "number") {
    return ts < 10000000000 ? ts * 1000 : ts;
  }
  const d = new Date(ts);
  if (!isNaN(d.getTime())) return d.getTime();
  const num = Number(ts);
  return !isNaN(num) ? (num < 10000000000 ? num * 1000 : num) : 0;
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

  // Sorting state: "newest" vs "oldest"
  const [uploadSort, setUploadSort] = useState<"newest" | "oldest">("newest");
  const [outputSort, setOutputSort] = useState<"newest" | "oldest">("newest");

  // Output tab category filter: "all" | "image" | "video"
  const [categoryFilter, setCategoryFilter] = useState<"all" | "image" | "video">("all");

  // Search queries
  const [searchUpload, setSearchUpload] = useState("");
  const [searchOutput, setSearchOutput] = useState("");

  // Uploading state inside drawer
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Copied indicator
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Preview modal for image / video
  const [previewItem, setPreviewItem] = useState<PreviewMediaItem | null>(null);

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

  // Process & filter Uploaded items
  const processedUploaded = useMemo(() => {
    let list = [...uploaded];

    // Search query
    if (searchUpload.trim()) {
      const q = searchUpload.toLowerCase();
      list = list.filter((item) => item.name.toLowerCase().includes(q));
    }

    // Sort by time
    list.sort((a, b) => {
      const tA = getTimestamp(a.created_ts);
      const tB = getTimestamp(b.created_ts);
      return uploadSort === "newest" ? tB - tA : tA - tB;
    });

    // Pinned priority: pinned items always float to the top
    const pinnedList: AssetUploadedItem[] = [];
    const regularList: AssetUploadedItem[] = [];
    for (const item of list) {
      if (item.isPinned) {
        pinnedList.push(item);
      } else {
        regularList.push(item);
      }
    }

    return {
      pinned: pinnedList,
      regular: regularList,
      all: [...pinnedList, ...regularList],
    };
  }, [uploaded, searchUpload, uploadSort]);

  // Process & filter Output items
  const processedOutputs = useMemo(() => {
    let list = [...outputs];

    // Category filter: image vs video vs all
    if (categoryFilter !== "all") {
      list = list.filter((item) => item.category === categoryFilter);
    }

    // Search query
    if (searchOutput.trim()) {
      const q = searchOutput.toLowerCase();
      list = list.filter(
        (item) =>
          item.name.toLowerCase().includes(q) ||
          (item.prompt && item.prompt.toLowerCase().includes(q)),
      );
    }

    // Sort by time
    list.sort((a, b) => {
      const tA = getTimestamp(a.created_ts);
      const tB = getTimestamp(b.created_ts);
      return outputSort === "newest" ? tB - tA : tA - tB;
    });

    const pinnedList = list.filter((item) => item.isPinned);
    const regularList = list.filter((item) => !item.isPinned);

    return { pinned: pinnedList, regular: regularList, all: list };
  }, [outputs, categoryFilter, searchOutput, outputSort]);

  const pinnedCount = useMemo(
    () =>
      uploaded.filter((i) => i.isPinned).length + outputs.filter((i) => i.isPinned).length,
    [uploaded, outputs],
  );

  // Category counts for outputs
  const outputCounts = useMemo(() => {
    let imgCount = 0;
    let vidCount = 0;
    for (const item of outputs) {
      if (item.category === "video") vidCount++;
      else imgCount++;
    }
    return { all: outputs.length, image: imgCount, video: vidCount };
  }, [outputs]);

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
                <button type="button" onClick={() => setUploadError(null)} className="text-err hover:text-white">
                  <X size={12} />
                </button>
              </div>
            )}

            {/* Compact Drag-and-drop Upload Target */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files) void handleFileUpload(e.dataTransfer.files);
              }}
              onClick={() => fileInputRef.current?.click()}
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
              {loadingUploaded && uploaded.length === 0 ? (
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
                            onTogglePin={(e) => handleTogglePin(item, true, e)}
                            onInsert={() => onInsertToCanvas({ url: item.url, name: item.name, category: "image" })}
                            onPreview={() =>
                              setPreviewItem({
                                url: item.url,
                                name: item.name,
                                category: "image",
                                created_ts: item.created_ts,
                                size_bytes: item.size_bytes,
                              })
                            }
                            onCopyUrl={(e) => handleCopyUrl(item.url, item.id, e)}
                            onDelete={(e) => handleDeleteUploaded(item, e)}
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
                          onTogglePin={(e) => handleTogglePin(item, false, e)}
                          onInsert={() => onInsertToCanvas({ url: item.url, name: item.name, category: "image" })}
                          onPreview={() =>
                            setPreviewItem({
                              url: item.url,
                              name: item.name,
                              category: "image",
                              created_ts: item.created_ts,
                              size_bytes: item.size_bytes,
                            })
                          }
                          onCopyUrl={(e) => handleCopyUrl(item.url, item.id, e)}
                          onDelete={(e) => handleDeleteUploaded(item, e)}
                        />
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: OUTPUT */}
        {activeTab === "output" && (
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
              {loadingOutputs && outputs.length === 0 ? (
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
                            onTogglePin={(e) => handleTogglePin(item, true, e)}
                            onInsert={() =>
                              onInsertToCanvas({
                                url: item.url,
                                name: item.prompt || item.name,
                                category: item.category,
                              })
                            }
                            onPreview={() =>
                              setPreviewItem({
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
                            onCopyUrl={(e) => handleCopyUrl(item.url, item.id, e)}
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
                          onTogglePin={(e) => handleTogglePin(item, false, e)}
                          onInsert={() =>
                            onInsertToCanvas({
                              url: item.url,
                              name: item.prompt || item.name,
                              category: item.category,
                            })
                          }
                          onPreview={() =>
                            setPreviewItem({
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
                          onCopyUrl={(e) => handleCopyUrl(item.url, item.id, e)}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
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

// --------------------------------------------------------------------------- //
// Uploaded Card Component
// --------------------------------------------------------------------------- //

function UploadedCard({
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

// --------------------------------------------------------------------------- //
// Output Card Component
// --------------------------------------------------------------------------- //

function OutputCard({
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

import { useEffect, useRef, useState } from "react";
import { CaretDown, FloppyDisk, FolderSimple, Gear, Play, Plus, Sparkle, Trash, X } from "@phosphor-icons/react";
import { Chip, Spinner } from "./ui";

export interface CanvasStats {
  imageCount: number;
  videoCount: number;
  lastFrameCount: number;
  nRunning: number;
  nDone: number;
  nPending: number;
  groupCount: number;
  selectedCount: number;
  wfBusy: boolean;
  linking: boolean;
}

export function TopBar({
  onLoadTemplate,
  onSaveTemplate,
  onDeleteCustomTemplate,
  customTemplates = [],
  onRunWorkflow,
  canvasStats,
  onOpenSettings,
  onToggleAssetDrawer,
  assetDrawerOpen,
  assetCount,
  currentProjectName,
  projectCount,
  projectSaveState = "idle",
  onOpenProjectManager,
}: {
  onLoadTemplate: (name: string) => void;
  onSaveTemplate?: (name: string) => void;
  onDeleteCustomTemplate?: (id: string) => void;
  customTemplates?: { id: string; name: string }[];
  onRunWorkflow: () => void;
  canvasStats?: CanvasStats | null;
  onOpenSettings: () => void;
  onToggleAssetDrawer?: () => void;
  assetDrawerOpen?: boolean;
  assetCount?: number;
  currentProjectName?: string | null;
  projectCount?: number;
  projectSaveState?: "idle" | "saving" | "saved" | "error";
  onOpenProjectManager?: () => void;
}) {
  const [templateMenuOpen, setTemplateMenuOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [templateNameInput, setTemplateNameInput] = useState("");
  const templateMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!templateMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (templateMenuRef.current && !templateMenuRef.current.contains(e.target as Node)) {
        setTemplateMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [templateMenuOpen]);

  const handleOpenSaveModal = () => {
    setTemplateMenuOpen(false);
    setTemplateNameInput(`Mẫu Lookbook 8s - ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
    setSaveModalOpen(true);
  };

  const handleConfirmSave = () => {
    if (!templateNameInput.trim()) return;
    onSaveTemplate?.(templateNameInput.trim());
    setSaveModalOpen(false);
  };

  const totalNodes =
    (canvasStats?.imageCount ?? 0) +
    (canvasStats?.videoCount ?? 0) +
    (canvasStats?.lastFrameCount ?? 0);

  const wfBusy = !!canvasStats?.wfBusy;
  const selectedCount = canvasStats?.selectedCount ?? 0;
  const groupCount = canvasStats?.groupCount ?? 0;
  const scopeLabel = selectedCount > 0 ? `Chạy vùng chọn (${selectedCount})` : "Chạy Workflow";
  const scopeTitle =
    selectedCount > 0
      ? "Chạy các nhóm chứa node đang chọn (mỗi nhóm độc lập — node lỗi chỉ dừng nhóm đó)"
      : groupCount > 0
        ? `Chạy ${groupCount} nhóm theo thứ tự (node lỗi chỉ dừng nhóm đó, nhóm khác vẫn chạy)`
        : "Chạy toàn bộ workflow theo chuỗi phụ thuộc";

  return (
    <>
      <header className="h-[52px] shrink-0 border-b border-line bg-panel/95 backdrop-blur-md px-4 flex items-center justify-between gap-3 select-none relative z-50">
        {/* LEFT CLUSTER: Logo + Templates Picker + Save Button */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="grid size-6 place-items-center rounded-[7px] bg-acc shadow-sm shadow-acc/20">
              <span className="block size-2.5 rounded-[3px] bg-accink" />
            </div>
            <div className="leading-none">
              <h1 className="text-[14.5px] font-bold tracking-tight text-fg">Flow Bench</h1>
              <p className="mt-0.5 text-[10px] font-medium text-mut">Workspace Canvas</p>
            </div>
          </div>

          <div className="h-4 w-px bg-line2 shrink-0 mx-1" />

          {onOpenProjectManager && (
            <button
              type="button"
              onClick={onOpenProjectManager}
              className="inline-flex items-center gap-2 px-2.5 h-8 max-w-[240px] rounded-ctl border border-line2 bg-panel2 text-[12px] font-semibold text-dim hover:text-fg hover:border-acc/50 transition-colors cursor-pointer"
              title="Chuyển / quản lý Project (canvas & assets riêng)"
            >
              <FolderSimple size={14} weight="bold" className="text-acc shrink-0" />
              <span className="truncate max-w-[150px]">{currentProjectName || "Chọn Project"}</span>
              {typeof projectCount === "number" && projectCount > 1 && (
                <span className="px-1 py-0.2 rounded bg-line2 text-[9px] font-mono text-mut shrink-0">
                  {projectCount}
                </span>
              )}
              <span
                className={`size-1.5 rounded-full shrink-0 ${
                  projectSaveState === "saved"
                    ? "bg-ok"
                    : projectSaveState === "saving"
                      ? "bg-acc animate-pulse"
                      : projectSaveState === "error"
                        ? "bg-err"
                        : "bg-mut/50"
                }`}
                title={
                  projectSaveState === "saved"
                    ? "Đã lưu canvas"
                    : projectSaveState === "saving"
                      ? "Đang lưu canvas..."
                      : projectSaveState === "error"
                        ? "Lưu canvas thất bại"
                        : "Chưa có thay đổi"
                }
              />
              <CaretDown size={10} weight="bold" className="text-mut shrink-0" />
            </button>
          )}

          {onToggleAssetDrawer && (
            <button
              type="button"
              onClick={onToggleAssetDrawer}
              className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border text-[12px] font-bold transition-all cursor-pointer shadow-xs ${
                assetDrawerOpen
                  ? "bg-acc text-accink border-acc shadow-acc/20"
                  : "border-line2 bg-panel2 text-dim hover:text-fg hover:border-acc/50"
              }`}
              title="Mở Kho Assets (Ảnh tải lên & Kết quả sinh) [Phím tắt: A]"
            >
              <FolderSimple size={15} weight={assetDrawerOpen ? "fill" : "bold"} />
              <span>Kho Assets</span>
              {typeof assetCount === "number" && assetCount > 0 && (
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                    assetDrawerOpen ? "bg-accink/20 text-accink" : "bg-line2 text-mut"
                  }`}
                >
                  {assetCount}
                </span>
              )}
            </button>
          )}

          {/* TEMPLATE PICKER DROPDOWN */}
          <div className="relative flex items-center gap-1" ref={templateMenuRef}>
            <button
              type="button"
              onClick={() => setTemplateMenuOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-acc/45 bg-acc/10 text-[12px] font-bold text-acc hover:bg-acc/20 hover:border-acc/70 transition-colors cursor-pointer shadow-sm shadow-acc/5"
              title="Mở danh sách các Mẫu Workflow (Template) hệ thống và tự lưu"
            >
              <Sparkle size={13} weight="fill" className="text-acc" />
              <span>Mẫu Workflow</span>
              <CaretDown
                size={11}
                weight="bold"
                className={`transition-transform duration-200 ${templateMenuOpen ? "rotate-180" : ""}`}
              />
            </button>

            {onSaveTemplate && (
              <button
                type="button"
                onClick={handleOpenSaveModal}
                className="inline-flex items-center gap-1 px-2.5 h-8 rounded-ctl border border-line2 bg-panel2 text-[11.5px] font-semibold text-dim hover:text-fg hover:border-acc/60 transition-colors cursor-pointer"
                title="Lưu toàn bộ nodes, nhóm và liên kết hiện tại trên canvas thành Mẫu Template mới"
              >
                <FloppyDisk size={13} />
                <span>Lưu Mẫu</span>
              </button>
            )}

            {/* Dropdown Menu */}
            {templateMenuOpen && (
              <div className="absolute top-full left-0 mt-1.5 w-[320px] rounded-panel border border-line2 bg-panel shadow-2xl p-1.5 z-[100] flex flex-col gap-1 text-[12px] animate-in fade-in zoom-in-95 duration-100">
                <div className="px-2 py-1 text-[9.5px] font-bold uppercase tracking-wider text-mut">
                  Mẫu Hệ Thống (Built-in)
                </div>

                <button
                  type="button"
                  onClick={() => {
                    onLoadTemplate("lookbook_8s");
                    setTemplateMenuOpen(false);
                  }}
                  className="flex items-start gap-2 px-2.5 py-1.5 rounded-ctl hover:bg-panel2 text-left transition-colors cursor-pointer group"
                >
                  <Sparkle size={14} weight="fill" className="text-acc shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-fg group-hover:text-acc transition-colors text-[11.5px]">
                      Lookbook Video 8s (Đẩy UI + Nối tiếp)
                    </div>
                    <div className="text-[10px] text-mut leading-tight">
                      2 nhóm: Video 1 đẩy cột NABI (8s) → Frame Cuối → Video 2 Showcase (8s) & Sinh ảnh 9:16
                    </div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    onLoadTemplate("tryon");
                    setTemplateMenuOpen(false);
                  }}
                  className="flex items-start gap-2 px-2.5 py-1.5 rounded-ctl hover:bg-panel2 text-left transition-colors cursor-pointer group"
                >
                  <Sparkle size={14} weight="bold" className="text-dim shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-fg group-hover:text-acc transition-colors text-[11.5px]">
                      Video Thử Đồ (Try-On 16s)
                    </div>
                    <div className="text-[10px] text-mut leading-tight">
                      2 ảnh tham chiếu (mẫu + đồ) → sinh ảnh → chuỗi 2 video 8s
                    </div>
                  </div>
                </button>

                {/* Custom User Templates */}
                {customTemplates.length > 0 && (
                  <>
                    <div className="h-px bg-line2 my-0.5" />
                    <div className="px-2 py-1 text-[9.5px] font-bold uppercase tracking-wider text-mut">
                      Mẫu Đã Lưu Của Bạn ({customTemplates.length})
                    </div>
                    <div className="max-h-[160px] overflow-y-auto flex flex-col gap-0.5">
                      {customTemplates.map((tpl) => (
                        <div
                          key={tpl.id}
                          className="flex items-center justify-between gap-1 px-2.5 py-1.5 rounded-ctl hover:bg-panel2 group"
                        >
                          <button
                            type="button"
                            onClick={() => {
                              onLoadTemplate(tpl.id);
                              setTemplateMenuOpen(false);
                            }}
                            className="flex-1 min-w-0 text-left font-semibold text-fg hover:text-acc truncate cursor-pointer text-[11.5px]"
                            title={`Tải mẫu "${tpl.name}"`}
                          >
                            {tpl.name}
                          </button>
                          {onDeleteCustomTemplate && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDeleteCustomTemplate(tpl.id);
                              }}
                              className="size-5 grid place-items-center text-mut hover:text-err rounded hover:bg-panel cursor-pointer shrink-0"
                              title="Xóa mẫu này"
                            >
                              <Trash size={12} />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                )}

                <div className="h-px bg-line2 my-0.5" />
                <button
                  type="button"
                  onClick={handleOpenSaveModal}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-ctl bg-acc/10 hover:bg-acc/20 text-acc font-bold text-left transition-colors cursor-pointer text-[11.5px]"
                >
                  <Plus size={13} weight="bold" />
                  <span>Lưu Canvas hiện tại thành Mẫu mới...</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT CLUSTER: Node Count Badges + Run Workflow + Settings Button */}
        <div className="flex items-center gap-2.5 shrink-0">
          {canvasStats && (
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-mut">
              {canvasStats.imageCount > 0 && <Chip tone="neutral">{`${canvasStats.imageCount} ảnh`}</Chip>}
              {canvasStats.videoCount > 0 && <Chip tone="neutral">{`${canvasStats.videoCount} video`}</Chip>}
              {canvasStats.lastFrameCount > 0 && (
                <Chip tone="neutral">{`${canvasStats.lastFrameCount} frame`}</Chip>
              )}
              {canvasStats.nRunning > 0 && <Chip tone="acc" live>{`${canvasStats.nRunning} chạy`}</Chip>}
              {canvasStats.nDone > 0 && <Chip tone="ok">{`${canvasStats.nDone} xong`}</Chip>}
              {canvasStats.nPending > 0 && <Chip tone="warn">{`${canvasStats.nPending} chờ`}</Chip>}
              {groupCount > 0 && <Chip tone="acc">{`${groupCount} nhóm`}</Chip>}
              {selectedCount > 0 && <Chip tone="neutral">{`${selectedCount} chọn`}</Chip>}
            </div>
          )}

          <div className="h-4 w-px bg-line2 shrink-0 mx-0.5" />

          <button
            type="button"
            onClick={onRunWorkflow}
            disabled={wfBusy || totalNodes === 0}
            className="inline-flex items-center gap-1.5 px-3.5 h-8 rounded-ctl bg-acc text-accink text-[12px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none shadow-sm shadow-acc/10"
            title={scopeTitle}
          >
            {wfBusy ? <Spinner size={12} /> : <Play size={12} weight="fill" />}
            <span>{scopeLabel}</span>
          </button>

          <button
            type="button"
            onClick={onOpenSettings}
            className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-line2 bg-panel2 text-[12px] font-semibold text-dim hover:text-fg hover:border-mut/60 transition-colors cursor-pointer"
            title="Mở Cài đặt & Tiện ích (Thư viện, Tài khoản, Hướng dẫn, Docs API)"
          >
            <Gear size={15} />
            <span>Cài đặt</span>
          </button>
        </div>
      </header>

      {/* SAVE TEMPLATE MODAL */}
      {saveModalOpen && (
        <div className="fixed inset-0 bg-ink/75 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-[390px] rounded-panel border border-line bg-panel p-4 shadow-2xl flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-[14px] font-bold text-fg flex items-center gap-1.5">
                <FloppyDisk size={16} className="text-acc" />
                <span>Lưu Workflow thành Mẫu</span>
              </h3>
              <button
                type="button"
                onClick={() => setSaveModalOpen(false)}
                className="size-6 grid place-items-center rounded text-mut hover:text-fg hover:bg-panel2 cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            <p className="text-[11px] text-mut leading-relaxed">
              Toàn bộ các nodes, nhóm, cài đặt prompt và liên kết hiện tại trên canvas sẽ được lưu lại thành một mẫu độc lập để bạn có thể tải lại bất kỳ lúc nào.
            </p>

            <div className="flex flex-col gap-1">
              <label className="text-[10.5px] font-semibold text-mut">Tên mẫu Template:</label>
              <input
                type="text"
                value={templateNameInput}
                onChange={(e) => setTemplateNameInput(e.target.value)}
                placeholder="Nhập tên mẫu..."
                className="h-8 rounded-ctl border border-line2 bg-panel2 px-2.5 text-[12px] text-fg focus:border-acc outline-none"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleConfirmSave();
                  if (e.key === "Escape") setSaveModalOpen(false);
                }}
              />
            </div>

            <div className="flex items-center justify-end gap-2 mt-1">
              <button
                type="button"
                onClick={() => setSaveModalOpen(false)}
                className="px-3 h-7 rounded-ctl border border-line2 bg-panel2 text-[11px] font-semibold text-mut hover:text-fg cursor-pointer"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleConfirmSave}
                disabled={!templateNameInput.trim()}
                className="px-3.5 h-7 rounded-ctl bg-acc text-accink text-[11px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40"
              >
                Lưu Template
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  Clock,
  Copy,
  DotsThreeVertical,
  FolderSimple,
  ImageSquare,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Sparkle,
  Stack,
  Trash,
  UploadSimple,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import type { WorkspaceProject } from "../types";
import { Btn, Spinner } from "./ui";

export interface ProjectTemplateOption {
  id: string;
  name: string;
}

export interface ProjectManagerModalProps {
  open: boolean;
  onClose: () => void;
  projects: WorkspaceProject[];
  currentProjectId: string | null;
  templates: ProjectTemplateOption[];
  onSelect: (id: string) => void | Promise<void>;
  onCreate: (name: string, templateId: string | null) => Promise<WorkspaceProject | null>;
  onRename: (id: string, name: string) => Promise<void>;
  onDuplicate: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  /** Set (or clear, with null) the project preview image. */
  onSetThumbnail: (id: string, url: string | null) => Promise<void>;
  onRefresh: () => void;
  busy?: boolean;
}

/** Minimal shape needed to render a thumbnail chooser tile. */
interface ThumbCandidate {
  url: string;
  label: string;
  category: "image" | "video";
}

function fmtRelative(ts: number): string {
  if (!ts) return "—";
  const diff = Date.now() - ts;
  if (diff < 60_000) return "vừa xong";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} phút trước`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} giờ trước`;
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} ngày trước`;
  const d = new Date(ts);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export function ProjectManagerModal({
  open,
  onClose,
  projects,
  currentProjectId,
  templates,
  onSelect,
  onCreate,
  onRename,
  onDuplicate,
  onDelete,
  onSetThumbnail,
  onRefresh,
  busy = false,
}: ProjectManagerModalProps) {
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [menuId, setMenuId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [thumbPickerId, setThumbPickerId] = useState<string | null>(null);
  const [thumbCandidates, setThumbCandidates] = useState<ThumbCandidate[]>([]);
  const [thumbLoading, setThumbLoading] = useState(false);
  const [thumbUploading, setThumbUploading] = useState(false);
  const thumbInputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const newNameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setCreating(false);
    setNewName("");
    setTemplateId(null);
    setEditingId(null);
    setMenuId(null);
    setError(null);
    setThumbPickerId(null);
    const t = window.setTimeout(() => searchRef.current?.focus(), 60);
    return () => window.clearTimeout(t);
  }, [open]);

  // Load every image/video the user can pick as a project preview.
  useEffect(() => {
    if (!thumbPickerId) return;
    let cancelled = false;
    setThumbLoading(true);
    void (async () => {
      try {
        const [ups, outs] = await Promise.all([
          api.assetsUploaded(null, "all"),
          api.assetsOutputs(null, "all"),
        ]);
        if (cancelled) return;
        const seen = new Set<string>();
        const candidates: ThumbCandidate[] = [];
        const push = (url: string | null | undefined, label: string, category: "image" | "video") => {
          if (!url || seen.has(url)) return;
          seen.add(url);
          candidates.push({ url, label, category });
        };
        for (const item of outs.items ?? []) {
          push(item.thumbnail_url || (item.category === "image" ? item.url : null), item.name, item.category);
        }
        for (const item of ups.items ?? []) {
          push(item.url, item.name, item.category);
        }
        setThumbCandidates(candidates.slice(0, 120));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setThumbLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [thumbPickerId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (thumbPickerId) setThumbPickerId(null);
        else if (creating) setCreating(false);
        else if (editingId) setEditingId(null);
        else setMenuId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, creating, editingId, thumbPickerId]);

  useEffect(() => {
    if (creating) {
      const t = window.setTimeout(() => newNameRef.current?.focus(), 60);
      return () => window.clearTimeout(t);
    }
  }, [creating]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.description || "").toLowerCase().includes(q),
    );
  }, [projects, search]);

  if (!open) return null;

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setError(null);
    setPendingId("__create__");
    try {
      const project = await onCreate(name, templateId);
      if (project) {
        setCreating(false);
        setNewName("");
        setTemplateId(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  const handleRename = async (id: string) => {
    const name = editName.trim();
    if (!name) return;
    setError(null);
    setPendingId(id);
    try {
      await onRename(id, name);
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  const handleDuplicate = async (id: string) => {
    setMenuId(null);
    setError(null);
    setPendingId(id);
    try {
      await onDuplicate(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  const handleDelete = async (project: WorkspaceProject) => {
    if (
      !window.confirm(
        `Xóa project "${project.name}"? Canvas sẽ bị xóa vĩnh viễn. Assets đã tạo vẫn được giữ lại nhưng không còn thuộc project nào.`,
      )
    ) {
      return;
    }
    setError(null);
    setPendingId(project.id);
    try {
      await onDelete(project.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  const applyThumbnail = async (projectId: string, url: string | null) => {
    setError(null);
    setThumbPickerId(null);
    setPendingId(projectId);
    try {
      await onSetThumbnail(projectId, url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  const uploadThumbnail = async (projectId: string, file: File) => {
    if (!file.type.startsWith("image/")) {
      setError("Ảnh preview phải là file ảnh (PNG/JPG/WebP).");
      return;
    }
    setError(null);
    setThumbUploading(true);
    try {
      const res = await api.upload(file, projectId);
      await applyThumbnail(projectId, res.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setThumbUploading(false);
    }
  };

  const handleSelect = async (id: string) => {
    if (id === currentProjectId) {
      onClose();
      return;
    }
    setError(null);
    setPendingId(id);
    try {
      await onSelect(id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/65 backdrop-blur-sm select-none">
      <div className="absolute inset-0" onClick={onClose} />
      <div className="relative w-full max-w-[900px] h-[min(760px,88vh)] rounded-panel border border-line2 bg-panel shadow-2xl flex flex-col overflow-hidden">
        {/* header */}
        <header className="flex items-center justify-between gap-3 px-5 h-14 border-b border-line2 bg-panel2/80 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="size-7 rounded-[7px] bg-acc/15 border border-acc/35 grid place-items-center text-acc">
              <FolderSimple size={16} weight="fill" />
            </div>
            <div className="min-w-0">
              <h2 className="text-[13.5px] font-bold text-fg leading-tight">Quản lý Project</h2>
              <p className="text-[10px] text-mut font-medium">
                {projects.length} project • Canvas, assets và viewport được lưu riêng
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Btn variant="ghost" onClick={onRefresh} disabled={busy}>
              Làm mới
            </Btn>
            <button
              type="button"
              onClick={onClose}
              className="size-8 grid place-items-center rounded-ctl text-mut hover:text-fg hover:bg-panel3 cursor-pointer"
              title="Đóng (Esc)"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {/* toolbar */}
        <div className="px-5 py-3 border-b border-line2/70 bg-panel/60 flex items-center gap-2.5 shrink-0">
          <div className="relative flex-1 max-w-[360px]">
            <MagnifyingGlass
              size={13}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mut pointer-events-none"
            />
            <input
              ref={searchRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm project theo tên hoặc mô tả..."
              className="w-full h-8 pl-8 pr-7 rounded-ctl border border-line2 bg-panel2 text-[11.5px] text-fg placeholder:text-mut focus:outline-none focus:border-acc/70"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-mut hover:text-fg cursor-pointer"
              >
                <X size={12} />
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => setCreating((v) => !v)}
            className="ml-auto inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer shadow-sm shadow-acc/10"
          >
            <Plus size={13} weight="bold" />
            <span>Tạo Project mới</span>
          </button>
        </div>

        {error && (
          <div className="px-5 py-2 bg-err/10 border-b border-err/30 text-err text-[11px] flex items-center justify-between">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} className="text-err hover:text-white cursor-pointer">
              <X size={12} />
            </button>
          </div>
        )}

        {/* create panel */}
        {creating && (
          <div className="px-5 py-3 border-b border-line2 bg-acc/[0.04] shrink-0">
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                ref={newNameRef}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCreate();
                }}
                placeholder="Tên project mới (vd: Lookbook Thu Đông)"
                maxLength={120}
                className="flex-1 h-8 rounded-ctl border border-line2 bg-panel px-2.5 text-[12px] text-fg placeholder:text-mut focus:outline-none focus:border-acc/70"
              />
              <select
                value={templateId ?? ""}
                onChange={(e) => setTemplateId(e.target.value || null)}
                className="h-8 rounded-ctl border border-line2 bg-panel px-2 text-[11.5px] text-fg focus:outline-none focus:border-acc/70 min-w-[220px]"
                title="Bắt đầu từ canvas trống hoặc một Mẫu Workflow"
              >
                <option value="">Canvas trống</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    Mẫu: {t.name}
                  </option>
                ))}
              </select>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={!newName.trim() || pendingId === "__create__"}
                  className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl bg-acc text-accink text-[11.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40"
                >
                  {pendingId === "__create__" ? <Spinner size={12} /> : <Check size={12} weight="bold" />}
                  <span>Tạo</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setNewName("");
                    setTemplateId(null);
                  }}
                  className="px-2.5 h-8 rounded-ctl border border-line2 bg-panel2 text-[11px] font-semibold text-mut hover:text-fg cursor-pointer"
                >
                  Hủy
                </button>
              </div>
            </div>
            <p className="mt-1.5 text-[10px] text-mut flex items-center gap-1">
              <Sparkle size={10} className="text-acc" />
              Project mới có canvas riêng — tải Mẫu Workflow sẽ không ảnh hưởng project khác.
            </p>
          </div>
        )}

        {/* project grid */}
        <div className="flex-1 overflow-y-auto slim-scroll p-4">
          {filtered.length === 0 ? (
            <div className="h-full grid place-items-center text-center text-mut">
              <div>
                <FolderSimple size={34} className="mx-auto opacity-40" />
                <p className="mt-3 text-[12.5px] font-medium text-dim">
                  {search ? "Không tìm thấy project phù hợp" : "Chưa có project nào"}
                </p>
                <p className="mt-1 text-[11px]">Bấm “Tạo Project mới” để bắt đầu một canvas độc lập.</p>
              </div>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((project) => {
                const active = project.id === currentProjectId;
                const nodeCount = project.nodeCount ?? project.canvasState?.nodes?.length ?? 0;
                const assetCount = project.assetCount ?? 0;
                const isPending = pendingId === project.id;
                return (
                  <div
                    key={project.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      if (editingId === project.id) return;
                      void handleSelect(project.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        void handleSelect(project.id);
                      }
                    }}
                    className={`group relative rounded-panel border overflow-hidden bg-panel2/50 transition-all cursor-pointer flex flex-col text-left ${
                      active
                        ? "border-acc ring-1 ring-acc/40 shadow-lg shadow-acc/5"
                        : "border-line2 hover:border-acc/50 hover:bg-panel2"
                    }`}
                  >
                    {/* thumbnail */}
                    <div className="relative aspect-[16/9] bg-ink overflow-hidden">
                      {project.thumbnailUrl ? (
                        <img
                          src={project.thumbnailUrl}
                          alt={project.name}
                          loading="lazy"
                          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                        />
                      ) : (
                        <div className="w-full h-full grid place-items-center bg-gradient-to-br from-panel2 to-ink">
                          <Stack size={26} className="text-mut/60" />
                        </div>
                      )}
                      <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
                      {active && (
                        <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide bg-acc text-accink shadow">
                          Đang mở
                        </span>
                      )}
                      {isPending && (
                        <span className="absolute inset-0 bg-black/45 grid place-items-center">
                          <Spinner size={18} />
                        </span>
                      )}

                      {/* quick actions */}
                      <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setThumbPickerId(project.id);
                          }}
                          className="size-6 grid place-items-center rounded bg-black/55 text-white/80 hover:text-white hover:bg-black/75 cursor-pointer"
                          title="Chọn ảnh preview cho project"
                        >
                          <ImageSquare size={13} weight="bold" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuId(menuId === project.id ? null : project.id);
                          }}
                          className="size-6 grid place-items-center rounded bg-black/55 text-white/80 hover:text-white hover:bg-black/75 cursor-pointer"
                          title="Tùy chọn project"
                        >
                          <DotsThreeVertical size={13} weight="bold" />
                        </button>
                      </div>

                      {menuId === project.id && (
                        <div
                          className="absolute top-8 right-1.5 w-[150px] rounded-ctl border border-line2 bg-panel shadow-xl p-1 z-20 flex flex-col"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setMenuId(null);
                              setEditingId(project.id);
                              setEditName(project.name);
                            }}
                            className="flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-dim hover:text-fg hover:bg-panel2 cursor-pointer"
                          >
                            <PencilSimple size={12} /> Đổi tên
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setMenuId(null);
                              setThumbPickerId(project.id);
                            }}
                            className="flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-dim hover:text-fg hover:bg-panel2 cursor-pointer"
                          >
                            <ImageSquare size={12} /> Ảnh preview
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDuplicate(project.id)}
                            className="flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-dim hover:text-fg hover:bg-panel2 cursor-pointer"
                          >
                            <Copy size={12} /> Nhân bản
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDelete(project)}
                            disabled={projects.length <= 1}
                            className="flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-err hover:bg-err/10 cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
                            title={projects.length <= 1 ? "Không thể xóa project cuối cùng" : "Xóa project"}
                          >
                            <Trash size={12} /> Xóa
                          </button>
                        </div>
                      )}
                    </div>

                    {/* info */}
                    <div className="p-3 flex flex-col gap-1.5 min-w-0">
                      {editingId === project.id ? (
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <input
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") void handleRename(project.id);
                              if (e.key === "Escape") setEditingId(null);
                            }}
                            maxLength={120}
                            autoFocus
                            className="flex-1 min-w-0 h-7 rounded border border-acc/60 bg-panel px-1.5 text-[11.5px] text-fg outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => void handleRename(project.id)}
                            className="size-7 grid place-items-center rounded bg-acc text-accink hover:bg-acc2 cursor-pointer"
                            title="Lưu tên"
                          >
                            <Check size={11} weight="bold" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="size-7 grid place-items-center rounded border border-line2 text-mut hover:text-fg cursor-pointer"
                            title="Hủy"
                          >
                            <X size={11} />
                          </button>
                        </div>
                      ) : (
                        <p className="text-[12px] font-bold text-fg truncate" title={project.name}>
                          {project.name}
                        </p>
                      )}
                      <div className="flex items-center gap-2 text-[10px] font-mono text-mut">
                        <span>{nodeCount} node</span>
                        <span className="text-line2">•</span>
                        <span>{assetCount} asset</span>
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-mut">
                        <Clock size={10} />
                        <span>{fmtRelative(project.updatedAt)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* thumbnail picker */}
        {thumbPickerId && (() => {
          const target = projects.find((p) => p.id === thumbPickerId);
          if (!target) return null;
          return (
            <div className="absolute inset-0 z-30 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-4">
              <div className="w-full max-w-[620px] max-h-[80%] rounded-panel border border-line2 bg-panel shadow-2xl flex flex-col overflow-hidden">
                <header className="flex items-center justify-between gap-2 px-4 h-12 border-b border-line2 bg-panel2/80 shrink-0">
                  <div className="min-w-0">
                    <h3 className="text-[12.5px] font-bold text-fg truncate">
                      Ảnh preview — {target.name}
                    </h3>
                    <p className="text-[10px] text-mut">Chọn từ assets, hoặc tải ảnh mới từ máy.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setThumbPickerId(null)}
                    className="size-7 grid place-items-center rounded-ctl text-mut hover:text-fg hover:bg-panel3 cursor-pointer shrink-0"
                    title="Đóng (Esc)"
                  >
                    <X size={14} />
                  </button>
                </header>

                <div className="px-4 py-2.5 border-b border-line2 flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => thumbInputRef.current?.click()}
                    disabled={thumbUploading}
                    className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-ctl bg-acc/15 border border-acc/40 text-acc text-[11px] font-bold hover:bg-acc/25 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {thumbUploading ? <Spinner size={11} /> : <UploadSimple size={12} weight="bold" />}
                    <span>Tải ảnh lên</span>
                  </button>
                  <input
                    ref={thumbInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void uploadThumbnail(target.id, file);
                      e.target.value = "";
                    }}
                  />
                  {target.thumbnailUrl && (
                    <button
                      type="button"
                      onClick={() => void applyThumbnail(target.id, null)}
                      className="ml-auto px-2.5 h-7 rounded-ctl border border-line2 bg-panel2 text-[10.5px] font-semibold text-mut hover:text-err hover:border-err/50 transition-colors cursor-pointer"
                      title="Bỏ ảnh preview, quay lại thumbnail tự động"
                    >
                      Bỏ ảnh đã chọn
                    </button>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto slim-scroll p-3">
                  {thumbLoading ? (
                    <div className="grid place-items-center py-14 text-mut gap-2">
                      <Spinner size={18} />
                      <span className="text-[11px]">Đang tải assets...</span>
                    </div>
                  ) : thumbCandidates.length === 0 ? (
                    <div className="grid place-items-center py-14 text-center text-mut">
                      <div>
                        <ImageSquare size={28} className="mx-auto opacity-40" />
                        <p className="mt-2 text-[11.5px]">Chưa có ảnh nào để chọn.</p>
                        <p className="text-[10px] mt-0.5">Hãy tải ảnh lên hoặc tạo kết quả trước.</p>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                      {thumbCandidates.map((cand) => {
                        const selected = target.thumbnailUrl === cand.url;
                        return (
                          <button
                            key={cand.url}
                            type="button"
                            onClick={() => void applyThumbnail(target.id, cand.url)}
                            className={`relative aspect-[4/3] rounded-ctl overflow-hidden border-2 transition-all cursor-pointer group ${
                              selected
                                ? "border-acc ring-1 ring-acc/40"
                                : "border-transparent hover:border-acc/60"
                            }`}
                            title={cand.label}
                          >
                            <img
                              src={cand.url}
                              alt={cand.label}
                              loading="lazy"
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                            />
                            {selected && (
                              <span className="absolute inset-0 bg-acc/25 grid place-items-center">
                                <span className="size-5 rounded-full bg-acc text-accink grid place-items-center">
                                  <Check size={11} weight="bold" />
                                </span>
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })()}

        <footer className="px-5 py-2.5 border-t border-line2 bg-panel2/60 text-[10px] text-mut flex items-center justify-between shrink-0">
          <span>Autosave canvas mỗi 0.8s • Viewport, node, nhóm và liên kết được khôi phục khi chuyển project.</span>
          <span className="font-mono">{currentProjectId ? currentProjectId.slice(0, 14) : "—"}</span>
        </footer>
      </div>
    </div>
  );
}

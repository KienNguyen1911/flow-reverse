import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAssets, useGallery, usePool, useStatus, useWorkspaceProjects } from "./hooks";
import {
  BUILTIN_TEMPLATES,
  CanvasPanel,
  type CanvasPanelHandle,
  type CanvasStats,
  type WorkspaceSaveState,
} from "./components/CanvasPanel";
import { SettingsModal, type SettingsTab } from "./components/SettingsModal";
import { TopBar } from "./components/TopBar";
import { AssetDrawer } from "./components/AssetDrawer";
import { ProjectManagerModal } from "./components/ProjectManagerModal";
import { api } from "./api";
import type { WorkspaceCanvasState, WorkspaceProject } from "./types";

const WORKSPACE_KEY = "fb_workspace_project";
const LEGACY_GRAPH_KEY = "fb_canvas_graph_v1";
const LEGACY_PINS_KEY = "fb_pinned_assets";
const DEFAULT_PROJECT_NAME = "Project Mặc định";

function readLegacyCanvas(): WorkspaceCanvasState | null {
  try {
    const raw = localStorage.getItem(LEGACY_GRAPH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { nodes?: unknown; groups?: unknown };
    if (!Array.isArray(parsed?.nodes)) return null;
    return {
      viewport: { x: 40, y: 20, zoom: 1 },
      nodes: parsed.nodes as WorkspaceCanvasState["nodes"],
      edges: [],
      groups: Array.isArray(parsed.groups)
        ? (parsed.groups as WorkspaceCanvasState["groups"])
        : [],
    };
  } catch {
    return null;
  }
}

function readLegacyPins(): string[] {
  try {
    const raw = localStorage.getItem(LEGACY_PINS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export default function App() {
  const { refresh: refreshStatus } = useStatus(5000);
  const { pool, refresh: refreshPool } = usePool(4000);
  const {
    projects: workspaceProjects,
    setProjects,
    loading: workspaceLoading,
    refresh: refreshWorkspaceProjects,
  } = useWorkspaceProjects();
  const {
    runs,
    loading: galleryLoading,
    error: galleryError,
    refresh: refreshGallery,
  } = useGallery();

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab>("gallery");
  const [projectManagerOpen, setProjectManagerOpen] = useState(false);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [projectSaveState, setProjectSaveState] = useState<WorkspaceSaveState>("idle");
  const [canvasStats, setCanvasStats] = useState<CanvasStats | null>(null);
  const [customTemplates, setCustomTemplates] = useState<{ id: string; name: string }[]>([]);
  const [assetScope, setAssetScope] = useState<"project" | "all">("project");

  const {
    uploaded: assetUploaded,
    outputs: assetOutputs,
    loadingUploaded: assetLoadingUploaded,
    loadingOutputs: assetLoadingOutputs,
    refreshUploaded: refreshAssetUploaded,
    refreshOutputs: refreshAssetOutputs,
    setPinned,
  } = useAssets(activeWorkspaceId, assetScope);

  const [assetDrawerOpen, setAssetDrawerOpen] = useState(false);

  // Auto-refresh asset lists whenever drawer opens (respecting current scope).
  useEffect(() => {
    if (assetDrawerOpen) {
      void refreshAssetUploaded();
      void refreshAssetOutputs();
    }
  }, [assetDrawerOpen, refreshAssetUploaded, refreshAssetOutputs]);

  // Global hotkey: 'A' to toggle asset drawer (unless typing in input/textarea)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement).isContentEditable
      ) {
        return;
      }
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        setAssetDrawerOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const canvasRef = useRef<CanvasPanelHandle>(null);
  const bootedRef = useRef(false);
  const canvasStatsRef = useRef<CanvasStats | null>(null);
  canvasStatsRef.current = canvasStats;

  const activeProject = useMemo(
    () => workspaceProjects.find((p) => p.id === activeWorkspaceId) ?? null,
    [workspaceProjects, activeWorkspaceId],
  );

  // -- Boot: one-time migration of localStorage canvas + pins ----------------
  useEffect(() => {
    if (workspaceLoading || bootedRef.current) return;
    bootedRef.current = true;
    void (async () => {
      const legacyCanvas = readLegacyCanvas();
      const legacyPins = readLegacyPins();
      try {
        const listing = await api.workspaceProjects();
        if (workspaceProjects.length === 0 || !listing.legacyMigrated) {
          await api.migrateWorkspace({
            name: DEFAULT_PROJECT_NAME,
            canvasState: legacyCanvas,
            pinnedIds: legacyPins,
          });
        } else if (legacyPins.length > 0) {
          await api.migrateWorkspace({ name: DEFAULT_PROJECT_NAME, pinnedIds: legacyPins });
        }
        // Server state is authoritative from here on; drop the legacy keys so
        // a later wipe can never be undone by stale browser data.
        localStorage.removeItem(LEGACY_GRAPH_KEY);
        localStorage.removeItem(LEGACY_PINS_KEY);
      } catch {
        // Keep legacy keys so a later reload can retry the migration.
      }

      const fresh = await refreshWorkspaceProjects();
      const saved = localStorage.getItem(WORKSPACE_KEY);
      const pick =
        fresh.find((p) => p.id === saved) ??
        fresh[0] ??
        null;
      setActiveWorkspaceId(pick?.id ?? null);
      setWorkspaceReady(true);
    })();
  }, [workspaceLoading, workspaceProjects.length, refreshWorkspaceProjects]);

  // Keep the active id valid when projects are added/removed elsewhere.
  useEffect(() => {
    if (!workspaceReady || workspaceProjects.length === 0) return;
    setActiveWorkspaceId((prev) => {
      if (prev && workspaceProjects.some((p) => p.id === prev)) return prev;
      const saved = localStorage.getItem(WORKSPACE_KEY);
      return (
        workspaceProjects.find((p) => p.id === saved)?.id ??
        workspaceProjects[0].id
      );
    });
  }, [workspaceProjects, workspaceReady]);

  useEffect(() => {
    if (activeWorkspaceId) localStorage.setItem(WORKSPACE_KEY, activeWorkspaceId);
  }, [activeWorkspaceId]);

  // -- project switching / CRUD ---------------------------------------------

  const confirmSwitchWhileRunning = useCallback((): boolean => {
    const stats = canvasStatsRef.current;
    const running = (stats?.nRunning ?? 0) > 0 || !!stats?.wfBusy;
    if (!running) return true;
    return window.confirm(
      "Canvas đang chạy workflow/node. Chuyển project bây giờ có thể làm mất dấu tiến trình đang chạy.\n\nBạn vẫn muốn chuyển?",
    );
  }, []);

  const handleSelectProject = useCallback(
    async (id: string) => {
      if (id === activeWorkspaceId) return;
      if (!confirmSwitchWhileRunning()) {
        throw new Error("Đã hủy chuyển project vì canvas đang chạy.");
      }
      await canvasRef.current?.flushSave();
      const fresh = await refreshWorkspaceProjects();
      if (!fresh.some((p) => p.id === id)) {
        throw new Error("Project không còn tồn tại.");
      }
      setProjectSaveState("saved");
      setActiveWorkspaceId(id);
    },
    [activeWorkspaceId, confirmSwitchWhileRunning, refreshWorkspaceProjects],
  );

  const handleCreateProject = useCallback(
    async (name: string, templateId: string | null): Promise<WorkspaceProject | null> => {
      await canvasRef.current?.flushSave();
      const canvasState = templateId
        ? canvasRef.current?.getTemplateCanvasState(templateId) ?? undefined
        : undefined;
      const res = await api.createWorkspaceProject({ name, canvasState });
      const fresh = await refreshWorkspaceProjects();
      const running = (canvasStatsRef.current?.nRunning ?? 0) > 0 || !!canvasStatsRef.current?.wfBusy;
      if (running) {
        // Keep the user on the running canvas; the new project is ready to open.
        window.alert(
          `Đã tạo project "${res.project.name}". Canvas hiện tại đang chạy nên chưa chuyển project — mở lại từ danh sách Project khi workflow xong.`,
        );
      } else {
        setProjectSaveState("saved");
        setActiveWorkspaceId(res.project.id);
      }
      return fresh.find((p) => p.id === res.project.id) ?? res.project;
    },
    [refreshWorkspaceProjects],
  );

  const handleRenameProject = useCallback(
    async (id: string, name: string) => {
      await api.updateWorkspaceProject(id, { name });
      await refreshWorkspaceProjects();
    },
    [refreshWorkspaceProjects],
  );

  const handleDuplicateProject = useCallback(
    async (id: string) => {
      await canvasRef.current?.flushSave();
      await api.duplicateWorkspaceProject(id);
      await refreshWorkspaceProjects();
    },
    [refreshWorkspaceProjects],
  );

  const handleSetThumbnail = useCallback(
    async (id: string, url: string | null) => {
      await api.setWorkspaceThumbnail(id, url);
      await refreshWorkspaceProjects();
    },
    [refreshWorkspaceProjects],
  );

  const handleDeleteProject = useCallback(
    async (id: string) => {
      if (id === activeWorkspaceId) {
        if (!confirmSwitchWhileRunning()) {
          throw new Error("Đã hủy xóa project vì canvas đang chạy.");
        }
        await canvasRef.current?.flushSave();
      }
      await api.deleteWorkspaceProject(id);
      const fresh = await refreshWorkspaceProjects();
      if (id === activeWorkspaceId) {
        setProjectSaveState("saved");
        setActiveWorkspaceId(fresh[0]?.id ?? null);
      }
    },
    [activeWorkspaceId, confirmSwitchWhileRunning, refreshWorkspaceProjects],
  );

  // Optimistically update project metadata after each autosave (no full rescan).
  const handleWorkspaceSaved = useCallback(
    (projectId: string) => {
      const nodeCount = canvasRef.current?.getCanvasState().nodes.length;
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId
            ? {
                ...p,
                updatedAt: Date.now(),
                nodeCount: nodeCount ?? p.nodeCount,
              }
            : p,
        ),
      );
    },
    [setProjects],
  );

  const handleOpenSettings = (tab: SettingsTab = "gallery") => {
    setSettingsInitialTab(tab);
    setSettingsOpen(true);
  };

  const templateOptions = useMemo(
    () => [
      ...BUILTIN_TEMPLATES.map((t) => ({ id: t.id, name: t.name })),
      ...customTemplates.map((t) => ({ id: t.id, name: t.name })),
    ],
    [customTemplates],
  );

  return (
    <div className="w-screen h-screen flex flex-col bg-ink overflow-hidden select-none">
      {/* Fixed top Header bar */}
      <TopBar
        onLoadTemplate={(name) => canvasRef.current?.loadTemplate(name)}
        onSaveTemplate={(name) => canvasRef.current?.saveCurrentTemplate(name)}
        onDeleteCustomTemplate={(id) => canvasRef.current?.deleteCustomTemplate(id)}
        customTemplates={customTemplates}
        onRunWorkflow={() => canvasRef.current?.openConfirmWorkflow()}
        canvasStats={canvasStats}
        onOpenSettings={() => handleOpenSettings("gallery")}
        onToggleAssetDrawer={() => setAssetDrawerOpen((v) => !v)}
        assetDrawerOpen={assetDrawerOpen}
        assetCount={assetUploaded.length + assetOutputs.length}
        currentProjectName={activeProject?.name ?? null}
        projectCount={workspaceProjects.length}
        projectSaveState={projectSaveState}
        onOpenProjectManager={() => setProjectManagerOpen(true)}
      />

      {/* Full-screen Canvas Workspace */}
      <main className="flex-1 min-h-0 w-full relative overflow-hidden">
        <CanvasPanel
          ref={canvasRef}
          workspaceProjectId={workspaceReady ? activeWorkspaceId : null}
          workspaceCanvasState={activeProject?.canvasState ?? null}
          onWorkspaceSaveState={setProjectSaveState}
          onWorkspaceSaved={handleWorkspaceSaved}
          onStatsChange={setCanvasStats}
          onTemplatesChange={setCustomTemplates}
          onAssetGenerated={() => {
            void refreshAssetOutputs();
            void refreshAssetUploaded();
            void refreshGallery();
            void refreshWorkspaceProjects();
          }}
        />
      </main>

      {/* Left Assets Drawer */}
      <AssetDrawer
        open={assetDrawerOpen}
        onClose={() => setAssetDrawerOpen(false)}
        uploaded={assetUploaded}
        outputs={assetOutputs}
        loadingUploaded={assetLoadingUploaded}
        loadingOutputs={assetLoadingOutputs}
        onRefreshUploaded={refreshAssetUploaded}
        onRefreshOutputs={refreshAssetOutputs}
        onInsertToCanvas={(item) => {
          canvasRef.current?.addReferenceNode(item.url, item.name);
        }}
        projectId={activeWorkspaceId}
        activeProjectName={activeProject?.name ?? null}
        scope={assetScope}
        onScopeChange={setAssetScope}
        onTogglePin={(item, pinned, kind) => {
          void setPinned(item, pinned, kind);
        }}
      />

      {/* Shared Settings & Utilities Modal (80vw x 80vh, Sidebar Layout) */}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        initialTab={settingsInitialTab}
        runs={runs}
        galleryLoading={galleryLoading}
        galleryError={galleryError}
        onRefreshGallery={() => void refreshGallery()}
        pool={pool}
        onRefreshPool={() => {
          refreshPool();
          refreshStatus();
        }}
        workspaceProjects={workspaceProjects}
      />

      {/* Project switcher / manager */}
      <ProjectManagerModal
        open={projectManagerOpen}
        onClose={() => setProjectManagerOpen(false)}
        projects={workspaceProjects}
        currentProjectId={activeWorkspaceId}
        templates={templateOptions}
        onSelect={handleSelectProject}
        onCreate={handleCreateProject}
        onRename={handleRenameProject}
        onDuplicate={handleDuplicateProject}
        onDelete={handleDeleteProject}
        onSetThumbnail={handleSetThumbnail}
        onRefresh={() => void refreshWorkspaceProjects()}
        busy={workspaceLoading}
      />
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useGallery, usePool, useProjects, useStatus } from "./hooks";
import { CanvasPanel, type CanvasPanelHandle, type CanvasStats } from "./components/CanvasPanel";
import { SettingsModal, type SettingsTab } from "./components/SettingsModal";
import { TopBar } from "./components/TopBar";

const PROJECT_KEY = "fb_project";

export default function App() {
  const { refresh: refreshStatus } = useStatus(5000);
  const { pool, refresh: refreshPool } = usePool(4000);
  const { projects } = useProjects();
  const {
    runs,
    loading: galleryLoading,
    error: galleryError,
    refresh: refreshGallery,
  } = useGallery();

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab>("gallery");
  const [selectedId, setSelectedId] = useState<string | null>(
    () => localStorage.getItem(PROJECT_KEY) || null,
  );
  const [canvasStats, setCanvasStats] = useState<CanvasStats | null>(null);

  const canvasRef = useRef<CanvasPanelHandle>(null);

  useEffect(() => {
    if (!selectedId && projects.length > 0) setSelectedId(projects[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects.length > 0]);

  useEffect(() => {
    if (selectedId) localStorage.setItem(PROJECT_KEY, selectedId);
    else localStorage.removeItem(PROJECT_KEY);
  }, [selectedId]);

  const handleOpenSettings = (tab: SettingsTab = "gallery") => {
    setSettingsInitialTab(tab);
    setSettingsOpen(true);
  };

  return (
    <div className="w-screen h-screen flex flex-col bg-ink overflow-hidden select-none">
      {/* Fixed top Header bar */}
      <TopBar
        onLoadTemplate={(name) => canvasRef.current?.loadTemplate(name)}
        onRunWorkflow={() => canvasRef.current?.openConfirmWorkflow()}
        canvasStats={canvasStats}
        onOpenSettings={() => handleOpenSettings("gallery")}
      />

      {/* Full-screen Canvas Workspace */}
      <main className="flex-1 min-h-0 w-full relative overflow-hidden">
        <CanvasPanel
          ref={canvasRef}
          projects={projects}
          selectedProjectId={selectedId}
          onStatsChange={setCanvasStats}
        />
      </main>

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
      />
    </div>
  );
}

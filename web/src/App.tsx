import { useEffect, useMemo, useState } from "react";
import { XCircle, X } from "@phosphor-icons/react";
import { api } from "./api";
import { useGallery, useJob, useProjects, useStatus } from "./hooks";
import type { Job } from "./types";
import { ComposePanel, type GenRequest } from "./components/ComposePanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { Gallery } from "./components/Gallery";
import { JobConsole } from "./components/JobConsole";
import { TopBar } from "./components/TopBar";

const PROJECT_KEY = "fb_project";

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function App() {
  const { status, refresh: refreshStatus } = useStatus(5000);
  const {
    projects,
    loading: projectsLoading,
    error: projectsError,
    refresh: refreshProjects,
  } = useProjects();
  const {
    runs,
    loading: galleryLoading,
    error: galleryError,
    refresh: refreshGallery,
  } = useGallery();

  const [selectedId, setSelectedId] = useState<string | null>(
    () => localStorage.getItem(PROJECT_KEY) || null,
  );
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [confirmReq, setConfirmReq] = useState<GenRequest | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dismissedProjectsError, setDismissedProjectsError] = useState(false);

  const onTerminal = useMemo(
    () => (j: Job) => {
      if (j.kind === "generate") refreshGallery(true);
      if (j.kind === "generate" || j.kind === "dry_run") refreshStatus();
      if (j.kind === "list_projects" || j.kind === "create_project") refreshProjects();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const job = useJob(activeJobId, onTerminal);

  // Default to the most recently used project once the registry loads.
  useEffect(() => {
    if (!selectedId && projects.length > 0) setSelectedId(projects[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects.length > 0]);

  useEffect(() => {
    if (selectedId) localStorage.setItem(PROJECT_KEY, selectedId);
    else localStorage.removeItem(PROJECT_KEY);
  }, [selectedId]);

  const busy = job ? job.state === "queued" || job.state === "running" : false;
  const bridgeReady = !!status?.cdp_ok;
  const selectedTitle = projects.find((p) => p.id === selectedId)?.title ?? null;

  const banner = actionError || (!dismissedProjectsError ? projectsError : null);

  const startJob = async (p: Promise<{ job_id: string }>) => {
    setActionError(null);
    try {
      const r = await p;
      setActiveJobId(r.job_id);
    } catch (e) {
      setActionError(msg(e));
    }
  };

  const submitDry = (req: GenRequest) => {
    void startJob(api.generate({ ...req, dry_run: true }));
  };

  const confirmRun = async () => {
    if (!confirmReq) return;
    setConfirmBusy(true);
    setActionError(null);
    try {
      const r = await api.generate({ ...confirmReq, confirm: true });
      setConfirmReq(null);
      setActiveJobId(r.job_id);
    } catch (e) {
      setActionError(msg(e));
      setConfirmReq(null);
    } finally {
      setConfirmBusy(false);
    }
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 lg:px-6 py-5 flex flex-col gap-5 min-h-full">
      <TopBar status={status} onRefresh={refreshStatus} />

      <div className="grid gap-5 lg:grid-cols-[400px_minmax(0,1fr)] items-start">
        <ComposePanel
          projects={projects}
          projectsLoading={projectsLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
          busy={busy}
          bridgeReady={bridgeReady}
          onRealRun={setConfirmReq}
          onDryRun={submitDry}
          onRefreshProjects={() => void startJob(api.refreshProjects())}
          onCreateProject={(title) => void startJob(api.createProject(title))}
          onAddProject={async (ref) => {
            await api.addProject(ref);
            await refreshProjects();
          }}
        />

        <div className="flex flex-col gap-3 min-w-0">
          {banner ? (
            <div className="flex items-start gap-2.5 rounded-ctl border border-err/30 bg-err/5 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-err">
              <XCircle size={16} className="mt-0.5 shrink-0" />
              <span className="min-w-0 break-words">{banner}</span>
              <button
                aria-label="Đóng thông báo"
                className="ml-auto shrink-0 text-err/70 hover:text-err"
                onClick={() => {
                  setActionError(null);
                  setDismissedProjectsError(true);
                }}
              >
                <X size={15} />
              </button>
            </div>
          ) : null}

          <JobConsole job={job} onUseProject={setSelectedId} />
        </div>
      </div>

      <Gallery
        runs={runs}
        loading={galleryLoading}
        error={galleryError}
        onRefresh={() => void refreshGallery()}
      />

      <footer className="flex flex-wrap items-center justify-between gap-2 pt-2 pb-4 text-[11.5px] text-mut">
        <p>
          Flow Bench · bridge mode qua CloakBrowser (CDP 9222). Mọi lần chạy thật đều cần bạn xác
          nhận trước.
        </p>
        <p className="font-mono">v0.1</p>
      </footer>

      <ConfirmDialog
        payload={confirmReq}
        projectTitle={selectedTitle}
        busy={confirmBusy}
        onCancel={() => setConfirmReq(null)}
        onConfirm={() => void confirmRun()}
      />
    </div>
  );
}

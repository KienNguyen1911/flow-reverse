import { useEffect, useMemo, useState } from "react";
import { BookOpen, Images, Sparkle, Users } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { api } from "./api";
import { useGallery, useJob, usePool, useProjects, useStatus } from "./hooks";
import type { Job } from "./types";
import { AccountPanel } from "./components/AccountPanel";
import { ComposePanel, type BatchRequest, type GenRequest } from "./components/ComposePanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { Gallery } from "./components/Gallery";
import { GuidePanel } from "./components/GuidePanel";
import { JobConsole } from "./components/JobConsole";
import { Tabs } from "./components/ui";
import { TopBar } from "./components/TopBar";

const PROJECT_KEY = "fb_project";

type TabKey = "compose" | "gallery" | "accounts" | "guide";

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function App() {
  const { status, refresh: refreshStatus } = useStatus(5000);
  const { pool, refresh: refreshPool } = usePool(4000);
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

  const [activeTab, setActiveTab] = useState<TabKey>("compose");
  const [selectedId, setSelectedId] = useState<string | null>(
    () => localStorage.getItem(PROJECT_KEY) || null,
  );
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [confirmReq, setConfirmReq] = useState<GenRequest | null>(null);
  const [confirmBatch, setConfirmBatch] = useState<BatchRequest | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dismissedProjectsError, setDismissedProjectsError] = useState(false);

  const reduceMotion = useReducedMotion();

  const onTerminal = useMemo(
    () => (j: Job) => {
      if (j.kind === "generate" || j.kind === "batch_generate") refreshGallery(true);
      if (j.kind === "generate" || j.kind === "dry_run" || j.kind === "batch_generate") {
        refreshStatus();
        refreshPool();
      }
      if (j.kind === "list_projects" || j.kind === "create_project") refreshProjects();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const job = useJob(activeJobId, onTerminal);

  useEffect(() => {
    if (!selectedId && projects.length > 0) setSelectedId(projects[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects.length > 0]);

  useEffect(() => {
    if (selectedId) localStorage.setItem(PROJECT_KEY, selectedId);
    else localStorage.removeItem(PROJECT_KEY);
  }, [selectedId]);

  // Keyboard shortcuts: Alt+1-4 to switch tabs
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      const idx = ["1", "2", "3", "4"].indexOf(e.key);
      if (idx === -1) return;
      const tabs: TabKey[] = ["compose", "gallery", "accounts", "guide"];
      setActiveTab(tabs[idx]);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const busy = job ? job.state === "queued" || job.state === "running" : false;
  const bridgeReady = !!status?.cdp_ok || (pool?.n_total ?? 0) > 0;
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

  const submitBatchDry = (req: BatchRequest) => {
    void startJob(api.batch({ ...req, dry_run: true }));
  };

  const cancelConfirm = () => {
    setConfirmReq(null);
    setConfirmBatch(null);
  };

  const confirmRun = async () => {
    if (!confirmReq && !confirmBatch) return;
    setConfirmBusy(true);
    setActionError(null);
    try {
      const r = confirmBatch
        ? await api.batch({ ...confirmBatch, confirm: true })
        : await api.generate({ ...confirmReq!, confirm: true });
      setConfirmReq(null);
      setConfirmBatch(null);
      setActiveJobId(r.job_id);
    } catch (e) {
      setActionError(msg(e));
      cancelConfirm();
    } finally {
      setConfirmBusy(false);
    }
  };

  const activeCount = pool?.working_set.length ?? 0;

  const tabs = useMemo(
    () => [
      { key: "compose" as TabKey, label: "Tao anh", icon: <Sparkle size={15} /> },
      { key: "gallery" as TabKey, label: "Thu vien", icon: <Images size={15} /> },
      {
        key: "accounts" as TabKey,
        label: "Tai khoan",
        icon: <Users size={15} />,
        badge: pool && activeCount > 0 ? String(activeCount) : undefined,
      },
      { key: "guide" as TabKey, label: "Huong dan", icon: <BookOpen size={15} /> },
    ],
    [pool, activeCount],
  );

  return (
    <div className="max-w-[1240px] mx-auto px-4 lg:px-6 py-5 flex flex-col gap-4 min-h-full">
      <TopBar
        status={status}
        pool={pool}
        onRefresh={() => {
          refreshStatus();
          refreshPool();
        }}
        onOpenAccounts={() => setActiveTab("accounts")}
      />

      <div className="rounded-panel border border-line bg-panel overflow-hidden">
        <Tabs tabs={tabs} active={activeTab} onChange={(key) => setActiveTab(key as TabKey)} />

        <div className="min-h-[60vh]">
          {activeTab === "compose" && (
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="p-4 sm:p-5"
            >
              <div className="grid gap-5 lg:grid-cols-[400px_minmax(0,1fr)] items-start">
                <ComposePanel
                  projects={projects}
                  projectsLoading={projectsLoading}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  busy={busy}
                  bridgeReady={bridgeReady}
                  pool={pool}
                  onRealRun={setConfirmReq}
                  onDryRun={submitDry}
                  onBatchRun={setConfirmBatch}
                  onBatchDryRun={submitBatchDry}
                  onSavePoolConfig={(q) => {
                    void api
                      .poolConfig({ target_jobs_per_account: q })
                      .then(() => refreshPool())
                      .catch((e) => setActionError(msg(e)));
                  }}
                  onRefreshProjects={() => void startJob(api.refreshProjects())}
                  onCreateProject={(title) => void startJob(api.createProject(title))}
                  onAddProject={async (ref) => {
                    await api.addProject(ref);
                    await refreshProjects();
                  }}
                  onOpenGuide={() => setActiveTab("guide")}
                />

                <div className="flex flex-col gap-3 min-w-0">
                  {banner ? (
                    <div className="flex items-start gap-2.5 rounded-ctl border border-err/30 bg-err/5 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-err">
                      <span className="min-w-0 break-words">{banner}</span>
                      <button
                        aria-label="Dong thong bao"
                        className="ml-auto shrink-0 text-err/70 hover:text-err cursor-pointer"
                        onClick={() => {
                          setActionError(null);
                          setDismissedProjectsError(true);
                        }}
                      >
                        &times;
                      </button>
                    </div>
                  ) : null}

                  <JobConsole job={job} onUseProject={setSelectedId} />
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === "gallery" && (
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="p-4 sm:p-5"
            >
              <Gallery
                runs={runs}
                loading={galleryLoading}
                error={galleryError}
                onRefresh={() => void refreshGallery()}
              />
            </motion.div>
          )}

          {activeTab === "accounts" && (
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <AccountPanel
                pool={pool}
                onRefreshPool={() => {
                  refreshPool();
                  refreshStatus();
                }}
              />
            </motion.div>
          )}

          {activeTab === "guide" && (
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <GuidePanel />
            </motion.div>
          )}
        </div>
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-2 pt-2 pb-4 text-[11.5px] text-mut">
        <p>
          Flow Bench - bridge mode qua CloakBrowser (pool N tai khoan, browser mo theo nhu cau). Moi
          lan chay that deu can ban xac nhan truoc.
        </p>
        <p className="font-mono">v0.2</p>
      </footer>

      <ConfirmDialog
        payload={confirmReq ?? confirmBatch}
        projectTitle={selectedTitle}
        pool={pool}
        busy={confirmBusy}
        onCancel={cancelConfirm}
        onConfirm={() => void confirmRun()}
      />
    </div>
  );
}

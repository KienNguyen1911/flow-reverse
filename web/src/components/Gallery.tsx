import { useMemo, useState } from "react";
import { ArrowClockwise, FolderSimple, ImageSquare } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import type { GalleryRun, WorkspaceProject } from "../types";
import { IconBtn, Panel } from "./ui";
import { Lightbox } from "./Lightbox";

function fmtDate(ts?: string | null) {
  if (!ts) return null;
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}`;
}

export function Gallery({
  runs,
  loading,
  error,
  onRefresh,
  projects = [],
}: {
  runs: GalleryRun[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  projects?: WorkspaceProject[];
}) {
  const reduce = useReducedMotion();
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [projectFilter, setProjectFilter] = useState<string>("all");

  const projectNames = useMemo(
    () => new Map(projects.map((p) => [p.id, p.name])),
    [projects],
  );

  const filteredRuns = useMemo(() => {
    if (projectFilter === "all") return runs;
    if (projectFilter === "__none__") return runs.filter((r) => !r.workspace_project_id);
    return runs.filter((r) => r.workspace_project_id === projectFilter);
  }, [runs, projectFilter]);

  const projectNameFor = (run: GalleryRun): string | null => {
    const id = run.workspace_project_id;
    if (!id) return null;
    return projectNames.get(id) || `Project ${id.slice(0, 8)}`;
  };

  return (
    <>
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-[14px] font-bold">Ảnh đã tạo</h2>
          <span className="font-mono text-[12px] text-mut">{filteredRuns.length}</span>

          <label className="ml-auto flex items-center gap-2 text-[11px] text-mut">
            <span className="whitespace-nowrap">Lọc theo Project:</span>
            <select
              value={projectFilter}
              onChange={(e) => {
                setProjectFilter(e.target.value);
                setLightboxIndex(null);
              }}
              className="h-8 max-w-[220px] rounded-ctl border border-line2 bg-panel2 px-2 text-[11.5px] text-fg focus:outline-none focus:border-acc/70 cursor-pointer"
              title="Chỉ hiện ảnh/video được tạo bởi một project"
            >
              <option value="all">Tất cả</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              <option value="__none__">Chưa gán project</option>
            </select>
          </label>

          <IconBtn label="Làm mới thư viện" onClick={onRefresh} disabled={loading}>
            <ArrowClockwise size={15} />
          </IconBtn>
        </div>

        {error ? <p className="text-[12px] text-err">{error}</p> : null}

        {loading && runs.length === 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-56 rounded-panel border border-line bg-panel animate-pulse" />
            ))}
          </div>
        ) : filteredRuns.length === 0 ? (
          <Panel className="p-8 grid place-items-center text-center">
            <div>
              <ImageSquare size={26} className="mx-auto text-mut" />
              <p className="mt-3 text-[13px] text-dim">
                {projectFilter === "all"
                  ? "Chưa có ảnh nào được tạo bằng playground."
                  : "Project này chưa có ảnh nào trong thư viện."}
              </p>
              <p className="mt-1 text-[12px] text-mut">
                Ảnh đầu tiên sẽ xuất hiện ở đây kèm seed và prompt.
              </p>
            </div>
          </Panel>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {filteredRuns.map((run, i) => {
              const projectName = projectNameFor(run);
              return (
                <motion.button
                  key={run.run}
                  type="button"
                  onClick={() => setLightboxIndex(i)}
                  initial={reduce ? false : { opacity: 0, y: 8 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.25) }}
                  className="group rounded-panel border border-line bg-panel overflow-hidden hover:border-acc/50 transition-colors cursor-pointer text-left"
                >
                  <div className="relative aspect-[16/9] bg-ink grid place-items-center overflow-hidden">
                    <img
                      src={run.url}
                      alt={run.prompt ?? "Ảnh"}
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                    />
                    {projectName && (
                      <span
                        className="absolute top-2 left-2 inline-flex items-center gap-1 max-w-[80%] truncate px-1.5 py-0.5 rounded bg-black/65 text-[9px] font-semibold text-white/85 border border-white/10"
                        title={`Project: ${projectName}`}
                      >
                        <FolderSimple size={9} weight="fill" className="shrink-0" />
                        <span className="truncate">{projectName}</span>
                      </span>
                    )}
                    {run.is_pinned && (
                      <span className="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-acc text-accink text-[9px] font-bold">
                        📌 Đã ghim
                      </span>
                    )}
                  </div>
                  <div className="p-4 flex flex-col gap-2">
                    <p className="text-[12.5px] leading-snug text-dim line-clamp-2">
                      {run.prompt || "(không có prompt)"}
                    </p>
                    <div className="flex items-center gap-2 text-[11px] text-mut font-mono">
                      <span>seed {run.seed_echo ?? run.seed ?? "?"}</span>
                      {run.resolution && run.resolution.length >= 2 ? (
                        <span>
                          {run.resolution[0]}x{run.resolution[1]}
                        </span>
                      ) : null}
                      <span className="ml-auto">{fmtDate(run.created_ts)}</span>
                    </div>
                  </div>
                </motion.button>
              );
            })}
          </div>
        )}
      </section>

      {lightboxIndex !== null && (
        <Lightbox
          runs={filteredRuns}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </>
  );
}

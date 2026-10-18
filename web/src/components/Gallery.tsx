import { ArrowClockwise, ImageSquare } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import type { GalleryRun } from "../types";
import { IconBtn, Panel } from "./ui";

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
}: {
  runs: GalleryRun[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const reduce = useReducedMotion();

  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex items-center gap-3">
        <h2 className="text-[14px] font-bold">Ảnh đã tạo</h2>
        <span className="font-mono text-[12px] text-mut">{runs.length}</span>
        <div className="ml-auto">
          <IconBtn label="Làm mới thư viện" onClick={onRefresh} disabled={loading}>
            <ArrowClockwise size={15} />
          </IconBtn>
        </div>
      </div>

      {error ? <p className="text-[12px] text-err">{error}</p> : null}

      {loading && runs.length === 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-52 rounded-panel border border-line bg-panel animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <Panel className="p-8 grid place-items-center text-center">
          <div>
            <ImageSquare size={26} className="mx-auto text-mut" />
            <p className="mt-3 text-[13px] text-dim">Chưa có ảnh nào được tạo bằng playground.</p>
            <p className="mt-1 text-[12px] text-mut">
              Ảnh đầu tiên sẽ xuất hiện ở đây kèm seed và prompt.
            </p>
          </div>
        </Panel>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {runs.map((run, i) => (
            <motion.a
              key={run.run}
              href={run.url}
              target="_blank"
              rel="noopener noreferrer"
              initial={reduce ? false : { opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.25) }}
              className="group rounded-panel border border-line bg-panel overflow-hidden hover:border-line2 transition-colors"
            >
              <div className="aspect-[16/9] bg-ink grid place-items-center overflow-hidden">
                <img
                  src={run.url}
                  alt={run.prompt ?? "Ảnh"}
                  loading="lazy"
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                />
              </div>
              <div className="p-3 flex flex-col gap-1.5">
                <p className="text-[12.5px] leading-snug text-dim line-clamp-2">
                  {run.prompt || "(không có prompt)"}
                </p>
                <div className="flex items-center gap-2 text-[11px] text-mut font-mono">
                  <span>seed {run.seed_echo ?? run.seed ?? "?"}</span>
                  {run.resolution && run.resolution.length >= 2 ? (
                    <span>
                      {run.resolution[0]}×{run.resolution[1]}
                    </span>
                  ) : null}
                  <span className="ml-auto">{fmtDate(run.created_ts)}</span>
                </div>
              </div>
            </motion.a>
          ))}
        </div>
      )}
    </section>
  );
}

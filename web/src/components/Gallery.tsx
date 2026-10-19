import { useState } from "react";
import { ArrowClockwise, ImageSquare } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import type { GalleryRun } from "../types";
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
}: {
  runs: GalleryRun[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const reduce = useReducedMotion();
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  return (
    <>
      <section className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <h2 className="text-[14px] font-bold">Anh da tao</h2>
          <span className="font-mono text-[12px] text-mut">{runs.length}</span>
          <div className="ml-auto">
            <IconBtn label="Lam moi thu vien" onClick={onRefresh} disabled={loading}>
              <ArrowClockwise size={15} />
            </IconBtn>
          </div>
        </div>

        {error ? <p className="text-[12px] text-err">{error}</p> : null}

        {loading && runs.length === 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-56 rounded-panel border border-line bg-panel animate-pulse" />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <Panel className="p-8 grid place-items-center text-center">
            <div>
              <ImageSquare size={26} className="mx-auto text-mut" />
              <p className="mt-3 text-[13px] text-dim">Chua co anh nao duoc tao bang playground.</p>
              <p className="mt-1 text-[12px] text-mut">
                Anh dau tien se xuat hien o day kem seed va prompt.
              </p>
            </div>
          </Panel>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {runs.map((run, i) => (
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
                <div className="aspect-[16/9] bg-ink grid place-items-center overflow-hidden">
                  <img
                    src={run.url}
                    alt={run.prompt ?? "Anh"}
                    loading="lazy"
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                  />
                </div>
                <div className="p-4 flex flex-col gap-2">
                  <p className="text-[12.5px] leading-snug text-dim line-clamp-2">
                    {run.prompt || "(khong co prompt)"}
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
            ))}
          </div>
        )}
      </section>

      {lightboxIndex !== null && (
        <Lightbox
          runs={runs}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </>
  );
}

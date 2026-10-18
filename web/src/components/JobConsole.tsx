import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { Job } from "../types";
import { ResultCard } from "./ResultCard";
import { Spinner } from "./ui";

const KIND_CLS: Record<string, string> = {
  step: "text-dim",
  info: "text-dim",
  capture: "text-acc",
  fired: "text-acc",
  response: "text-acc",
  download: "text-ok",
  done: "text-ok",
  warn: "text-warn",
  retry: "text-warn",
  error: "text-err",
  debug: "text-mut",
};

const STATE_META: Record<string, { label: string; cls: string; live?: boolean }> = {
  queued: { label: "Đang chờ", cls: "text-dim border-line2" },
  running: { label: "Đang chạy", cls: "text-acc border-acc/40", live: true },
  succeeded: { label: "Hoàn tất", cls: "text-ok border-ok/40" },
  rejected: { label: "Bị từ chối", cls: "text-warn border-warn/40" },
  failed: { label: "Lỗi", cls: "text-err border-err/40" },
};

function hhmmss(ts: number) {
  return new Date(ts).toTimeString().slice(0, 8);
}

export function JobConsole({
  job,
  onUseProject,
}: {
  job: Job | null;
  onUseProject: (id: string) => void;
}) {
  const reduce = useReducedMotion();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const running = job?.state === "running" || job?.state === "queued";
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [job?.state]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (near) el.scrollTop = el.scrollHeight;
  }, [job?.event_count, job?.state]);

  const events = job?.events ?? [];
  const meta = job ? STATE_META[job.state] : null;

  let elapsed: string | null = null;
  if (job?.started_ms) {
    const end = job.finished_ms ?? now;
    elapsed = ((end - job.started_ms) / 1000).toFixed(1) + "s";
  }

  return (
    <section className="rounded-panel border border-line bg-panel flex flex-col min-h-[420px]">
      <header className="flex items-center gap-3 border-b border-line px-4 lg:px-5 h-12 shrink-0">
        <h2 className="text-[12.5px] font-semibold text-dim">Nhật ký</h2>
        {job ? (
          <span className="font-mono text-[11px] text-mut truncate" title={job.id}>
            {job.id}
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-2.5">
          {elapsed ? <span className="font-mono text-[11px] text-mut">{elapsed}</span> : null}
          {meta ? (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 h-6 text-[11px] font-medium ${meta.cls}`}
            >
              {meta.live ? <Spinner size={11} /> : null}
              {meta.label}
            </span>
          ) : null}
        </div>
      </header>

      <div
        ref={scrollRef}
        className="slim-scroll flex-1 overflow-y-auto px-4 lg:px-5 py-3 font-mono text-[11.5px] leading-[1.7] max-h-[380px]"
      >
        {events.length === 0 ? (
          <div className="h-full min-h-[200px] grid place-items-center">
            <div className="text-center max-w-[440px]">
              <p className="font-sans text-[13px] text-dim">Chưa có job nào.</p>
              <p className="mt-1.5 font-sans text-[12px] leading-relaxed text-mut">
                Nhập prompt rồi bấm Dry-run để kiểm tra pipeline (0 credit), hoặc Tạo ảnh để chạy
                thật (khoảng 1 credit nếu được nhận).
              </p>
            </div>
          </div>
        ) : (
          events.map((e) => (
            <motion.div
              key={e.i}
              initial={reduce ? false : { opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
              className="flex gap-2 whitespace-pre-wrap break-words"
            >
              <span className="text-mut shrink-0">{hhmmss(e.ts_ms)}</span>
              <span className={`shrink-0 min-w-[58px] font-semibold ${KIND_CLS[e.kind] ?? "text-dim"}`}>
                {e.kind}
              </span>
              <span className="text-fg/85 min-w-0">{e.message}</span>
            </motion.div>
          ))
        )}
      </div>

      {job && (job.state === "succeeded" || job.state === "rejected" || job.state === "failed") ? (
        <div className="border-t border-line p-4 lg:p-5 shrink-0">
          <ResultCard job={job} onUseProject={onUseProject} />
        </div>
      ) : null}
    </section>
  );
}

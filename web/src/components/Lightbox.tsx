import { useCallback, useEffect } from "react";
import { CaretLeft, CaretRight, X } from "@phosphor-icons/react";
import type { GalleryRun } from "../types";

interface Props {
  runs: GalleryRun[];
  index: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

export function Lightbox({ runs, index, onClose, onNavigate }: Props) {
  const run = runs[index];
  const total = runs.length;

  const goPrev = useCallback(() => {
    onNavigate((index - 1 + total) % total);
  }, [index, total, onNavigate]);

  const goNext = useCallback(() => {
    onNavigate((index + 1) % total);
  }, [index, total, onNavigate]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, goPrev, goNext]);

  if (!run) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <span className="font-mono text-[13px] text-white/70">
          {index + 1} / {total}
        </span>
        <button
          onClick={onClose}
          className="inline-grid place-items-center size-10 rounded-full bg-white/10 text-white/80 hover:bg-white/20 hover:text-white transition-colors cursor-pointer"
          aria-label="Dong"
        >
          <X size={20} />
        </button>
      </div>

      {/* Main image */}
      <div className="flex-1 flex items-center justify-center min-h-0 px-16 sm:px-20 relative">
        {/* Prev button */}
        <button
          onClick={(e) => { e.stopPropagation(); goPrev(); }}
          className="absolute left-3 sm:left-6 top-1/2 -translate-y-1/2 inline-grid place-items-center size-12 rounded-full bg-white/10 text-white/80 hover:bg-white/25 hover:text-white transition-all hover:scale-105 active:scale-95 cursor-pointer"
          aria-label="Anh truoc"
        >
          <CaretLeft size={28} weight="bold" />
        </button>

        <img
          src={run.url}
          alt={run.prompt ?? "Anh"}
          className="max-h-full max-w-full object-contain rounded-lg shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        />

        {/* Next button */}
        <button
          onClick={(e) => { e.stopPropagation(); goNext(); }}
          className="absolute right-3 sm:right-6 top-1/2 -translate-y-1/2 inline-grid place-items-center size-12 rounded-full bg-white/10 text-white/80 hover:bg-white/25 hover:text-white transition-all hover:scale-105 active:scale-95 cursor-pointer"
          aria-label="Anh sau"
        >
          <CaretRight size={28} weight="bold" />
        </button>
      </div>

      {/* Footer info */}
      <div className="shrink-0 px-4 py-4 flex flex-col gap-1.5 text-center">
        <p className="text-[13px] text-white/90 leading-snug line-clamp-2 max-w-2xl mx-auto">
          {run.prompt || "(khong co prompt)"}
        </p>
        <div className="flex items-center justify-center gap-3 text-[11.5px] text-white/50 font-mono">
          <span>seed {run.seed_echo ?? run.seed ?? "?"}</span>
          {run.resolution && run.resolution.length >= 2 ? (
            <span>{run.resolution[0]}x{run.resolution[1]}</span>
          ) : null}
        </div>
        <p className="text-[11px] text-white/40 mt-1">
          Dung de dong - Arrow Left/Right de dieu huong
        </p>
      </div>
    </div>
  );
}

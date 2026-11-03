import { useMemo, useState } from "react";
import { ArrowClockwise, Clock, DownloadSimple, Eye, FilmStrip, MagnifyingGlass, X } from "@phosphor-icons/react";
import type { TryOnRunManifest } from "../../types";
import type { HistoryStatusFilter } from "./types";
import { formatDuration } from "./format";
import { Panel } from "../ui";

/** Search + status filter state for the history gallery (kept by the parent so it survives view switches). */
export function useHistoryFilter(historyRuns: TryOnRunManifest[]) {
  const [historySearch, setHistorySearch] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState<HistoryStatusFilter>("all");

  // Filtered history runs
  const filteredRuns = useMemo(() => {
    return historyRuns.filter((r) => {
      const matchSearch =
        !historySearch ||
        r.run_id.toLowerCase().includes(historySearch.toLowerCase()) ||
        (r.video_prompt_1 && r.video_prompt_1.toLowerCase().includes(historySearch.toLowerCase())) ||
        (r.product_title && r.product_title.toLowerCase().includes(historySearch.toLowerCase()));
      const matchStatus =
        historyStatusFilter === "all" ||
        (historyStatusFilter === "succeeded" && r.status === "succeeded") ||
        (historyStatusFilter === "failed" && r.status !== "succeeded");
      return matchSearch && matchStatus;
    });
  }, [historyRuns, historySearch, historyStatusFilter]);

  return { historySearch, setHistorySearch, historyStatusFilter, setHistoryStatusFilter, filteredRuns };
}

export type HistoryFilter = ReturnType<typeof useHistoryFilter>;

interface Props {
  runs: TryOnRunManifest[];
  filter: HistoryFilter;
  onRefresh: () => void;
  onViewRun: (run: TryOnRunManifest) => void;
  onReuse: (run: TryOnRunManifest) => void;
}

/** Full history gallery of past try-on runs with search and status filters. */
export function HistoryGallery({ runs, filter, onRefresh, onViewRun, onReuse }: Props) {
  const { historySearch, setHistorySearch, historyStatusFilter, setHistoryStatusFilter, filteredRuns } = filter;

  return (
    <div className="flex flex-col gap-4 flex-1">
      <Panel className="p-4 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
          <div>
            <h3 className="text-[15px] font-bold text-fg flex items-center gap-2">
              <Clock size={18} className="text-acc" />
              <span>Kho Lưu Trữ Lịch Sử Video Thử Đồ</span>
            </h3>
            <p className="text-[12px] text-mut mt-0.5">
              Tất cả các bản dựng video 16s, khung hình First/Last Frame và kịch bản đã tạo.
            </p>
          </div>

          {/* Search & Filter Controls */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <MagnifyingGlass
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mut"
              />
              <input
                type="text"
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                placeholder="Tìm theo Run ID, prompt..."
                className="h-8 pl-8 pr-3 rounded-ctl border border-line2 bg-panel2 text-[11.5px] text-fg focus:border-acc outline-none w-48 sm:w-60"
              />
              {historySearch && (
                <button
                  onClick={() => setHistorySearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-mut hover:text-fg cursor-pointer"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            <div className="flex items-center gap-1 bg-panel2 p-0.5 rounded-ctl border border-line text-[11.5px]">
              <button
                onClick={() => setHistoryStatusFilter("all")}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  historyStatusFilter === "all" ? "bg-panel text-fg font-semibold" : "text-mut hover:text-fg"
                }`}
              >
                Tất cả ({runs.length})
              </button>
              <button
                onClick={() => setHistoryStatusFilter("succeeded")}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  historyStatusFilter === "succeeded" ? "bg-ok/15 text-ok font-semibold" : "text-mut hover:text-fg"
                }`}
              >
                Thành công
              </button>
              <button
                onClick={() => setHistoryStatusFilter("failed")}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  historyStatusFilter === "failed" ? "bg-err/15 text-err font-semibold" : "text-mut hover:text-fg"
                }`}
              >
                Lỗi
              </button>
            </div>

            <button
              onClick={() => onRefresh()}
              className="size-8 rounded-ctl border border-line2 bg-panel2 text-dim hover:text-fg grid place-items-center cursor-pointer"
              title="Làm mới lịch sử"
            >
              <ArrowClockwise size={15} />
            </button>
          </div>
        </div>

        {/* Gallery Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredRuns.map((run) => (
            <div
              key={run.run_id}
              className="rounded-ctl border border-line2 bg-panel2/60 hover:bg-panel2 p-3 flex flex-col justify-between gap-3 transition-all hover:border-acc/40 group"
            >
              <div className="flex flex-col gap-2">
                {/* Media Thumbnail or Video */}
                <div className="relative rounded-ctl overflow-hidden bg-black aspect-[3/4] max-h-[260px] border border-line flex items-center justify-center">
                  {run.final_video_url ? (
                    <video
                      src={run.final_video_url}
                      controls
                      className="size-full object-contain"
                      preload="metadata"
                    />
                  ) : run.first_frame_url ? (
                    <img
                      src={run.first_frame_url}
                      alt="First Frame"
                      className="size-full object-contain"
                    />
                  ) : (
                    <div className="text-mut text-[11px] grid place-items-center">
                      Không có media
                    </div>
                  )}

                  <span
                    className={`absolute top-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      run.status === "succeeded"
                        ? "bg-ok/90 text-black shadow-xs"
                        : "bg-err/90 text-white shadow-xs"
                    }`}
                  >
                    {run.status === "succeeded"
                      ? run.single_video || !run.video_2_url
                        ? "8s Hoàn chỉnh"
                        : "16s Hoàn chỉnh"
                      : "Lỗi"}
                  </span>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-mut font-mono">
                    <span className="font-bold text-fg truncate">{run.run_id}</span>
                    <span>{formatDuration(run.elapsed_s)}</span>
                  </div>
                  <p className="text-[11px] text-dim line-clamp-2 mt-1 leading-snug">
                    {run.video_prompt_1 || "(Không có prompt)"}
                  </p>
                </div>
              </div>

              {/* Actions Toolbar */}
              <div className="flex items-center justify-between gap-2 pt-2 border-t border-line text-[11.5px]">
                <button
                  onClick={() => onViewRun(run)}
                  className="inline-flex items-center gap-1.5 text-acc hover:underline font-semibold cursor-pointer"
                >
                  <Eye size={14} />
                  <span>Xem chi tiết</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onReuse(run)}
                    className="text-dim hover:text-fg text-[11px] cursor-pointer"
                    title="Tái sử dụng prompt và thiết lập"
                  >
                    Tái sử dụng
                  </button>
                  {run.final_video_url && (
                    <a
                      href={run.final_video_url}
                      download={`${run.run_id}_${run.single_video || !run.video_2_url ? "8s" : "16s"}.mp4`}
                      className="text-dim hover:text-fg p-1 rounded hover:bg-line"
                      title="Tải video"
                    >
                      <DownloadSimple size={14} />
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}

          {filteredRuns.length === 0 && (
            <div className="col-span-full py-16 text-center text-mut flex flex-col items-center justify-center">
              <FilmStrip size={40} className="opacity-30 mb-2" />
              <p className="text-[13px] font-medium text-dim">
                Không tìm thấy bản ghi lịch sử nào phù hợp
              </p>
              <p className="text-[11.5px] text-mut mt-1">
                Thử tìm kiếm với từ khóa khác hoặc chuyển sang tab Studio để tạo video mới.
              </p>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

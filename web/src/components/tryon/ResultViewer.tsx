import { Check, Copy, DownloadSimple, Image as ImageIcon, VideoCamera } from "@phosphor-icons/react";
import type { TryOnRunManifest } from "../../types";
import type { ResultTab } from "./types";

interface Props {
  activeResult: TryOnRunManifest;
  resultTab: ResultTab;
  onResultTabChange: (tab: ResultTab) => void;
  copiedKey: string | null;
  onCopyPrompt: (text: string, key: string) => void;
}

/** Completed-run viewer with final video, sub-videos, key frames and prompt tabs. */
export function ResultViewer({ activeResult, resultTab, onResultTabChange, copiedKey, onCopyPrompt }: Props) {
  return (
    <div className="flex flex-col gap-3 pt-1">
      {/* Sub-tabs */}
      <div className="flex items-center gap-1.5 border-b border-line2 pb-2">
        <button
          onClick={() => onResultTabChange("final")}
          className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
            resultTab === "final"
              ? "bg-panel2 text-acc border border-line2"
              : "text-mut hover:text-fg"
          }`}
        >
          {activeResult.single_video || !activeResult.video_2_url
            ? "Video 8s Hoàn Chỉnh"
            : "Video 16s Hoàn Chỉnh"}
        </button>
        {!activeResult.single_video && activeResult.video_2_url && (
          <button
            onClick={() => onResultTabChange("subvideos")}
            className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
              resultTab === "subvideos"
                ? "bg-panel2 text-acc border border-line2"
                : "text-mut hover:text-fg"
            }`}
          >
            Video 1 & 2 (8s + 8s)
          </button>
        )}
        <button
          onClick={() => onResultTabChange("frames")}
          className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
            resultTab === "frames"
              ? "bg-panel2 text-acc border border-line2"
              : "text-mut hover:text-fg"
          }`}
        >
          {activeResult.single_video || !activeResult.last_frame_url
            ? "Ảnh First Frame"
            : "Khung hình First & Last Frame"}
        </button>
        <button
          onClick={() => onResultTabChange("prompts")}
          className={`px-3 py-1 text-[11.5px] font-semibold rounded-ctl transition-colors cursor-pointer ${
            resultTab === "prompts"
              ? "bg-panel2 text-acc border border-line2"
              : "text-mut hover:text-fg"
          }`}
        >
          Kịch Bản Prompts
        </button>
      </div>

      {/* TAB 1: FINAL 16S VIDEO */}
      {resultTab === "final" && (
        <div className="flex flex-col items-center justify-center">
          {activeResult.final_video_url ? (
            <div className="rounded-panel overflow-hidden bg-black/90 border border-line flex items-center justify-center w-full max-h-[480px]">
              <video
                controls
                src={activeResult.final_video_url}
                className="max-h-[480px] w-auto max-w-full object-contain"
                autoPlay
                muted
                loop
                playsInline
              />
            </div>
          ) : (
            <div className="p-8 text-center text-mut rounded-ctl bg-panel2 w-full">
              <VideoCamera size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-[12.5px] font-medium text-dim">
                Chưa có file video 16s đã nối hoàn chỉnh.
              </p>
              <p className="text-[11px] text-mut mt-1">
                Kiểm tra các video con 8s ở tab "Video 1 & 2".
              </p>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: SUB-VIDEOS */}
      {resultTab === "subvideos" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Video 1 */}
          <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                <VideoCamera size={13} className="text-acc" />
                <span>Video 1 (0-8s)</span>
              </span>
              {activeResult.video_1_url && (
                <a
                  href={activeResult.video_1_url}
                  download="video_1.mp4"
                  className="text-mut hover:text-fg"
                  title="Tải Video 1"
                >
                  <DownloadSimple size={13} />
                </a>
              )}
            </div>
            {activeResult.video_1_url ? (
              <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                <video
                  controls
                  src={activeResult.video_1_url}
                  className="max-h-[62vh] w-auto max-w-full object-contain"
                  playsInline
                />
              </div>
            ) : (
              <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                Chưa có Video 1
              </div>
            )}
          </div>

          {/* Video 2 */}
          <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                <VideoCamera size={13} className="text-ok" />
                <span>Video 2 (8-16s)</span>
              </span>
              {activeResult.video_2_url && (
                <a
                  href={activeResult.video_2_url}
                  download="video_2.mp4"
                  className="text-mut hover:text-fg"
                  title="Tải Video 2"
                >
                  <DownloadSimple size={13} />
                </a>
              )}
            </div>
            {activeResult.video_2_url ? (
              <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                <video
                  controls
                  src={activeResult.video_2_url}
                  className="max-h-[62vh] w-auto max-w-full object-contain"
                  playsInline
                />
              </div>
            ) : (
              <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                Chưa có Video 2
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: KEYFRAMES COMPARISON */}
      {resultTab === "frames" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* First Frame */}
          <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                <ImageIcon size={13} className="text-acc" />
                <span>First Frame (Khởi đầu Video 1)</span>
              </span>
              {activeResult.first_frame_url && (
                <a
                  href={activeResult.first_frame_url}
                  download="first_frame.png"
                  className="text-mut hover:text-fg"
                  title="Tải First Frame"
                >
                  <DownloadSimple size={13} />
                </a>
              )}
            </div>
            {activeResult.first_frame_url ? (
              <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                <img
                  src={activeResult.first_frame_url}
                  alt="First Frame"
                  className="max-h-[62vh] w-auto max-w-full object-contain"
                />
              </div>
            ) : (
              <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                Không có ảnh First Frame
              </div>
            )}
          </div>

          {/* Last Frame */}
          <div className="flex flex-col gap-1.5 p-2.5 rounded-ctl bg-panel2 border border-line">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
                <ImageIcon size={13} className="text-ok" />
                <span>Last Frame Video 1 (FFmpeg cắt)</span>
              </span>
              {activeResult.last_frame_url && (
                <a
                  href={activeResult.last_frame_url}
                  download="last_frame_video_1.png"
                  className="text-mut hover:text-fg"
                  title="Tải Last Frame"
                >
                  <DownloadSimple size={13} />
                </a>
              )}
            </div>
            {activeResult.last_frame_url ? (
              <div className="rounded-ctl overflow-hidden bg-black border border-line2 flex items-center justify-center">
                <img
                  src={activeResult.last_frame_url}
                  alt="Last Frame"
                  className="max-h-[62vh] w-auto max-w-full object-contain"
                />
              </div>
            ) : (
              <div className="aspect-[3/4] grid place-items-center bg-ink/40 text-mut text-[11px]">
                Không có ảnh Last Frame
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: PROMPTS */}
      {resultTab === "prompts" && (
        <div className="flex flex-col gap-2.5">
          <div className="p-2.5 rounded-ctl bg-panel2 border border-line flex flex-col gap-1">
            <div className="flex items-center justify-between text-[11.5px]">
              <span className="font-bold text-fg flex items-center gap-1.5">
                <VideoCamera size={13} className="text-acc" />
                <span>Video Prompt 1 (0-8s)</span>
              </span>
              <button
                onClick={() => onCopyPrompt(activeResult.video_prompt_1 || "", "vp1")}
                className="text-[10.5px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
              >
                {copiedKey === "vp1" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                <span>{copiedKey === "vp1" ? "Đã chép" : "Sao chép"}</span>
              </button>
            </div>
            <p className="font-mono text-[11px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
              {activeResult.video_prompt_1 || "(Không có dữ liệu)"}
            </p>
          </div>

          {!activeResult.single_video && activeResult.video_prompt_2 && (
            <div className="p-2.5 rounded-ctl bg-panel2 border border-line flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11.5px]">
                <span className="font-bold text-fg flex items-center gap-1.5">
                  <VideoCamera size={13} className="text-ok" />
                  <span>Video Prompt 2 (8-16s)</span>
                </span>
                <button
                  onClick={() => onCopyPrompt(activeResult.video_prompt_2 || "", "vp2")}
                  className="text-[10.5px] text-mut hover:text-fg flex items-center gap-1 cursor-pointer"
                >
                  {copiedKey === "vp2" ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
                  <span>{copiedKey === "vp2" ? "Đã chép" : "Sao chép"}</span>
                </button>
              </div>
              <p className="font-mono text-[11px] text-fg/90 whitespace-pre-wrap leading-relaxed select-all">
                {activeResult.video_prompt_2 || "(Không có dữ liệu)"}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

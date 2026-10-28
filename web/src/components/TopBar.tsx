import { Gear, Play, Sparkle } from "@phosphor-icons/react";
import { Chip, Spinner } from "./ui";

export interface CanvasStats {
  imageCount: number;
  videoCount: number;
  lastFrameCount: number;
  nRunning: number;
  nDone: number;
  nPending: number;
  wfBusy: boolean;
  linking: boolean;
}

export function TopBar({
  onLoadTemplate,
  onRunWorkflow,
  canvasStats,
  onOpenSettings,
}: {
  onLoadTemplate: (name: "tryon") => void;
  onRunWorkflow: () => void;
  canvasStats?: CanvasStats | null;
  onOpenSettings: () => void;
}) {
  const totalNodes =
    (canvasStats?.imageCount ?? 0) +
    (canvasStats?.videoCount ?? 0) +
    (canvasStats?.lastFrameCount ?? 0);

  const wfBusy = !!canvasStats?.wfBusy;

  return (
    <header className="h-[52px] shrink-0 border-b border-line bg-panel/95 backdrop-blur-md px-4 flex items-center justify-between gap-3 overflow-hidden select-none z-30">
      {/* LEFT CLUSTER: Logo + Template Button */}
      <div className="flex items-center gap-2.5 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="grid size-6 place-items-center rounded-[7px] bg-acc shadow-sm shadow-acc/20">
            <span className="block size-2.5 rounded-[3px] bg-accink" />
          </div>
          <div className="leading-none">
            <h1 className="text-[14.5px] font-bold tracking-tight text-fg">Flow Bench</h1>
            <p className="mt-0.5 text-[10px] font-medium text-mut">Workspace Canvas</p>
          </div>
        </div>

        <div className="h-4 w-px bg-line2 shrink-0 mx-1" />

        <button
          type="button"
          onClick={() => onLoadTemplate("tryon")}
          className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-acc/45 bg-acc/10 text-[12px] font-bold text-acc hover:bg-acc/20 hover:border-acc/70 transition-colors cursor-pointer shadow-sm shadow-acc/5"
          title="Khởi tạo Mẫu Workflow: Video Thử Đồ (Try-On 16s với 6 nodes kết nối sẵn)"
        >
          <Sparkle size={13} weight="fill" className="text-acc" />
          <span>Mẫu: Video Thử Đồ</span>
        </button>
      </div>

      {/* RIGHT CLUSTER: Node Count Badges + Run Workflow + Settings Button */}
      <div className="flex items-center gap-2.5 shrink-0">
        {canvasStats && (
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mut">
            {canvasStats.imageCount > 0 && <Chip tone="neutral">{`${canvasStats.imageCount} ảnh`}</Chip>}
            {canvasStats.videoCount > 0 && <Chip tone="neutral">{`${canvasStats.videoCount} video`}</Chip>}
            {canvasStats.lastFrameCount > 0 && (
              <Chip tone="neutral">{`${canvasStats.lastFrameCount} frame`}</Chip>
            )}
            {canvasStats.nRunning > 0 && <Chip tone="acc" live>{`${canvasStats.nRunning} chạy`}</Chip>}
            {canvasStats.nDone > 0 && <Chip tone="ok">{`${canvasStats.nDone} xong`}</Chip>}
            {canvasStats.nPending > 0 && <Chip tone="warn">{`${canvasStats.nPending} chờ`}</Chip>}
          </div>
        )}

        <div className="h-4 w-px bg-line2 shrink-0 mx-0.5" />

        <button
          type="button"
          onClick={onRunWorkflow}
          disabled={wfBusy || totalNodes === 0}
          className="inline-flex items-center gap-1.5 px-3.5 h-8 rounded-ctl bg-acc text-accink text-[12px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none shadow-sm shadow-acc/10"
          title="Chạy toàn bộ workflow theo chuỗi phụ thuộc"
        >
          {wfBusy ? <Spinner size={12} /> : <Play size={12} weight="fill" />}
          <span>Chạy Workflow</span>
        </button>

        <button
          type="button"
          onClick={onOpenSettings}
          className="inline-flex items-center gap-1.5 px-3 h-8 rounded-ctl border border-line2 bg-panel2 text-[12px] font-semibold text-dim hover:text-fg hover:border-mut/60 transition-colors cursor-pointer"
          title="Mở Cài đặt & Tiện ích (Thư viện, Tài khoản, Hướng dẫn, Docs API)"
        >
          <Gear size={15} />
          <span>Cài đặt</span>
        </button>
      </div>
    </header>
  );
}

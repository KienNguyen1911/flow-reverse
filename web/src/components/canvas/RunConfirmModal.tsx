import { Warning } from "@phosphor-icons/react";
import type { CanvasNode, ConfirmTarget, RunUnit } from "./types";

/** Confirm Modal (Real Run): shows the execution plan + estimated credit cost. */
export function RunConfirmModal({
  target,
  selectedCount,
  runUnits,
  nodeById,
  imageNodeCount,
  videoNodeCount,
  lastFrameNodeCount,
  jitPromptEnabled,
  onJitPromptChange,
  onCancel,
  onConfirm,
}: {
  target: ConfirmTarget;
  selectedCount: number;
  runUnits: RunUnit[];
  nodeById: Map<string, CanvasNode>;
  imageNodeCount: number;
  videoNodeCount: number;
  lastFrameNodeCount: number;
  jitPromptEnabled: boolean;
  onJitPromptChange: (enabled: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-panel border border-line2 bg-panel p-5 flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <span className="grid place-items-center size-8 rounded-full bg-warn/15 text-warn">
            <Warning size={17} weight="fill" />
          </span>
          <h3 className="text-[14px] font-bold text-fg">Xác nhận chạy thật</h3>
        </div>
        <p className="text-[12.5px] leading-relaxed text-dim">
          {target.mode === "workflow"
            ? selectedCount > 0
              ? `Sẽ chạy ${runUnits.length} nhóm chứa ${selectedCount} node đã chọn. Mỗi nhóm là một đơn vị độc lập — node lỗi chỉ dừng nhóm đó.`
              : `Sẽ chạy ${runUnits.length} nhóm (${imageNodeCount} node ảnh + ${videoNodeCount} node video + ${lastFrameNodeCount} node frame cuối). Mỗi nhóm là một đơn vị độc lập — node lỗi chỉ dừng nhóm đó, các nhóm khác vẫn chạy.`
            : "Sẽ chạy node này qua tài khoản Flow."}
        </p>

        {target.mode === "workflow" && runUnits.length > 0 && (
          <div className="flex flex-col gap-1 max-h-44 overflow-y-auto slim-scroll">
            {runUnits.map((u) => {
              const imgs = u.nodeIds.filter((id) => nodeById.get(id)?.type === "image").length;
              const vids = u.nodeIds.filter((id) => nodeById.get(id)?.type === "video").length;
              const frames = u.nodeIds.filter((id) => nodeById.get(id)?.type === "last_frame").length;
              return (
                <div
                  key={u.id}
                  className="flex items-center justify-between gap-2 rounded-ctl border border-line bg-panel2 px-2.5 py-1.5 text-[11.5px]"
                >
                  <span className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="size-1.5 rounded-full shrink-0"
                      style={{ background: u.color ?? "var(--color-mut)" }}
                    />
                    <span className="truncate font-semibold text-fg">{u.name}</span>
                  </span>
                  <span className="font-mono text-[10.5px] text-mut shrink-0">
                    {imgs} ảnh · {vids} video · {frames} frame
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <p className="text-[12px] leading-relaxed text-warn bg-warn/5 border border-warn/25 rounded-ctl px-3 py-2">
          Chi phí ước tính ~
          {target.mode === "workflow"
            ? ` ${runUnits.reduce(
                (acc, u) =>
                  acc +
                  u.nodeIds.filter((id) => {
                    const t = nodeById.get(id)?.type;
                    return t === "image" || t === "video";
                  }).length,
                0,
              )} credit (các node Frame Cuối: 0 credit)`
            : " 1 credit"}{" "}
          nếu Google nhận (bị từ chối = 0 credit).
        </p>

        {target.mode === "workflow" && (
          <label className="flex items-start gap-2.5 p-2.5 rounded-ctl border border-acc/35 bg-acc/10 text-[12px] text-fg cursor-pointer select-none">
            <input
              type="checkbox"
              checked={jitPromptEnabled}
              onChange={(e) => onJitPromptChange(e.target.checked)}
              className="mt-0.5 accent-acc"
            />
            <div>
              <span className="font-bold text-acc">Dynamic JIT: Tự động tối ưu prompt theo kết quả node trước</span>
              <p className="text-[10.5px] text-mut mt-0.5 leading-snug">
                AI Agent cục bộ sẽ nhìn ảnh thật vừa sinh để viết prompt chính xác cho node tiếp theo trước khi chạy.
              </p>
            </div>
          </label>
        )}
        <div className="flex justify-end gap-2 mt-1">
          <button
            onClick={onCancel}
            className="h-9 px-4 rounded-ctl border border-line2 text-[12.5px] font-semibold text-dim hover:text-fg cursor-pointer"
          >
            Hủy
          </button>
          <button
            onClick={onConfirm}
            className="h-9 px-4 rounded-ctl bg-acc text-accink text-[12.5px] font-bold hover:bg-acc2 cursor-pointer"
          >
            Chạy thật
          </button>
        </div>
      </div>
    </div>
  );
}

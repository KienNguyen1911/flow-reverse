import { Sparkle, Warning } from "@phosphor-icons/react";
import { Btn } from "../ui";

interface Props {
  isSingleRun: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Credit-cost confirmation shown before starting a real (non dry-run) job. */
export function ConfirmModal({ isSingleRun, onCancel, onConfirm }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="rounded-panel border border-line2 bg-panel w-full max-w-md p-5 flex flex-col gap-4 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-full bg-warn/15 text-warn grid place-items-center shrink-0">
            <Warning size={22} weight="bold" />
          </div>
          <div>
            <h3 className="text-[15px] font-bold text-fg">
              {isSingleRun
                ? "Xác nhận tạo Video 8s Thật"
                : "Xác nhận tạo Video Thử Đồ Thật"}
            </h3>
            <p className="text-[12px] text-mut mt-0.5">Sử dụng Google Flow credit</p>
          </div>
        </div>

        {isSingleRun ? (
          <div className="rounded-ctl bg-panel2 border border-line p-3 text-[12px] leading-relaxed flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-mut">Video (8 giây, 1080p):</span>
              <span className="font-mono text-fg">~1 Flow Credit</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-mut">Hậu kỳ & Xóa Watermark (Local):</span>
              <span className="font-mono text-ok">0 Credit (Local)</span>
            </div>
            <div className="border-t border-line2 pt-1.5 flex items-center justify-between font-bold text-acc">
              <span>Tổng chi phí ước tính:</span>
              <span className="font-mono">~1 Credit</span>
            </div>
          </div>
        ) : (
          <div className="rounded-ctl bg-panel2 border border-line p-3 text-[12px] leading-relaxed flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-mut">Video 1 (8 giây):</span>
              <span className="font-mono text-fg">~1 Flow Credit</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-mut">Trích xuất Last Frame (FFmpeg):</span>
              <span className="font-mono text-ok">0 Credit (Local)</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-mut">Video 2 (8 giây):</span>
              <span className="font-mono text-fg">~1 Flow Credit</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-mut">Ghép nối 16s (FFmpeg):</span>
              <span className="font-mono text-ok">0 Credit (Local)</span>
            </div>
            <div className="border-t border-line2 pt-1.5 flex items-center justify-between font-bold text-acc">
              <span>Tổng chi phí ước tính:</span>
              <span className="font-mono">~2 Credits</span>
            </div>
          </div>
        )}

        <p className="text-[11.5px] text-dim leading-relaxed">
          Job sẽ được xếp vào hàng đợi và phân bổ cho tài khoản CloakBrowser khả dụng. Bạn có thể tiếp tục tạo thêm các job khác trong lúc render.
        </p>

        <div className="flex items-center justify-end gap-2.5 pt-2">
          <Btn
            variant="ghost"
            onClick={onCancel}
            className="h-9 px-4 text-[12.5px]"
          >
            Hủy bỏ
          </Btn>
          <Btn
            variant="primary"
            icon={<Sparkle size={15} weight="fill" />}
            onClick={onConfirm}
            className="h-9 px-4 text-[12.5px] font-bold"
          >
            Xác nhận tạo Video
          </Btn>
        </div>
      </div>
    </div>
  );
}

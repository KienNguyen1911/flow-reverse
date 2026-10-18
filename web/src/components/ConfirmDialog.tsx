import { useEffect, useRef } from "react";
import { Sparkle } from "@phosphor-icons/react";
import type { GenRequest } from "./ComposePanel";
import { Btn } from "./ui";

interface Props {
  payload: GenRequest | null;
  projectTitle?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
}

export function ConfirmDialog({ payload, projectTitle, onCancel, onConfirm, busy }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (payload && !d.open) d.showModal();
    if (!payload && d.open) d.close();
  }, [payload]);

  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onCancel();
      }}
    >
      {payload ? (
        <div className="p-5 flex flex-col gap-4">
          <div>
            <h2 className="text-[15px] font-bold">Xác nhận chạy thật</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-mut">
              Request sẽ được gửi lên Google Flow bằng tab đang mở trong CloakBrowser.
            </p>
          </div>

          <div className="rounded-ctl border border-line2 bg-panel2 p-3 text-[12.5px] leading-relaxed flex flex-col gap-2">
            <div>
              <span className="text-mut">Dự án: </span>
              <span className="font-medium">{projectTitle || payload.project_id.slice(0, 8)}</span>
            </div>
            <div>
              <span className="text-mut">Seed: </span>
              <span className="font-mono">{payload.seed ?? "ngẫu nhiên"}</span>
            </div>
            <div>
              <span className="text-mut">Prompt</span>
              <p className="mt-0.5 line-clamp-3 text-dim">{payload.prompt}</p>
            </div>
          </div>

          <p className="text-[12px] leading-relaxed text-dim">
            Nếu Google nhận ảnh: khoảng 1 credit. Nếu bị từ chối: 0 credit.
          </p>

          <div className="flex justify-end gap-2">
            <Btn variant="ghost" onClick={onCancel} disabled={busy}>
              Huỷ
            </Btn>
            <Btn
              variant="primary"
              icon={<Sparkle size={15} weight="fill" />}
              busy={busy}
              onClick={onConfirm}
            >
              Tạo ảnh
            </Btn>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}

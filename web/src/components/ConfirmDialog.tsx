import { useEffect, useRef } from "react";
import { Sparkle, Stack } from "@phosphor-icons/react";
import type { PoolInfo } from "../types";
import type { BatchRequest, GenRequest } from "./ComposePanel";
import { Btn } from "./ui";

export type ConfirmPayload = GenRequest | BatchRequest;

function isBatch(p: ConfirmPayload): p is BatchRequest {
  return "items" in p;
}

interface Props {
  payload: ConfirmPayload | null;
  projectTitle?: string | null;
  pool: PoolInfo | null;
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
}

export function ConfirmDialog({ payload, projectTitle, pool, onCancel, onConfirm, busy }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (payload && !d.open) d.showModal();
    if (!payload && d.open) d.close();
  }, [payload]);

  const batch = payload && isBatch(payload) ? payload : null;
  const single = payload && !isBatch(payload) ? payload : null;

  const nAlloc = (() => {
    if (!batch) return 0;
    const j = batch.items.length;
    const n = pool?.n_available ?? 1;
    const m = pool?.max_active_browsers ?? 4;
    const q = Math.max(1, pool?.target_jobs_per_account ?? 25);
    return Math.max(1, Math.min(n, m, Math.ceil(j / q)));
  })();

  const i2iCount = batch ? batch.items.filter((i) => i.mode === "i2i").length : 0;

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
            <h2 className="text-[15px] font-bold">
              {batch ? "Xác nhận chạy batch" : "Xác nhận chạy thật"}
            </h2>
            <p className="mt-1 text-[12px] leading-relaxed text-mut">
              Request sẽ được gửi lên Google Flow bằng tab đang mở trong CloakBrowser
              {batch ? `, song song trên tối đa ${nAlloc} tài khoản.` : "."}
            </p>
          </div>

          <div className="rounded-ctl border border-line2 bg-panel2 p-3 text-[12.5px] leading-relaxed flex flex-col gap-2">
            <div>
              <span className="text-mut">Dự án: </span>
              <span className="font-medium">
                {projectTitle || (payload.project_id ? payload.project_id.slice(0, 8) : "Tự động quản lý theo từng account")}
              </span>
            </div>
            {batch ? (
              <>
                <div>
                  <span className="text-mut">Số ảnh: </span>
                  <span className="font-mono font-medium">{batch.items.length}</span>
                  <span className="text-mut">
                    {" "}
                    · t2i {batch.items.length - i2iCount} · i2i {i2iCount}
                  </span>
                </div>
                <div>
                  <span className="text-mut">N_alloc dự kiến: </span>
                  <span className="font-mono font-medium">{nAlloc}</span>
                  <span className="text-mut">
                    {" "}
                    / {pool?.n_total ?? "?"} account (Q_target {pool?.target_jobs_per_account ?? 25})
                  </span>
                </div>
                <div>
                  <span className="text-mut">Prompt đầu tiên</span>
                  <p className="mt-0.5 line-clamp-2 text-dim">{batch.items[0]?.prompt}</p>
                </div>
              </>
            ) : (
              <>
                <div>
                  <span className="text-mut">Seed: </span>
                  <span className="font-mono">{single!.seed ?? "ngẫu nhiên"}</span>
                </div>
                <div>
                  <span className="text-mut">Prompt</span>
                  <p className="mt-0.5 line-clamp-3 text-dim">{single!.prompt}</p>
                </div>
              </>
            )}
          </div>

          <p className="text-[12px] leading-relaxed text-dim">
            {batch ? (
              <>
                Tối đa khoảng {batch.items.length} credit (ảnh bị từ chối = 0 credit). Account dính
                giới hạn sẽ tự động được thay bằng account dự phòng.
              </>
            ) : (
              <>Nếu Google nhận ảnh: khoảng 1 credit. Nếu bị từ chối: 0 credit.</>
            )}
          </p>

          <div className="flex justify-end gap-2">
            <Btn variant="ghost" onClick={onCancel} disabled={busy}>
              Huỷ
            </Btn>
            <Btn
              variant="primary"
              icon={batch ? <Stack size={15} weight="fill" /> : <Sparkle size={15} weight="fill" />}
              busy={busy}
              onClick={onConfirm}
            >
              {batch ? `Tạo ${batch.items.length} ảnh` : "Tạo ảnh"}
            </Btn>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}

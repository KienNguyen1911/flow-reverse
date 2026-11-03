import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Copy,
  FolderOpen,
  FilmReel,
  Warning,
  CheckCircle,
  ArrowsClockwise,
  Info,
} from "@phosphor-icons/react";
import { api } from "../api";
import { waitForJob } from "../jobWatcher";
import type { DeliveryItemRef, DeliveryListItem } from "../types";
import { Modal } from "./Modal";
import { Btn, Chip, Spinner } from "./ui";

interface DeliveryModalProps {
  open: boolean;
  onClose: () => void;
  /**
   * Run đã sinh trong canvas, nối theo `clips[].id` của script.
   * Ví dụ: `{ clip1: "video_20261030_230016", clip2: "video_20261031_020523" }`.
   */
  runsByClip?: Record<string, string | null | undefined>;
  /**
   * Ảnh sản phẩm đã sinh từ node ảnh có cờ `is_item`: `{name, run_id}`.
   * Không phụ thuộc `items[]` của script — delivery đặt tên file theo `name`.
   */
  itemsByNode?: DeliveryItemRef[];
  scriptPath?: string;
}

const SCRIPT_PATH = "configs/lookbook_script.json";

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", { hour12: false });
}

export function DeliveryModal({
  open,
  onClose,
  runsByClip = {},
  itemsByNode = [],
  scriptPath,
}: DeliveryModalProps) {
  const [items, setItems] = useState<DeliveryListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const runRefs = useMemo(
    () =>
      Object.entries(runsByClip)
        .filter(([, runId]) => !!runId)
        .map(([clip_id, run_id]) => ({ clip_id, run_id: run_id as string })),
    [runsByClip],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { deliveries } = await api.deliveries();
      setItems(deliveries);
      setError(null);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const build = useCallback(async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.createDelivery({
        script_path: scriptPath || SCRIPT_PATH,
        run_refs: runRefs,
        item_refs: itemsByNode,
        overwrite: true,
      });
      // Build chỉ copy + ffprobe nên thường <2s. `waitForJob` giữ đúng hành vi cũ (chờ tới khi
      // xong) nhưng có timeout và không còn tự viết vòng đếm 120 lần.
      const job = await waitForJob(res.job_id, { intervalMs: 400, timeoutMs: 60_000 });
      if (job.state !== "succeeded") throw new Error(job.error || "job xuất thất bại");
      setNotice(`Đã xuất: ${res.dest_dir}`);
      setActiveSlug(res.slug);
      await refresh();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }, [refresh, runRefs, itemsByNode, scriptPath]);

  const active = items.find((d) => d.slug === activeSlug) || items[0] || null;

  const copyPath = async () => {
    if (!active) return;
    try {
      await navigator.clipboard.writeText(active.dest_dir);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Trình duyệt chặn clipboard — hãy copy đường dẫn bằng tay.");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Xuất bộ dựng phim cho HyperFrames"
      subtitle="Gom plate + clip + cutout vào một thư mục tự chứa, kèm delivery.json và README."
      icon={<FilmReel size={16} weight="bold" />}
      extraHeader={
        <Btn onClick={() => void refresh()} variant="ghost">
          <ArrowsClockwise size={13} /> Làm mới
        </Btn>
      }
    >
      <div className="flex-1 overflow-auto p-5 space-y-4 text-[12.5px]">
        <div className="rounded-ctl border border-line2 bg-panel2 p-3.5 space-y-2">
          <div className="font-bold text-fg flex items-center gap-1.5">
            <Info size={13} weight="fill" className="text-acc" /> Nguyên tắc
          </div>
          <ul className="text-dim space-y-1 list-disc pl-5 leading-relaxed">
            <li>
              AI video chỉ sản xuất <strong className="text-fg">plate</strong> (người mẫu, không
              UI/chữ). Card sản phẩm, kinetic text, progress bar do HyperFrames dựng.
            </li>
            <li>
              Thời lượng trong <code className="font-mono text-[11px]">delivery.json</code> là{" "}
              <strong className="text-fg">số đo ffprobe</strong>, không phải tham số 8s.
            </li>
            <li>Clip không có audio — phải thêm BGM trong app dựng.</li>
          </ul>
        </div>

        <div className="rounded-ctl border border-line2 bg-panel p-3.5 space-y-2">
          <div className="font-bold text-fg">Run đã chọn ({runRefs.length})</div>
          {runRefs.length === 0 ? (
            <div className="text-mut">
              Chưa có run nào được nối. Chạy node video trong canvas trước — hoặc nút sẽ xuất bộ
              với <code className="font-mono">assets_missing</code> để bạn biết còn thiếu gì.
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {runRefs.map((r) => (
                <Chip key={r.clip_id} tone="acc">
                  {r.clip_id} → {r.run_id}
                </Chip>
              ))}
            </div>
          )}
        </div>

        <Btn onClick={() => void build()} variant="primary" disabled={busy || loading}>
          {busy ? <Spinner size={13} /> : <FilmReel size={13} weight="bold" />}
          {busy ? "Đang xuất…" : "Xuất bộ dựng phim"}
        </Btn>

        {error && (
          <div className="rounded-ctl border border-err/40 bg-err/10 px-3 py-2 text-err flex gap-2">
            <Warning size={14} weight="fill" className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {notice && (
          <div className="rounded-ctl border border-ok/40 bg-ok/10 px-3 py-2 text-ok flex gap-2">
            <CheckCircle size={14} weight="fill" className="shrink-0 mt-0.5" />
            <span>{notice}</span>
          </div>
        )}

        <div className="space-y-2">
          <div className="font-bold text-fg">Bộ đã xuất</div>
          {loading && <div className="text-mut flex items-center gap-2"><Spinner size={12} /> Đang tải…</div>}
          {!loading && items.length === 0 && <div className="text-mut">Chưa có bộ nào.</div>}
          <div className="grid gap-1.5">
            {items.map((d) => {
              const selected = (active?.slug ?? "") === d.slug;
              const missing = d.missing;
              return (
                <button
                  key={d.slug}
                  type="button"
                  onClick={() => setActiveSlug(d.slug)}
                  className={`text-left rounded-ctl border px-3 py-2 transition-colors cursor-pointer ${
                    selected
                      ? "border-acc/60 bg-acc/10"
                      : "border-line2 bg-panel hover:bg-panel2"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-fg truncate">{d.title || d.slug}</span>
                    <span className="text-[10px] font-mono text-mut shrink-0">
                      {fmtTime(d.created_ts)}
                    </span>
                  </div>
                  <div className="text-[11px] text-dim truncate font-mono">{d.dest_dir}</div>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    {d.canvas && (
                      <Chip>
                        {d.canvas.width}×{d.canvas.height} @ {d.canvas.fps}fps · {d.canvas.duration_s}s
                      </Chip>
                    )}
                    {d.summary && (
                      <Chip tone={d.summary.clips_measured === d.summary.clips_expected ? "ok" : "warn"}>
                        {d.summary.clips_measured}/{d.summary.clips_expected} clip
                      </Chip>
                    )}
                    {d.warnings > 0 && <Chip tone="warn">{d.warnings} cảnh báo</Chip>}
                    {missing > 0 && <Chip tone="err">thiếu {missing}</Chip>}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {active && (
          <div className="rounded-ctl border border-line2 bg-panel2 p-3.5 space-y-2">
            <div className="font-bold text-fg">Mở trong HyperFrames</div>
            <div className="font-mono text-[11px] break-all text-dim">{active.dest_dir}</div>
            <div className="flex gap-1.5">
              <Btn onClick={() => void copyPath()} variant="ghost">
                <Copy size={13} /> {copied ? "Đã copy" : "Copy đường dẫn"}
              </Btn>
              <a
                href={api.deliveryFileUrl(active.slug, "delivery.json")}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-ctl border border-line2 text-dim hover:text-fg hover:bg-panel text-[11.5px] font-bold"
              >
                <FolderOpen size={13} /> Xem delivery.json
              </a>
            </div>
            <div className="text-[11px] text-mut leading-relaxed">
              Desktop app chỉ nhận <strong className="text-fg">file</strong>, không nhận URL kéo
              thả. Mở thư mục trên bằng File Explorer rồi kéo <code className="font-mono">clips/</code>,{" "}
              <code className="font-mono">items/</code>, <code className="font-mono">plate.*</code> vào.
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

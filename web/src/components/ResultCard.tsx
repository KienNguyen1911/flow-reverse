import {
  ArrowSquareOut,
  CheckCircle,
  DownloadSimple,
  Flask,
  FolderSimplePlus,
  XCircle,
} from "@phosphor-icons/react";
import type { Job } from "../types";
import { btnCls } from "./ui";

const BATCH_STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: "chờ", cls: "text-mut" },
  running: { label: "chạy", cls: "text-acc" },
  ok: { label: "ok", cls: "text-ok" },
  dry_run: { label: "dry", cls: "text-dim" },
  rejected: { label: "từ chối", cls: "text-warn" },
  failed: { label: "lỗi", cls: "text-err" },
  skipped: { label: "bỏ", cls: "text-mut" },
};

function BatchResultCard({ job }: { job: Job }) {
  const r = job.result;
  if (!r?.batch) {
    return (
      <div className="rounded-ctl border border-err/30 bg-err/5 p-3.5 text-[12.5px] leading-relaxed">
        <p className="font-semibold text-err">Batch lỗi</p>
        <p className="mt-1 text-dim">{job.error || "Không rõ nguyên nhân."}</p>
      </div>
    );
  }
  const items = r.items ?? [];
  const running = job.state === "running" || job.state === "queued";
  return (
    <div className="rounded-ctl border border-line2 bg-panel2 p-3.5 flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px]">
        <p className="font-semibold text-fg">Batch {r.total ?? items.length} ảnh</p>
        {running && (r.pending ?? 0) > 0 ? (
          <span className="text-acc">{r.pending} đang chờ/chạy…</span>
        ) : null}
        <span className="text-ok">{r.ok ?? 0} ok</span>
        {r.rejected ? <span className="text-warn">{r.rejected} bị từ chối</span> : null}
        {r.failed ? <span className="text-err">{r.failed} lỗi</span> : null}
        {r.skipped ? <span className="text-mut">{r.skipped} bỏ qua</span> : null}
        {r.dry_run ? <span className="text-dim">{r.dry_run} dry-run</span> : null}
      </div>
      <p className="text-[11.5px] text-mut">
        N_alloc {r.n_alloc ?? "?"} - account: {r.accounts?.join(", ") || "khong co"}
        {r.output_dir ? <span className="font-mono"> · {r.output_dir}</span> : null}
      </p>
      <div className="slim-scroll max-h-[320px] overflow-y-auto flex flex-col">
        {items.map((it) => {
          const st = BATCH_STATUS[it.status] ?? { label: it.status, cls: "text-mut" };
          return (
            <div key={it.idx} className="flex items-center gap-2 py-[3px] text-[11.5px] min-w-0">
              <span className="w-7 shrink-0 font-mono text-mut">
                {String(it.idx + 1).padStart(3, "0")}
              </span>
              <span className={`w-12 shrink-0 font-medium ${st.cls}`}>{st.label}</span>
              <span className="w-8 shrink-0 font-mono text-[10px] text-mut">{it.mode}</span>
              <span className="min-w-0 flex-1 truncate text-dim" title={it.prompt}>
                {it.shot_id ? (
                  <span className="font-mono text-[10.5px] text-mut">{it.shot_id} </span>
                ) : null}
                {it.prompt}
              </span>
              {it.account_id ? (
                <span className="shrink-0 font-mono text-[10px] text-mut">{it.account_id}</span>
              ) : null}
              {it.result?.image_url ? (
                <a
                  className="shrink-0 text-acc hover:underline"
                  href={it.result.image_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  xem
                </a>
              ) : null}
              {it.error ? (
                <span className="shrink-0 max-w-[180px] truncate text-err" title={it.error}>
                  {it.error}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
      {job.state === "failed" && job.error ? <p className="text-[12px] text-err">{job.error}</p> : null}
    </div>
  );
}

function Meta({ k, v, mono = true }: { k: string; v: string | number | null | undefined; mono?: boolean }) {
  if (v === null || v === undefined || v === "") return null;
  return (
    <div className="flex gap-2 text-[12px] leading-relaxed">
      <span className="text-mut w-[76px] shrink-0">{k}</span>
      <span className={`${mono ? "font-mono" : ""} min-w-0 text-dim break-all`}>{String(v)}</span>
    </div>
  );
}

function fmtBytes(n?: number | null) {
  if (!n) return null;
  return (n / 1024).toFixed(1) + " KB";
}

function fmtRes(r?: number[] | null) {
  if (!r || r.length < 2) return null;
  return `${r[0]}×${r[1]}`;
}

export function ResultCard({ job, onUseProject }: { job: Job; onUseProject: (id: string) => void }) {
  const r = job.result;

  if (job.kind === "batch_generate") {
    return <BatchResultCard job={job} />;
  }

  if (job.state === "failed") {
    return (
      <div className="rounded-ctl border border-err/30 bg-err/5 p-3.5 text-[12.5px] leading-relaxed">
        <p className="font-semibold text-err">Job lỗi</p>
        <p className="mt-1 text-dim">{job.error || "Không rõ nguyên nhân."}</p>
      </div>
    );
  }
  if (!r) return null;

  if (job.kind === "create_project" && r.id) {
    const pid = r.id;
    return (
      <div className="rounded-ctl border border-ok/30 bg-ok/5 p-3.5 flex flex-col gap-2">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-ok">
          <FolderSimplePlus size={16} /> Đã tạo dự án (0 credit)
        </p>
        <p className="text-[12.5px] text-dim">{r.title || "(không tiêu đề)"}</p>
        <p className="font-mono text-[11px] text-mut">{pid}</p>
        <div>
          <button className={btnCls("solid")} onClick={() => onUseProject(pid)}>
            Dùng dự án này
          </button>
        </div>
      </div>
    );
  }

  if (job.kind === "list_projects") {
    return (
      <div className="rounded-ctl border border-line2 bg-panel2 p-3.5">
        <p className="text-[12.5px] text-dim">
          Đã cập nhật danh sách dự án: {r.count ?? 0} dự án (0 credit).
        </p>
      </div>
    );
  }

  const st = r.status;

  if (st === "dry_run") {
    return (
      <div className="rounded-ctl border border-line2 bg-panel2 p-3.5 flex flex-col gap-2">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-fg">
          <Flask size={16} className="text-acc" /> Dry-run thành công (0 credit)
        </p>
        <p className="text-[12px] leading-relaxed text-mut">
          Đã capture request của app và dựng request của ta hợp lệ, nhưng không gửi lên Google.
        </p>
        <div className="flex flex-col gap-1 mt-0.5">
          <Meta k="Seed" v={r.seed_used} />
          <Meta k="Thư mục" v={r.run_dir?.split(/[\\/]/).pop()} />
        </div>
      </div>
    );
  }

  if (st === "rejected") {
    return (
      <div className="rounded-ctl border border-warn/30 bg-warn/5 p-3.5 flex flex-col gap-2">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-warn">
          <XCircle size={16} /> Bị từ chối: {r.reason}
          {r.grpc_code != null ? ` (gRPC ${r.grpc_code})` : ""}
        </p>
        {r.hint ? <p className="text-[12.5px] leading-relaxed text-dim">{r.hint}</p> : null}
        <p className="text-[12px] text-mut">Lần chạy này không tốn credit.</p>
        {r.detail ? (
          <details className="text-[11.5px]">
            <summary className="cursor-pointer text-mut hover:text-dim">Chi tiết server</summary>
            <pre className="mt-1.5 max-h-[140px] overflow-auto slim-scroll font-mono text-[10.5px] text-mut whitespace-pre-wrap break-all">
              {r.detail}
            </pre>
          </details>
        ) : null}
      </div>
    );
  }

  if (st === "ok" || st === "ok_no_download") {
    const img = r.image;
    const seedMatch = img?.seed_echo != null && img?.seed != null && img.seed_echo === img.seed;
    return (
      <div className="rounded-ctl border border-ok/25 bg-ok/5 p-3.5 flex flex-col gap-3.5">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-ok">
          <CheckCircle size={16} /> Ảnh đã tạo
          {img?.title ? <span className="text-dim font-medium">, {img.title}</span> : null}
        </p>

        <div className="flex flex-col md:flex-row gap-3.5">
          {r.image_url ? (
            <a href={r.image_url} target="_blank" rel="noopener noreferrer" className="shrink-0">
              <img
                src={r.image_url}
                alt={img?.prompt ?? "Ảnh đã tạo"}
                className="max-h-[300px] w-auto rounded-ctl border border-line2 bg-ink"
              />
            </a>
          ) : (
            <div className="grid place-items-center rounded-ctl border border-line2 bg-ink text-[12px] text-mut px-6 py-10">
              Không tải được file ảnh (URL có thể đã hết hạn).
            </div>
          )}
          <div className="flex flex-col gap-1.5 min-w-0">
            <Meta k="Seed" v={img?.seed} />
            {seedMatch ? (
              <p className="flex items-center gap-1.5 text-[11.5px] text-ok">
                <CheckCircle size={13} /> Server echo trùng seed gửi lên
              </p>
            ) : null}
            <Meta k="Kích thước" v={fmtRes(img?.resolution)} />
            <Meta k="Dung lượng" v={fmtBytes(img?.file_bytes)} />
            <Meta k="Media id" v={img?.media_id} />
            <Meta k="Generation" v={img?.generation_id_echo || img?.generation_id} />
            <Meta k="Thời gian" v={r.elapsed_s != null ? `${r.elapsed_s}s` : null} mono={false} />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {r.image_url ? (
            <a className={btnCls("primary")} href={r.image_url} download>
              <DownloadSimple size={15} /> Tải ảnh xuống
            </a>
          ) : null}
          {img?.project_id ? (
            <a
              className={btnCls("ghost")}
              href={`https://flow.google.com/project/${img.project_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ArrowSquareOut size={15} /> Mở trong Flow
            </a>
          ) : null}
        </div>
      </div>
    );
  }

  return null;
}

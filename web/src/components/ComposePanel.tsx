import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowClockwise,
  BookOpen,
  CaretDown,
  Flask,
  Image as ImageIcon,
  LinkSimple,
  Plus,
  Sparkle,
  Trash,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import type { BatchItemRequest, PoolInfo, Project } from "../types";
import { Btn, Field, IconBtn, InfoTip, Panel } from "./ui";
import { api } from "../api";

export interface GenRequest {
  project_id: string;
  prompt: string;
  aspect: number;
  seed: number | null;
}

export interface BatchRequest {
  project_id?: string;
  aspect: number;
  items: BatchItemRequest[];
}

interface Props {
  projects: Project[];
  projectsLoading: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  busy: boolean;
  bridgeReady: boolean;
  pool: PoolInfo | null;
  onRealRun: (req: GenRequest) => void;
  onDryRun: (req: GenRequest) => void;
  onBatchRun: (req: BatchRequest) => void;
  onBatchDryRun: (req: BatchRequest) => void;
  onSavePoolConfig: (targetJobsPerAccount: number) => void;
  onRefreshProjects: () => void;
  onCreateProject: (title: string) => void;
  onAddProject: (ref: string) => Promise<void>;
  onOpenGuide: () => void;
}

const PROMPT_KEY = "fb_prompt_draft";
const BATCH_ON_KEY = "fb_batch_on";
const BATCH_KEY = "fb_batch_prompts";
const BATCH_REF_KEY = "fb_batch_ref";
const MAX_BATCH = 300;

export function ComposePanel(p: Props) {
  const [prompt, setPrompt] = useState(() => localStorage.getItem(PROMPT_KEY) ?? "");
  const [seedStr, setSeedStr] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);


  // -- batch mode (plan Task 4) --------------------------------------------- //
  const [batchOn, setBatchOn] = useState(() => localStorage.getItem(BATCH_ON_KEY) === "1");
  const [batchText, setBatchText] = useState(() => localStorage.getItem(BATCH_KEY) ?? "");
  const [batchRef, setBatchRef] = useState(() => localStorage.getItem(BATCH_REF_KEY) ?? "");
  const [refPreviewUrl, setRefPreviewUrl] = useState<string | null>(null);
  const [uploadingRef, setUploadingRef] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [qTargetStr, setQTargetStr] = useState("");

  const [addOpen, setAddOpen] = useState(false);
  const [addRef, setAddRef] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const createDlg = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    localStorage.setItem(PROMPT_KEY, prompt);
  }, [prompt]);

  useEffect(() => {
    localStorage.setItem(BATCH_ON_KEY, batchOn ? "1" : "0");
  }, [batchOn]);

  useEffect(() => {
    localStorage.setItem(BATCH_KEY, batchText);
  }, [batchText]);

  useEffect(() => {
    localStorage.setItem(BATCH_REF_KEY, batchRef);
    if (batchRef && !refPreviewUrl) {
      const normalized = batchRef.replace(/\\/g, "/");
      const fn = normalized.split("/").pop();
      if (normalized.includes("references") && fn) {
        setRefPreviewUrl(`/api/references/${fn}`);
      }
    }
  }, [batchRef, refPreviewUrl]);

  useEffect(() => {
    const d = createDlg.current;
    if (!d) return;
    if (createOpen && !d.open) d.showModal();
    if (!createOpen && d.open) d.close();
  }, [createOpen]);

  const selected = useMemo(() => p.projects.find((x) => x.id === p.selectedId) ?? null, [p.projects, p.selectedId]);

  const seedValue = (): number | null | "bad" => {
    const s = seedStr.trim();
    if (!s) return null;
    const n = Number(s);
    if (!Number.isInteger(n) || n < 1 || n > 2147483647) return "bad";
    return n;
  };

  const validate = (): GenRequest | null => {
    setFormErr(null);
    if (!p.selectedId) {
      setFormErr("Chọn dự án trước khi chạy.");
      return null;
    }
    const seed = seedValue();
    if (seed === "bad") {
      setFormErr("Seed phải là số nguyên trong khoảng 1 đến 2³¹−1, hoặc để trống.");
      return null;
    }
    if (!prompt.trim()) {
      setFormErr("Prompt không được để trống.");
      return null;
    }
    return { project_id: p.selectedId, prompt: prompt.trim(), aspect: 3, seed };
  };

  // -- batch helpers --------------------------------------------------------- //

  const batchLines = useMemo(
    () => batchText.split("\n").map((l) => l.trim()).filter(Boolean),
    [batchText],
  );

  const qTarget = (() => {
    const n = Number(qTargetStr);
    if (Number.isInteger(n) && n >= 1 && n <= 500) return n;
    return p.pool?.target_jobs_per_account ?? 25;
  })();

  const predictedN = useMemo(() => {
    const j = batchLines.length;
    if (!j) return 0;
    const n = p.pool?.n_available ?? 1;
    const m = p.pool?.max_active_browsers ?? 4;
    return Math.max(1, Math.min(n, m, Math.ceil(j / qTarget)));
  }, [batchLines.length, p.pool?.n_available, p.pool?.max_active_browsers, qTarget]);

  const validateBatch = (): BatchRequest | null => {
    setFormErr(null);
    if (batchLines.length === 0) {
      setFormErr("Nhập ít nhất 1 prompt (mỗi dòng là 1 ảnh).");
      return null;
    }
    if (batchLines.length > MAX_BATCH) {
      setFormErr(`Batch toi da ${MAX_BATCH} anh. Chia thanh nhieu lan chay.`);
      return null;
    }
    if (batchLines.some((l) => l.length > 2000)) {
      setFormErr("Có dòng dài quá 2000 ký tự.");
      return null;
    }
    const ref = batchRef.trim() || null;
    return {
      ...(p.selectedId ? { project_id: p.selectedId } : {}),
      aspect: 3,
      items: batchLines.map((line, i) => ({
        prompt: line,
        id: `shot_${String(i + 1).padStart(3, "0")}`,
        ...(ref ? { mode: "i2i" as const, reference_image_path: ref } : {}),
      })),
    };
  };

  const doReal = () => {
    if (batchOn) {
      const req = validateBatch();
      if (req) p.onBatchRun(req);
      return;
    }
    const req = validate();
    if (req) p.onRealRun(req);
  };
  const doDry = () => {
    if (batchOn) {
      const req = validateBatch();
      if (req) p.onBatchDryRun(req);
      return;
    }
    const req = validate();
    if (req) p.onDryRun(req);
  };

  const canRun = !p.busy && p.bridgeReady;

  return (
    <Panel className="p-4 lg:p-5 flex flex-col gap-4">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-2 border-b border-line2/50">
        <div className="flex items-center gap-2">
          <Sparkle size={15} className="text-acc" weight="fill" />
          <h2 className="text-[13.5px] font-bold text-fg">Thiết lập Tạo ảnh</h2>
        </div>
        <button
          type="button"
          onClick={p.onOpenGuide}
          className="inline-flex items-center gap-1.5 rounded-ctl border border-line2/70 bg-panel2/60 px-2.5 py-1 text-[11.5px] font-medium text-dim hover:text-fg hover:border-acc/50 transition-colors"
          title="Xem hướng dẫn quy tắc tính credit, batch và vận hành an toàn"
        >
          <BookOpen size={13} className="text-acc" />
          <span>Hướng dẫn</span>
        </button>
      </div>

      {/* Project ---------------------------------------------------------- */}
      <Field
        label="Dự án"
        htmlFor="fb-project"
        info={
          batchOn
            ? "Trong chế độ batch, bạn có thể chọn 1 dự án cụ thể hoặc để trống để từng tài khoản trong pool tự tạo/sử dụng dự án riêng."
            : "Dự án trên Google Flow để lưu trữ các ảnh tạo ra. Bạn có thể tải danh sách hoặc tạo mới với 0 credit."
        }
        right={
          selected ? (
            <span className="font-mono text-[11px] text-mut" title={`UUID: ${selected.id}`}>
              ID: {selected.id.slice(0, 8)}...
            </span>
          ) : batchOn ? (
            <span className="font-mono text-[11px] text-acc">Tự động theo account</span>
          ) : null
        }
      >
        <div className="flex gap-2">
          <div className="relative flex-1">
            <select
              id="fb-project"
              className="w-full h-9 appearance-none rounded-ctl border border-line2 bg-panel2 pl-3 pr-8 text-[13px] text-fg outline-none focus-visible:border-acc/60"
              value={p.selectedId ?? ""}
              onChange={(e) => p.onSelect(e.target.value || null)}
              disabled={p.projectsLoading}
            >
              <option value="">
                {p.projectsLoading
                  ? "Đang tải..."
                  : batchOn
                  ? "(Tự động tạo / dùng dự án riêng từng account)"
                  : "Chọn dự án"}
              </option>
              {p.projects.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {(pr.title || "(không tiêu đề)") + " (" + pr.id.slice(0, 8) + ")"}
                </option>
              ))}
            </select>
            <CaretDown
              size={13}
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-mut"
            />
          </div>
          <IconBtn label="Tải danh sách dự án từ Flow (0 credit)" onClick={p.onRefreshProjects} disabled={p.busy}>
            <ArrowClockwise size={15} />
          </IconBtn>
          <IconBtn label="Tạo dự án mới trên Flow (0 credit)" onClick={() => setCreateOpen(true)} disabled={p.busy}>
            <Plus size={15} />
          </IconBtn>
          <IconBtn
            label="Thêm dự án bằng UUID hoặc link"
            onClick={() => {
              setAddOpen((v) => !v);
              setAddErr(null);
            }}
            disabled={p.busy}
          >
            <LinkSimple size={15} />
          </IconBtn>
        </div>

        {addOpen ? (
          <div className="flex gap-2">
            <input
              className="flex-1 h-9 rounded-ctl border border-line2 bg-panel2 px-3 text-[13px] text-fg outline-none placeholder:text-mut focus-visible:border-acc/60"
              placeholder="Dán UUID hoặc link /project/..."
              value={addRef}
              onChange={(e) => setAddRef(e.target.value)}
            />
            <Btn
              variant="solid"
              busy={addBusy}
              onClick={async () => {
                if (!addRef.trim()) return;
                setAddBusy(true);
                setAddErr(null);
                try {
                  await p.onAddProject(addRef.trim());
                  setAddRef("");
                  setAddOpen(false);
                } catch (e) {
                  setAddErr(e instanceof Error ? e.message : String(e));
                } finally {
                  setAddBusy(false);
                }
              }}
            >
              Thêm
            </Btn>
          </div>
        ) : null}
        {addErr ? <p className="text-[11.5px] text-err">{addErr}</p> : null}
      </Field>

      {/* Batch toggle -------------------------------------------------------- */}
      <div className="flex items-center justify-between rounded-ctl border border-line2 bg-panel2 px-3 h-9 select-none">
        <label className="flex items-center gap-2.5 cursor-pointer flex-1">
          <input
            type="checkbox"
            className="accent-acc size-3.5"
            checked={batchOn}
            onChange={(e) => setBatchOn(e.target.checked)}
          />
          <span className="text-[12.5px] font-medium text-dim">
            Chế độ Batch (nhiều ảnh song song)
          </span>
        </label>
        <div className="flex items-center gap-2">
          {batchOn && batchLines.length > 0 && (
            <span className="font-mono text-[11px] text-mut">
              {batchLines.length} ảnh → ~{predictedN} acc
            </span>
          )}
          <InfoTip content="Chạy nhiều prompt song song, tự động phân bổ đều trên các tài khoản trong pool theo công thức min(N, M_RAM, ceil(J/Q))." />
        </div>
      </div>

      {batchOn ? (
        <>
          {/* Batch prompts ---------------------------------------------------- */}
          <Field
            label="Danh sách prompt"
            htmlFor="fb-batch"
            info="Mỗi dòng là một prompt riêng biệt (tương ứng 1 ảnh). Tối đa 300 ảnh/batch."
            right={<span className="font-mono text-[11px] text-mut">{batchLines.length}/{MAX_BATCH}</span>}
          >
            <textarea
              id="fb-batch"
              rows={6}
              className="w-full resize-y rounded-ctl border border-line2 bg-panel2 px-3 py-2 text-[13px] leading-relaxed text-fg outline-none placeholder:text-mut focus-visible:border-acc/60 slim-scroll font-mono"
              placeholder={"Cảnh 1: toàn cảnh thung lũng lúc bình minh...\nCảnh 2: cận cảnh nhân vật chính...\nCảnh 3: ..."}
              value={batchText}
              onChange={(e) => setBatchText(e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3 items-start">
            <Field
              label="Ảnh tham chiếu i2i"
              htmlFor="fb-batch-ref"
              info="Chọn file ảnh từ máy để chạy image2image giữ nhất quán nhân vật/phong cách cho mọi dòng trong batch. Hệ thống sẽ tự upload và dùng làm ảnh tham chiếu."
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setUploadingRef(true);
                  setUploadErr(null);
                  try {
                    const res = await api.uploadReference(f);
                    setBatchRef(res.path);
                    setRefPreviewUrl(res.url);
                  } catch (err) {
                    setUploadErr(err instanceof Error ? err.message : String(err));
                  } finally {
                    setUploadingRef(false);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }
                }}
              />

              {batchRef ? (
                <div className="flex items-center gap-2 rounded-ctl border border-line2 bg-panel2 p-2">
                  {refPreviewUrl ? (
                    <img
                      src={refPreviewUrl}
                      alt="Tham chiếu"
                      className="size-11 rounded object-cover border border-line2 bg-panel shrink-0"
                    />
                  ) : (
                    <div className="size-11 rounded border border-line2 bg-panel flex items-center justify-center shrink-0 text-mut">
                      <ImageIcon size={20} />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-medium text-fg truncate" title={batchRef}>
                      {batchRef.replace(/\\/g, "/").split("/").pop()}
                    </p>
                    <p className="font-mono text-[10px] text-mut truncate" title={batchRef}>
                      {batchRef}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setBatchRef("");
                      setRefPreviewUrl(null);
                    }}
                    className="p-1.5 rounded-ctl text-mut hover:text-err hover:bg-err/10 transition-colors shrink-0"
                    title="Bỏ ảnh tham chiếu"
                  >
                    <Trash size={14} />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  disabled={uploadingRef}
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full h-9 inline-flex items-center justify-center gap-2 rounded-ctl border border-dashed border-line2 bg-panel2/60 hover:bg-panel2 hover:border-acc/60 text-[12.5px] font-medium text-dim hover:text-fg transition-colors"
                >
                  <UploadSimple size={15} className="text-acc" />
                  <span>{uploadingRef ? "Đang tải ảnh..." : "Chọn ảnh từ máy (JPG/PNG)"}</span>
                </button>
              )}
              {uploadErr ? <p className="text-[11px] text-err mt-1">{uploadErr}</p> : null}
            </Field>
            <Field
              label="Q_target (ảnh/account)"
              htmlFor="fb-batch-q"
              info="Ngưỡng ảnh mục tiêu trên 1 account trước khi mở thêm account mới. Công thức N_alloc = min(N, M_RAM, ceil(J/Q))."
            >
              <input
                id="fb-batch-q"
                inputMode="numeric"
                className="w-full h-9 rounded-ctl border border-line2 bg-panel2 px-3 font-mono text-[13px] text-fg outline-none placeholder:text-mut focus-visible:border-acc/60"
                placeholder={String(p.pool?.target_jobs_per_account ?? 25)}
                value={qTargetStr}
                onChange={(e) => setQTargetStr(e.target.value.replace(/[^0-9]/g, ""))}
                onBlur={() => {
                  const n = Number(qTargetStr);
                  if (Number.isInteger(n) && n >= 1 && n <= 500 && n !== p.pool?.target_jobs_per_account) {
                    p.onSavePoolConfig(n);
                  } else {
                    setQTargetStr("");
                  }
                }}
              />
            </Field>
          </div>

          <div className="flex items-center justify-between rounded-ctl border border-line2/70 bg-panel2/50 px-3 py-1.5 text-[11.5px] text-dim">
            <span className="font-mono text-mut">
              {batchLines.length} ảnh · N khả dụng: {p.pool?.n_available ?? 1} · dự kiến: <strong className="text-acc">{predictedN} acc</strong>
            </span>
            <InfoTip content="Các account được đánh thức khi đến lượt; account rảnh còn lại giữ Standby để tiết kiệm 100% RAM. Xem chi tiết trong mục Hướng dẫn." />
          </div>
        </>
      ) : (
        <>
          {/* Prompt ------------------------------------------------------------ */}
          <Field
            label="Prompt"
            htmlFor="fb-prompt"
            info="Mô tả chi tiết hình ảnh bạn muốn tạo. Nhấn Ctrl+Enter để chạy nhanh."
            right={
              <span className="font-mono text-[11px] text-mut">{prompt.length}/2000</span>
            }
          >
            <textarea
              id="fb-prompt"
              rows={5}
              maxLength={2000}
              className="w-full resize-y rounded-ctl border border-line2 bg-panel2 px-3 py-2.5 text-[13.5px] leading-relaxed text-fg outline-none placeholder:text-mut focus-visible:border-acc/60 slim-scroll"
              placeholder="Mô tả ảnh bạn muốn tạo. Ví dụ: một con vịt vàng bơi trên mặt hồ phẳng lặng, nắng sớm, góc máy ngang tầm nước."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                  e.preventDefault();
                  doReal();
                }
              }}
            />
          </Field>

          {/* Params ------------------------------------------------------------- */}
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Tỷ lệ khung"
              htmlFor="fb-aspect"
              info="Tỷ lệ khung hình 16:9 (ngang), định dạng chuẩn tối ưu nhất của mô hình Google Flow."
            >
              <div className="relative">
                <select
                  id="fb-aspect"
                  className="w-full h-9 appearance-none rounded-ctl border border-line2 bg-panel2 pl-3 pr-8 text-[13px] text-fg outline-none focus-visible:border-acc/60"
                  value="3"
                  onChange={() => undefined}
                >
                  <option value="3">16:9, ngang</option>
                </select>
                <CaretDown
                  size={13}
                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-mut"
                />
              </div>
            </Field>
            <Field
              label="Seed"
              htmlFor="fb-seed"
              info="Số nguyên từ 1 đến 2³¹−1 để cố định phong cách ảnh. Bỏ trống để ngẫu nhiên."
            >
              <input
                id="fb-seed"
                inputMode="numeric"
                className="w-full h-9 rounded-ctl border border-line2 bg-panel2 px-3 font-mono text-[13px] text-fg outline-none placeholder:text-mut focus-visible:border-acc/60"
                placeholder="Ngẫu nhiên"
                value={seedStr}
                onChange={(e) => setSeedStr(e.target.value.replace(/[^0-9]/g, ""))}
              />
            </Field>
          </div>
        </>
      )}

      {/* Actions ------------------------------------------------------------ */}
      <div className="flex flex-col gap-2.5">
        <div className="flex gap-2">
          <Btn
            variant="primary"
            icon={<Sparkle size={15} weight="fill" />}
            disabled={!canRun}
            onClick={doReal}
            className="flex-1"
          >
            {batchOn ? `Tạo batch${batchLines.length ? ` (${batchLines.length} ảnh)` : ""}` : "Tạo ảnh"}
          </Btn>
          <Btn variant="ghost" icon={<Flask size={15} />} disabled={!canRun} onClick={doDry} className="flex-1">
            {batchOn ? "Batch dry-run" : "Dry-run"}
          </Btn>
        </div>

        <div className="flex items-center justify-between text-[11px] text-mut px-0.5">
          <span>Ước tính: ~{batchOn ? (batchLines.length || 0) : 1} credit khi thành công</span>
          <div className="flex items-center gap-1.5">
            <span className="text-ok">Dry-run: 0 credit</span>
            <InfoTip content="Google chỉ trừ credit khi ảnh được tạo thành công. Bị từ chối hoặc Dry-run luôn 0 credit. Khi job chạy, tránh thao tác trên tab Flow của trình duyệt." />
          </div>
        </div>

        {formErr ? (
          <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-err">
            <WarningCircle size={14} className="mt-0.5 shrink-0" />
            {formErr}
          </p>
        ) : null}

        {!p.bridgeReady ? (
          <div className="flex items-center justify-between rounded-ctl border border-warn/30 bg-warn/10 px-3 py-1.5 text-[11.5px] text-warn">
            <div className="flex items-center gap-1.5">
              <WarningCircle size={14} className="shrink-0" />
              <span>Trình duyệt đang Standby</span>
            </div>
            <InfoTip content="CloakBrowser sẽ được tự động mở khi bạn bấm Tạo ảnh/Batch, hoặc bạn có thể mở thủ công trong Quản lý Account." />
          </div>
        ) : null}
      </div>

      {/* Create-project dialog -------------------------------------------------- */}
      <dialog ref={createDlg} className="confirm-dialog" onCancel={() => setCreateOpen(false)}>
        <div className="p-5 flex flex-col gap-4">
          <div>
            <h2 className="text-[15px] font-bold">Tạo dự án mới trên Flow</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-mut">
              Dự án thật sẽ được tạo trong tài khoản Google của bạn. Thao tác này không tốn credit.
            </p>
          </div>
          <input
            autoFocus
            className="h-9 rounded-ctl border border-line2 bg-panel2 px-3 text-[13px] text-fg outline-none placeholder:text-mut focus-visible:border-acc/60"
            placeholder="Tên dự án, ví dụ: Batch 18/10 tối"
            value={createTitle}
            maxLength={120}
            onChange={(e) => setCreateTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && createTitle.trim() && !createBusy) {
                setCreateBusy(true);
                p.onCreateProject(createTitle.trim());
                setCreateBusy(false);
                setCreateOpen(false);
              }
            }}
          />
          <div className="flex justify-end gap-2">
            <Btn variant="ghost" onClick={() => setCreateOpen(false)}>
              Huỷ
            </Btn>
            <Btn
              variant="primary"
              busy={createBusy}
              disabled={!createTitle.trim()}
              onClick={() => {
                setCreateBusy(true);
                p.onCreateProject(createTitle.trim());
                setCreateBusy(false);
                setCreateOpen(false);
              }}
            >
              Tạo dự án
            </Btn>
          </div>
        </div>
      </dialog>
    </Panel>
  );
}

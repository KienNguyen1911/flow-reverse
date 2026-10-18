import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowClockwise,
  CaretDown,
  Flask,
  LinkSimple,
  Plus,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import type { BatchItemRequest, PoolInfo, Project } from "../types";
import { Btn, Field, IconBtn, Panel } from "./ui";
import { api } from "../api";

export interface GenRequest {
  project_id: string;
  prompt: string;
  aspect: number;
  seed: number | null;
}

export interface BatchRequest {
  project_id: string;
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
  }, [batchRef]);

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
    if (!p.selectedId) {
      setFormErr("Chọn dự án trước khi chạy batch.");
      return null;
    }
    if (batchLines.length === 0) {
      setFormErr("Nhập ít nhất 1 prompt (mỗi dòng là 1 ảnh).");
      return null;
    }
    if (batchLines.length > MAX_BATCH) {
      setFormErr(`Batch tối đa ${MAX_BATCH} ảnh — chia thành nhiều lần chạy.`);
      return null;
    }
    if (batchLines.some((l) => l.length > 2000)) {
      setFormErr("Có dòng dài quá 2000 ký tự.");
      return null;
    }
    const ref = batchRef.trim() || null;
    return {
      project_id: p.selectedId,
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
    <Panel className="p-4 lg:p-5 flex flex-col gap-5">
      {/* Project ---------------------------------------------------------- */}
      <Field
        label="Dự án"
        htmlFor="fb-project"
        hint={
          selected
            ? `UUID: ${selected.id}`
            : "Chưa có dự án trong danh sách. Bấm biểu tượng tải để đọc danh sách từ Flow (0 credit)."
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
              <option value="">{p.projectsLoading ? "Đang tải..." : "Chọn dự án"}</option>
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
      <label className="flex items-center gap-2.5 rounded-ctl border border-line2 bg-panel2 px-3 h-9 cursor-pointer select-none">
        <input
          type="checkbox"
          className="accent-acc size-3.5"
          checked={batchOn}
          onChange={(e) => setBatchOn(e.target.checked)}
        />
        <span className="text-[12.5px] font-medium text-dim">
          Chế độ batch — nhiều ảnh, chạy song song trên N_alloc account
        </span>
        {batchOn && batchLines.length > 0 ? (
          <span className="ml-auto font-mono text-[11px] text-mut">
            {batchLines.length} ảnh → ~{predictedN} account
          </span>
        ) : null}
      </label>

      {batchOn ? (
        <>
          {/* Batch prompts ---------------------------------------------------- */}
          <Field
            label="Danh sách prompt (mỗi dòng 1 ảnh)"
            htmlFor="fb-batch"
            right={<span className="font-mono text-[11px] text-mut">{batchLines.length}/{MAX_BATCH}</span>}
            hint="Mỗi dòng là một prompt riêng. Số ảnh J = số dòng không trống."
          >
            <textarea
              id="fb-batch"
              rows={7}
              className="w-full resize-y rounded-ctl border border-line2 bg-panel2 px-3 py-2.5 text-[13px] leading-relaxed text-fg outline-none placeholder:text-mut focus-visible:border-acc/60 slim-scroll"
              placeholder={"Cảnh 1: toàn cảnh thung lũng lúc bình minh...\nCảnh 2: cận cảnh nhân vật chính...\nCảnh 3: ..."}
              value={batchText}
              onChange={(e) => setBatchText(e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Ảnh tham chiếu i2i (tuỳ chọn)"
              htmlFor="fb-batch-ref"
              hint="Đường dẫn file ảnh local — điền để chạy image2image cho mọi dòng."
            >
              <input
                id="fb-batch-ref"
                className="w-full h-9 rounded-ctl border border-line2 bg-panel2 px-3 font-mono text-[12px] text-fg outline-none placeholder:text-mut focus-visible:border-acc/60"
                placeholder="out/outputs/.../shot_001_t2i.jpg"
                value={batchRef}
                onChange={(e) => setBatchRef(e.target.value)}
              />
            </Field>
            <Field
              label="Q_target (ảnh/account)"
              htmlFor="fb-batch-q"
              hint="Ngưỡng tải chuẩn mỗi account. N_alloc = min(N, M_RAM, ⌈J/Q⌉)."
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

          <p className="text-[11.5px] leading-relaxed text-mut">
            J = {batchLines.length || 0} ảnh · N khả dụng {p.pool?.n_available ?? "?"} · M_RAM{" "}
            {p.pool?.max_active_browsers ?? "?"} · dự kiến N_alloc = {predictedN}. Mỗi tài khoản được
            đánh thức khi đến lượt; account rảnh còn lại giữ standby (không mở browser).
          </p>
        </>
      ) : (
        <>
          {/* Prompt ------------------------------------------------------------ */}
          <Field
            label="Prompt"
            htmlFor="fb-prompt"
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
            <Field label="Tỷ lệ khung" htmlFor="fb-aspect" hint="Đã kiểm chứng end-to-end (aspect 3).">
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
            <Field label="Seed" htmlFor="fb-seed" hint="Số nguyên 1 đến 2³¹−1. Bỏ trống = ngẫu nhiên.">
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
        <p className="text-[11.5px] leading-relaxed text-mut">
          {batchOn
            ? "Batch: mỗi ảnh được nhận ≈ 1 credit, bị từ chối = 0 credit. Batch dry-run: luôn 0 credit (vẫn capture request app, i2i vẫn đính ảnh nhưng không gửi)."
            : "Tạo ảnh: khoảng 1 credit nếu Google nhận ảnh, 0 credit nếu bị từ chối. Dry-run: luôn 0 credit."}
        </p>

        {formErr ? (
          <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-err">
            <WarningCircle size={14} className="mt-0.5 shrink-0" />
            {formErr}
          </p>
        ) : null}

        {!p.bridgeReady ? (
          <p className="flex items-start gap-1.5 text-[11.5px] leading-relaxed text-warn">
            <WarningCircle size={14} className="mt-0.5 shrink-0" />
            <span>
              CloakBrowser chưa kết nối (CDP 9222). Với pool, browser sẽ được đánh thức khi chạy job:
              <span className="font-mono"> python -m src.WebUI.app</span> đã bật pool tự launch hồ sơ trong{" "}
              <span className="font-mono">browser_vault/</span>.
            </span>
          </p>
        ) : (
          <p className="text-[11.5px] leading-relaxed text-mut">
            Khi job chạy, playground điều khiển tab Flow trong CloakBrowser. Tránh thao tác tab đó
            cho tới khi job xong.
          </p>
        )}
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

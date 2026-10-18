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
import type { Project } from "../types";
import { Btn, Field, IconBtn, Panel } from "./ui";
import { api } from "../api";

export interface GenRequest {
  project_id: string;
  prompt: string;
  aspect: number;
  seed: number | null;
}

interface Props {
  projects: Project[];
  projectsLoading: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  busy: boolean;
  bridgeReady: boolean;
  onRealRun: (req: GenRequest) => void;
  onDryRun: (req: GenRequest) => void;
  onRefreshProjects: () => void;
  onCreateProject: (title: string) => void;
  onAddProject: (ref: string) => Promise<void>;
}

const PROMPT_KEY = "fb_prompt_draft";

export function ComposePanel(p: Props) {
  const [prompt, setPrompt] = useState(() => localStorage.getItem(PROMPT_KEY) ?? "");
  const [seedStr, setSeedStr] = useState("");
  const [formErr, setFormErr] = useState<string | null>(null);

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

  const doReal = () => {
    const req = validate();
    if (req) p.onRealRun(req);
  };
  const doDry = () => {
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

      {/* Actions ------------------------------------------------------------ */}
      <div className="flex flex-col gap-2.5">
        <div className="flex gap-2">
          <Btn variant="primary" icon={<Sparkle size={15} weight="fill" />} disabled={!canRun} onClick={doReal} className="flex-1">
            Tạo ảnh
          </Btn>
          <Btn variant="ghost" icon={<Flask size={15} />} disabled={!canRun} onClick={doDry} className="flex-1">
            Dry-run
          </Btn>
        </div>
        <p className="text-[11.5px] leading-relaxed text-mut">
          Tạo ảnh: khoảng 1 credit nếu Google nhận ảnh, 0 credit nếu bị từ chối. Dry-run: luôn 0 credit.
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
              CloakBrowser chưa kết nối (CDP 9222). Khởi động bằng:
              <span className="font-mono"> python src/BrowserHost/launch_profile.py --profile flow_main --wait</span>
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

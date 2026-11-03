import { useMemo } from "react";
import { Image as ImageIcon, Plus } from "@phosphor-icons/react";
import type { ItemScope, LibraryItem } from "../../../types";
import {
  NodeDropdownPill,
  OrderBadge,
  SeedDropdownPill,
} from "../../node-badge/NodeBadges";
import { PromptPreviewCard } from "../../prompt/PromptBits";
import { ITEM_SCOPE_OPTIONS } from "../constants";
import type { CanvasNode, FocusLink, HoverRefInfo } from "../types";
import { PromptAgentRow } from "./PromptAgentRow";
import { sourceLabel, type NodeSources } from "./nodeSources";
import type { NodeOptionLists } from "./optionLists";
import type { CardDropdown, NodeBodyActions } from "./types";

/** Image-generation node body: reference strip, prompt, item flag and option pills. */
export function ImageNodeBody({
  n,
  options,
  sources,
  nodeSkills,
  dropdown,
  actions,
  wfBusy,
  aiGeneratingId,
  onGenerateAiPrompt,
  itemLibrary,
  focusLink,
  onFocusLink,
  onHoverRef,
}: {
  n: CanvasNode;
  options: NodeOptionLists;
  sources: NodeSources;
  nodeSkills: { id: string; name: string }[];
  dropdown: CardDropdown;
  actions: NodeBodyActions;
  wfBusy: boolean;
  aiGeneratingId?: string | null;
  onGenerateAiPrompt?: (id: string) => void;
  itemLibrary?: LibraryItem[];
  focusLink?: FocusLink | null;
  onFocusLink?: (link: FocusLink | null) => void;
  onHoverRef?: (info: HoverRefInfo | null) => void;
}) {
  const { imageRatios, imageModels, imageCounts, imageDefaultModel } = options;
  const { connectedSources, availableOptions, sourceBlocked } = sources;

  const ratioItems = useMemo(() => {
    const base = imageRatios.length ? imageRatios : ["16:9", "4:3", "1:1", "3:4", "9:16"];
    const list = base.includes(n.aspectRatio) ? base : [n.aspectRatio, ...base];
    const hints: Record<string, string> = {
      "9:16": "Dọc (TikTok, Shorts)",
      "16:9": "Ngang (YouTube)",
      "1:1": "Vuông (Instagram)",
      "4:3": "Ngang cổ điển",
      "3:4": "Dọc chân dung",
    };
    return list.map((r) => ({
      value: r,
      label: r,
      hint: hints[r],
    }));
  }, [imageRatios, n.aspectRatio]);

  const imageModelItems = useMemo(() => {
    return imageModels.map((m) => ({
      value: m.id,
      label: m.label,
      hint: m.id === imageDefaultModel ? "Mặc định" : undefined,
    }));
  }, [imageModels, imageDefaultModel]);

  const imageCountItems = useMemo(() => {
    const list = imageCounts.length ? imageCounts : [1, 2, 3, 4];
    return list.map((c) => ({
      value: c,
      label: `${c} ảnh`,
      hint: `x${c}`,
    }));
  }, [imageCounts]);

  const itemScopeItems = useMemo(() => {
    return ITEM_SCOPE_OPTIONS.map((opt) => ({
      value: opt.value,
      label: opt.label,
      hint: opt.hint,
    }));
  }, []);

  return (
    <>
      <div className="flex flex-col gap-1.5">
        {/* Tiêu đề + "Xóa hết" trên một dòng riêng; strip chip chiếm trọn bề ngang
            node bên dưới để 5+ ảnh xuống dòng gọn (3–4 chip/hàng) thay vì 1 chip/hàng. */}
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold text-mut truncate">
            Ảnh tham chiếu ({connectedSources.length})
          </span>
          {connectedSources.length > 0 && (
            <button
              type="button"
              onClick={() => actions.onSourcesChange([])}
              className="text-[9.5px] text-mut hover:text-err cursor-pointer shrink-0 whitespace-nowrap"
              title="Bỏ tất cả ảnh tham chiếu"
            >
              Xóa hết
            </button>
          )}
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {connectedSources.map((src, idx) => (
            <div
              key={src.id}
              className="group/ref relative shrink-0"
              onMouseEnter={(e) => {
                onFocusLink?.({ from: src.id, to: n.id });
                const r = e.currentTarget.getBoundingClientRect();
                onHoverRef?.({ src, index: idx + 1, x: r.left, y: r.bottom });
              }}
              onMouseLeave={() => {
                onFocusLink?.(null);
                onHoverRef?.(null);
              }}
            >
              <div
                className={`inline-flex items-center gap-1 h-6 pl-1 pr-1.5 rounded-full border text-[10px] font-semibold transition-colors ${
                  focusLink?.from === src.id && focusLink?.to === n.id
                    ? "border-warn/70 bg-warn/20 text-warn"
                    : "border-line2 bg-panel2 text-dim hover:border-warn/50 hover:text-fg"
                }`}
                title={
                  src.type === "ref"
                    ? `${src.fileName ?? src.id} — Image ${idx + 1}`
                    : `${sourceLabel(src)} — Image ${idx + 1}`
                }
              >
                <OrderBadge index={idx + 1} size="xs" />
                {src.fileUrl ? (
                  <img src={src.fileUrl} alt="" className="size-4 rounded-[3px] object-cover" />
                ) : (
                  <ImageIcon size={11} className="text-mut" />
                )}
              </div>
            </div>
          ))}
          {availableOptions.length > 0 && (
            <button
              type="button"
              onClick={() => actions.onOpenDrawer(n.id, "sources")}
              className="shrink-0 grid place-items-center size-6 rounded-full border border-dashed border-line2 text-mut hover:border-acc hover:text-acc transition-colors cursor-pointer"
              title="Nối thêm ảnh tham chiếu (mở Cấu hình)"
            >
              <Plus size={11} weight="bold" />
            </button>
          )}
          {connectedSources.length === 0 && availableOptions.length === 0 && (
            <span className="text-[9.5px] text-mut">Chưa có ảnh nào</span>
          )}
        </div>

        {sourceBlocked && (
          <p className="text-[10px] text-warn leading-snug">
            Một số node nguồn chưa có kết quả — hãy chạy trước khi chạy node này.
          </p>
        )}
      </div>

      <PromptAgentRow
        label="Prompt ảnh"
        skills={nodeSkills}
        skillId={n.agentSkillId}
        onSkillChange={(agentSkillId) => actions.onFieldChange({ agentSkillId })}
        skillTitle="Chọn skill quy chuẩn AI tạo prompt cho node này"
        autoOptionLabel="(Tự động: Ảnh Lookbook)"
        onGenerate={onGenerateAiPrompt ? () => onGenerateAiPrompt(n.id) : undefined}
        generating={aiGeneratingId === n.id}
        disabled={aiGeneratingId === n.id || wfBusy}
        generateTitle="Local AI Agent sẽ phân tích ảnh kết quả nguồn để sinh prompt chuẩn"
      />

      {/* Ô này KHÔNG gắn ảnh — ảnh tham chiếu nằm ở strip pill phía trên.
          Nó chỉ đánh dấu: ảnh node này sinh ra là **ảnh sản phẩm**, nên được chép vào
          thư viện `out/items/<project>/` ngay khi sinh xong. Tên món quyết định tên file.
          Phạm vi cắt món (Áo/Quần/Cả bộ) đã chuyển vào Drawer cho gọn node. */}
      {n.type === "image" && (
        <div className="flex items-center gap-1.5 min-w-0">
          <label className="flex items-center gap-1.5 cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={!!n.isItem}
              onChange={(e) =>
                actions.onFieldChange({
                  isItem: e.target.checked,
                  // Bật cờ thì mặc định luôn một phạm vi: để null nghĩa là agent
                  // không được chỉ định món nào và quay lại lỗi "ra chiếc áo".
                  ...(e.target.checked ? { itemScope: n.itemScope ?? "top" } : {}),
                })
              }
              className="h-3 w-3 accent-[var(--acc)] cursor-pointer"
            />
            <span className="text-[10px] font-semibold text-mut whitespace-nowrap">Ảnh sản phẩm</span>
          </label>
          {n.isItem && (
            <input
              type="text"
              value={n.itemName ?? ""}
              onChange={(e) => actions.onFieldChange({ itemName: e.target.value })}
              placeholder="Tên món…"
              list="canvas-item-library"
              className="h-6 min-w-0 flex-1 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[10px] text-fg focus:border-acc outline-none"
              title="Tên file trong thư viện: bỏ dấu, thường hoá, cách nhau bằng _"
            />
          )}
          <datalist id="canvas-item-library">
            {(itemLibrary ?? []).map((it) => (
              <option key={it.file} value={it.name} />
            ))}
          </datalist>
        </div>
      )}

      <PromptPreviewCard
        prompt={n.prompt}
        placeholder="Prompt mô tả ảnh cần tạo… bấm để sửa"
        onExpand={() => actions.onOpenPromptEditor(n.id)}
      />

      {/* Summary pills: Bấm mở dropdown chọn option trực tiếp thay vì mở drawer */}
      <div className="flex items-center gap-1 flex-wrap">
        {n.agentMode ? (
          <NodeDropdownPill
            tone="warn"
            value="Tác nhân quyết định"
            title="Flow đang bật 'Tác nhân' — bấm để tắt hoặc mở Cấu hình"
            id="agent"
            isOpen={dropdown.open === "agent"}
            onToggle={() => dropdown.toggle("agent")}
            onClose={dropdown.close}
            header="Tác nhân"
            items={[
              { value: "off", label: "Tắt Tác nhân", hint: "Tự chọn model & thông số" },
              { value: "drawer", label: "Mở Cấu hình", hint: "Xem trong Drawer" },
            ]}
            onSelect={(val) => {
              if (val === "off") actions.onFieldChange({ agentMode: false });
              else actions.onOpenDrawer(n.id, "config");
            }}
          />
        ) : (
          <>
            <NodeDropdownPill
              value={n.aspectRatio}
              title={`Tỷ lệ khung hình: ${n.aspectRatio} — bấm để đổi`}
              id="aspectRatio"
              isOpen={dropdown.open === "aspectRatio"}
              onToggle={() => dropdown.toggle("aspectRatio")}
              onClose={dropdown.close}
              header="Tỷ lệ khung hình"
              items={ratioItems}
              selectedValue={n.aspectRatio}
              onSelect={(val) => actions.onFieldChange({ aspectRatio: String(val) })}
            />
            <NodeDropdownPill
              label="Model"
              value={
                imageModels.find((m) => m.id === (n.imageModel ?? ""))?.label ??
                imageModels.find((m) => m.id === (imageDefaultModel || ""))?.label ??
                imageModels[0]?.label ??
                n.imageModel ??
                "—"
              }
              title="Model ảnh của composer Flow — bấm để đổi"
              id="imageModel"
              isOpen={dropdown.open === "imageModel"}
              onToggle={() => dropdown.toggle("imageModel")}
              onClose={dropdown.close}
              header="Chọn Model ảnh"
              width="min-w-[190px]"
              items={imageModelItems}
              selectedValue={n.imageModel ?? imageDefaultModel ?? imageModels[0]?.id}
              onSelect={(val) => actions.onFieldChange({ imageModel: String(val) })}
            />
            <NodeDropdownPill
              value={`x${n.imageCount ?? 1}`}
              title="Số ảnh mỗi lần chạy (x1..x4) — bấm để đổi"
              id="imageCount"
              isOpen={dropdown.open === "imageCount"}
              onToggle={() => dropdown.toggle("imageCount")}
              onClose={dropdown.close}
              header="Số lượng ảnh"
              align="right"
              width="min-w-[120px]"
              items={imageCountItems}
              selectedValue={n.imageCount ?? 1}
              onSelect={(val) => actions.onFieldChange({ imageCount: Number(val) })}
            />
            <SeedDropdownPill
              seed={n.seed}
              id="seed"
              isOpen={dropdown.open === "seed"}
              onToggle={() => dropdown.toggle("seed")}
              onClose={dropdown.close}
              onChangeSeed={(val) => actions.onFieldChange({ seed: val })}
              onOpenDrawer={() => actions.onOpenDrawer(n.id, "config")}
            />
          </>
        )}
        {n.isItem && (
          <NodeDropdownPill
            tone="warn"
            value={`Sản phẩm · ${ITEM_SCOPE_OPTIONS.find((o) => o.value === (n.itemScope ?? "top"))?.label ?? "Áo"}`}
            title="Ảnh sản phẩm lưu vào thư viện items/ — bấm để đổi phạm vi"
            id="itemScope"
            isOpen={dropdown.open === "itemScope"}
            onToggle={() => dropdown.toggle("itemScope")}
            onClose={dropdown.close}
            header="Phạm vi sản phẩm"
            items={itemScopeItems}
            selectedValue={n.itemScope ?? "top"}
            onSelect={(val) => actions.onFieldChange({ itemScope: val as ItemScope })}
          />
        )}
      </div>
    </>
  );
}

import type { CanvasDrawerNode } from "./types";
// Một nguồn duy nhất cho 4 phạm vi — trước đây list này được chép tay và lệch ngay khi
// thêm `coordinate_sheet`.
import { ITEM_SCOPE_OPTIONS } from "../canvas/constants";

interface Props {
  node: CanvasDrawerNode;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** Marks an image node as a product item (saved to items/) and picks the crop scope. */
export function ItemOptions({ node, onUpdateNode }: Props) {
  return (
    <div className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-2">
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={!!node.isItem}
          onChange={(e) =>
            onUpdateNode?.(node.id, {
              isItem: e.target.checked,
              ...(e.target.checked ? { itemScope: node.itemScope ?? "top" } : {}),
            })
          }
          className="h-3.5 w-3.5 accent-[var(--color-acc)] cursor-pointer"
        />
        <span className="text-[11px] font-semibold text-dim">
          Đây là ảnh sản phẩm <span className="font-normal text-mut">(lưu vào items/)</span>
        </span>
      </label>
      {node.isItem && (
        <>
          <input
            type="text"
            value={node.itemName ?? ""}
            onChange={(e) => onUpdateNode?.(node.id, { itemName: e.target.value })}
            placeholder="Tên món — vd: Áo Kiểu Nữ Donna"
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc"
          />
          {/* 4 lựa chọn ⇒ lưới 2×2. Xếp một hàng thì "Quần / Váy" và "Bộ phối" bị bóp
              chữ trong drawer hẹp. */}
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-mut">Cắt món</span>
            <div className="grid grid-cols-2 gap-1">
              {ITEM_SCOPE_OPTIONS.map((opt) => {
                const active = (node.itemScope ?? "top") === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onUpdateNode?.(node.id, { itemScope: opt.value })}
                    title={opt.hint}
                    className={`h-6 rounded-[4px] text-[10px] font-semibold border transition-colors cursor-pointer ${
                      active
                        ? "border-acc bg-acc/15 text-acc"
                        : "border-line2 bg-panel text-dim hover:text-fg"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            {node.prompt.trim() !== "" && (
              <p className="text-[10px] text-mut leading-snug">
                Đổi phạm vi <span className="font-semibold text-warn">không</span> tự viết lại
                prompt — bấm <span className="font-semibold text-acc">AI Prompt</span> trên node.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

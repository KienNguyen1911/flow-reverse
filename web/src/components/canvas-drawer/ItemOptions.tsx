import type { CanvasDrawerNode } from "./types";

/** Phạm vi ảnh sản phẩm — phải khớp `ITEM_SCOPE_OPTIONS` trong CanvasPanel. */
const ITEM_SCOPE_OPTIONS: { value: "top" | "bottom" | "full_set"; label: string; hint: string }[] = [
  { value: "top", label: "Áo", hint: "Chỉ món mặc trên: áo, camisole, cardigan" },
  { value: "bottom", label: "Quần / Váy", hint: "Chỉ món mặc dưới: quần, váy, shorts" },
  { value: "full_set", label: "Cả bộ", hint: "Các món xếp cạnh nhau trên một ảnh — không tách nền được" },
];

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
          <div className="flex items-center gap-1">
            <span className="text-[10px] font-semibold text-mut shrink-0">Cắt món</span>
            <div className="flex items-center gap-1 flex-1">
              {ITEM_SCOPE_OPTIONS.map((opt) => {
                const active = (node.itemScope ?? "top") === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onUpdateNode?.(node.id, { itemScope: opt.value })}
                    title={opt.hint}
                    className={`flex-1 h-6 rounded-[4px] text-[10px] font-semibold border transition-colors cursor-pointer ${
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
          </div>
        </>
      )}
    </div>
  );
}

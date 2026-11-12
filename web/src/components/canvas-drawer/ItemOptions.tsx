import type { CanvasDrawerNode } from "./types";

interface Props {
  node: CanvasDrawerNode;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** Marks an image node as a coordinate sheet (saved to items/) — there is one output, no scope pick. */
export function ItemOptions({ node, onUpdateNode }: Props) {
  return (
    <div className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex flex-col gap-2">
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={!!node.isItem}
          onChange={(e) => onUpdateNode?.(node.id, { isItem: e.target.checked })}
          className="h-3.5 w-3.5 accent-[var(--color-acc)] cursor-pointer"
        />
        <span className="text-[11px] font-semibold text-dim">
          Bảng phối <span className="font-normal text-mut">(lưu vào items/)</span>
        </span>
      </label>
      {node.isItem && (
        <>
          <input
            type="text"
            value={node.itemName ?? ""}
            onChange={(e) => onUpdateNode?.(node.id, { itemName: e.target.value })}
            placeholder="Tên bộ phối — vd: Set Y2K"
            className="h-7 rounded-ctl border border-line2 bg-panel px-1.5 text-[11.5px] text-fg outline-none focus:border-acc"
          />
          <p className="text-[10px] text-mut leading-snug">
            Ảnh ra là <span className="font-semibold text-dim">coordinate sheet</span>: cả bộ +
            callout, 3 ô detail, palette 5 màu. Có chữ sẵn nên{" "}
            <span className="font-semibold text-warn">không</span> tách nền được và{" "}
            <span className="font-semibold text-warn">không</span> dùng làm first frame.
          </p>
        </>
      )}
    </div>
  );
}

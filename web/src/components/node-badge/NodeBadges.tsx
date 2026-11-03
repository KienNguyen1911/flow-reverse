import { useEffect, useState } from "react";
import { CaretDown, Check, Image as ImageIcon } from "@phosphor-icons/react";

/**
 * Badges and pills for a canvas node body: the order badge, the summary pill, the generic
 * dropdown, and the seed picker. They only read a node's settings and forward the user to the
 * drawer, so they share one reason to change: how a node's settings are summarised.
 */

/** Amber/gold index badge shared by the source node header, chips and drawer rows. */
export function OrderBadge({
  index,
  size = "sm",
  muted = false,
  className = "",
}: {
  index: number;
  size?: "xs" | "sm" | "md";
  muted?: boolean;
  className?: string;
}) {
  const dims =
    size === "xs" ? "h-[15px] min-w-[15px] px-1 text-[9px]" : size === "md" ? "h-5 min-w-5 px-1.5 text-[11px]" : "h-[18px] min-w-[18px] px-1 text-[10px]";
  const tone = muted
    ? "border-line2 bg-panel2 text-mut"
    : "border-warn/55 bg-warn/15 text-warn";
  return (
    <span
      className={`inline-grid place-items-center rounded-[4px] border font-mono font-bold leading-none tabular-nums shrink-0 ${dims} ${tone} ${className}`}
      title={`Ảnh tham chiếu #${index} — khớp với "Image ${index}" trong prompt`}
    >
      #{index}
    </span>
  );
}

/** One-line pill used for compact config summaries on the node body. */
export function SummaryPill({
  label,
  value,
  title,
  onClick,
  tone = "neutral",
}: {
  label?: string;
  value: string;
  title?: string;
  onClick?: () => void;
  tone?: "neutral" | "warn";
}) {
  const toneCls =
    tone === "warn"
      ? "border-warn/35 bg-warn/10 text-warn hover:border-warn/60"
      : "border-line2 bg-panel2 text-dim hover:border-line2/80 hover:text-fg";
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      title={title ?? "Mở Cấu hình trong bảng điều khiển bên phải"}
      className={`inline-flex items-center gap-1 h-[22px] px-2 rounded-full border text-[10px] font-semibold whitespace-nowrap transition-colors cursor-pointer ${toneCls}`}
    >
      {label ? <span className="opacity-60 font-medium">{label}</span> : null}
      <span className="truncate max-w-[110px]">{value}</span>
    </button>
  );
}

export interface DropdownItem<T = string | number> {
  value: T;
  label: string;
  hint?: string;
  disabled?: boolean;
}

/**
 * Clickable badge with an in-place dropdown list for picking node options directly
 * without having to open the right drawer.
 */
export function NodeDropdownPill<T = string | number>({
  id,
  label,
  value,
  title,
  tone = "neutral",
  isOpen,
  onToggle,
  onClose,
  items,
  selectedValue,
  onSelect,
  header,
  align = "left",
  width,
  children,
}: {
  id?: string;
  label?: string;
  value: string;
  title?: string;
  tone?: "neutral" | "warn";
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  items?: DropdownItem<T>[];
  selectedValue?: T | null;
  onSelect?: (val: T) => void;
  header?: string;
  align?: "left" | "right";
  width?: string;
  children?: React.ReactNode;
}) {
  const toneCls = isOpen
    ? "border-acc bg-acc/15 text-acc shadow-sm"
    : tone === "warn"
      ? "border-warn/35 bg-warn/10 text-warn hover:border-warn/60 hover:bg-warn/20"
      : "border-line2 bg-panel2 text-dim hover:border-line2/80 hover:text-fg hover:bg-panel";

  return (
    <div className="relative inline-block node-dropdown-container" data-dropdown-id={id}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
        onPointerDown={(e) => e.stopPropagation()}
        title={title ?? "Bấm để chọn trực tiếp"}
        className={`inline-flex items-center gap-1 h-[22px] px-2 rounded-full border text-[10px] font-semibold whitespace-nowrap transition-all cursor-pointer group ${toneCls}`}
      >
        {label ? <span className="opacity-60 font-medium">{label}</span> : null}
        <span className="truncate max-w-[110px]">{value}</span>
        <CaretDown
          size={9}
          weight="bold"
          className={`opacity-50 group-hover:opacity-100 transition-transform ${
            isOpen ? "rotate-180 text-acc opacity-100" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          className={`absolute top-full mt-1 z-50 ${
            align === "right" ? "right-0" : "left-0"
          } ${width ?? "min-w-[150px] max-w-[260px]"} rounded-ctl border border-line2 bg-panel/95 backdrop-blur-md p-1 shadow-2xl shadow-black/90 select-none animate-in fade-in zoom-in-95 duration-100`}
        >
          {header && (
            <div className="px-2 py-1 text-[9.5px] font-bold text-mut uppercase tracking-wider border-b border-line mb-1">
              {header}
            </div>
          )}

          {children ? (
            children
          ) : (
            <div className="max-h-[220px] overflow-y-auto slim-scroll flex flex-col gap-0.5">
              {items?.map((item) => {
                const isSelected = selectedValue === item.value;
                return (
                  <button
                    key={String(item.value)}
                    type="button"
                    disabled={item.disabled}
                    onClick={() => {
                      if (item.disabled) return;
                      onSelect?.(item.value);
                      onClose();
                    }}
                    className={`w-full flex items-center justify-between gap-2 px-2 py-1 rounded-[4px] text-left text-[11px] transition-colors cursor-pointer ${
                      item.disabled
                        ? "opacity-40 cursor-not-allowed text-mut"
                        : isSelected
                          ? "bg-acc/15 text-acc font-semibold"
                          : "text-dim hover:text-fg hover:bg-panel2"
                    }`}
                  >
                    <span className="truncate">{item.label}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      {item.hint && <span className="text-[9.5px] text-mut">{item.hint}</span>}
                      {isSelected && <Check size={11} weight="bold" className="text-acc" />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Popover pill for quick seed management (random vs custom number) */
export function SeedDropdownPill({
  id = "seed",
  seed,
  isOpen,
  onToggle,
  onClose,
  onChangeSeed,
  onOpenDrawer,
}: {
  id?: string;
  seed: number | null;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onChangeSeed: (s: number | null) => void;
  onOpenDrawer?: () => void;
}) {
  const [inputVal, setInputVal] = useState<string>(seed != null ? String(seed) : "");

  useEffect(() => {
    if (isOpen) {
      setInputVal(seed != null ? String(seed) : "");
    }
  }, [isOpen, seed]);

  const applyCustom = () => {
    const trimmed = inputVal.trim();
    if (!trimmed) {
      onChangeSeed(null);
    } else {
      const num = parseInt(trimmed, 10);
      if (!isNaN(num)) onChangeSeed(num);
    }
    onClose();
  };

  const handleRandomize = () => {
    const rand = Math.floor(10000000 + Math.random() * 90000000);
    setInputVal(String(rand));
    onChangeSeed(rand);
    onClose();
  };

  return (
    <NodeDropdownPill
      id={id}
      value={`Seed: ${seed ?? "random"}`}
      title="Seed — bấm để chọn hoặc nhập seed cố định"
      isOpen={isOpen}
      onToggle={onToggle}
      onClose={onClose}
      header="Cấu hình Seed"
      align="right"
      width="min-w-[190px]"
    >
      <div className="flex flex-col gap-1 p-1">
        <button
          type="button"
          onClick={() => {
            onChangeSeed(null);
            onClose();
          }}
          className={`w-full flex items-center justify-between px-2 py-1.5 rounded-[4px] text-[11px] transition-colors cursor-pointer ${
            seed == null
              ? "bg-acc/15 text-acc font-semibold"
              : "text-dim hover:text-fg hover:bg-panel2"
          }`}
        >
          <span className="flex items-center gap-1.5">
            <span>🎲</span>
            <span>Ngẫu nhiên (random)</span>
          </span>
          {seed == null && <Check size={11} weight="bold" className="text-acc" />}
        </button>

        <div className="border-t border-line my-0.5" />

        <div className="flex flex-col gap-1 pt-0.5">
          <div className="flex items-center justify-between text-[10px] text-mut">
            <span>Nhập seed:</span>
            <button
              type="button"
              onClick={handleRandomize}
              className="text-[9.5px] text-acc hover:underline flex items-center gap-0.5 cursor-pointer"
              title="Tạo ngẫu nhiên 8 số mới và lưu ngay"
            >
              <span>Tạo số mới</span>
            </button>
          </div>
          <div className="flex items-center gap-1">
            <input
              type="number"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="VD: 42815193"
              className="h-6 w-full rounded border border-line2 bg-panel2 px-1.5 text-[10.5px] text-fg focus:border-acc outline-none font-mono"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  applyCustom();
                }
              }}
            />
            <button
              type="button"
              onClick={applyCustom}
              className="h-6 px-2 rounded bg-acc text-accink font-bold text-[10px] hover:bg-acc2 shrink-0 cursor-pointer"
            >
              Lưu
            </button>
          </div>
        </div>

        {onOpenDrawer && (
          <button
            type="button"
            onClick={() => {
              onClose();
              onOpenDrawer();
            }}
            className="w-full text-[9.5px] text-mut hover:text-fg text-center py-1 mt-1 border-t border-line cursor-pointer"
          >
            Mở Cấu hình nâng cao →
          </button>
        )}
      </div>
    </NodeDropdownPill>
  );
}

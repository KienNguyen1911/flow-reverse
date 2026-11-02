import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowsOut, Check, Copy, Image as ImageIcon } from "@phosphor-icons/react";

/**
 * Shared node-body primitives for the canvas.
 *
 * The node cards used to embed the full edit form. That made them tall, and a
 * `textarea` inside a `scale()`-ed canvas fights the pan/zoom wheel handler, so
 * long prompts were painful to read. Editing now lives in the Right Inspector
 * Drawer / the prompt modal; the card only renders a clamped preview plus a row
 * of summary pills that forward the user to the drawer.
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

/**
 * Highlight `Image 1` / `Image 2` / `[TAG]` tokens so the reader can line the
 * prompt up with the numbered reference chips. Returns text nodes + marks; no
 * HTML injection.
 */
export function highlightPrompt(prompt: string): React.ReactNode[] {
  const re = /(\bImage\s+\d+\b|\[[^\]]{1,60}\])/gi;
  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(prompt))) {
    if (m.index > last) out.push(prompt.slice(last, m.index));
    const isRef = /^image/i.test(m[0]);
    out.push(
      <mark
        key={`h${key++}`}
        className={
          isRef
            ? "bg-warn/20 text-warn rounded-[3px] px-[2px] font-semibold"
            : "bg-acc/15 text-acc rounded-[3px] px-[2px]"
        }
      >
        {m[0]}
      </mark>,
    );
    last = m.index + m[0].length;
  }
  if (last < prompt.length) out.push(prompt.slice(last));
  return out;
}

function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

export function useCopyPrompt(prompt: string) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);
  const copy = () => {
    void navigator.clipboard?.writeText(prompt ?? "").then(
      () => setCopied(true),
      () => setCopied(false),
    );
  };
  return { copied, copy };
}

/**
 * Read-only, 3-line clamped prompt card for the node body. Wheel events are
 * swallowed so a scroll gesture over the card cannot zoom/pan the canvas.
 */
export function PromptPreviewCard({
  prompt,
  placeholder,
  lines = 3,
  onExpand,
  className = "",
}: {
  prompt: string;
  placeholder: string;
  lines?: number;
  onExpand: () => void;
  className?: string;
}) {
  const empty = !prompt.trim();
  const clampStyle =
    lines === 3
      ? { display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical" as const, overflow: "hidden" }
      : { display: "-webkit-box", WebkitLineClamp: lines, WebkitBoxOrient: "vertical" as const, overflow: "hidden" };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={(e) => {
        e.stopPropagation();
        onExpand();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onExpand();
        }
      }}
      onWheel={(e) => e.stopPropagation()}
      title="Bấm để mở trình sửa prompt"
      className={`group/prompt relative rounded-ctl border border-line2 bg-panel2/80 px-2 py-1.5 text-left cursor-text transition-colors hover:border-acc/50 ${className}`}
    >
      <p
        className={`text-[10.5px] font-mono leading-[1.45] break-words pr-6 ${
          empty ? "text-mut italic" : "text-dim"
        }`}
        style={clampStyle}
      >
        {empty ? placeholder : highlightPrompt(prompt)}
      </p>
      <span className="absolute top-1 right-1 grid place-items-center size-5 rounded-[5px] bg-panel border border-line2 text-mut opacity-0 group-hover/prompt:opacity-100 group-hover/prompt:text-acc transition-all">
        <ArrowsOut size={10} weight="bold" />
      </span>
    </div>
  );
}

/**
 * Full prompt editor: auto-resizes between `minHeight` and 60vh, highlights the
 * reference tokens while reading, and exposes copy + word/char counters.
 */
export function PromptEditor({
  value,
  onChange,
  placeholder,
  minHeight = 220,
  maxChars,
  autoFocus = false,
  fill = false,
  footerRight,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  minHeight?: number;
  maxChars?: number;
  autoFocus?: boolean;
  /** Trong modal: cao theo khung (flex), không auto-resize ⇒ không nhảy kích thước. */
  fill?: boolean;
  footerRight?: React.ReactNode;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [editing, setEditing] = useState(false);
  const { copied, copy } = useCopyPrompt(value);
  const [expanded, setExpanded] = useState(false);
  const words = useMemo(() => countWords(value), [value]);
  const over = maxChars ? value.length > maxChars : false;

  // Auto-resize to content, capped at 60vh (or the viewport when expanded).
  // Chế độ `fill` để CSS lo chiều cao: modal giữ nguyên kích thước ở cả 2 mode.
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    if (fill) {
      el.style.height = "";
      return;
    }
    el.style.height = "auto";
    const cap = expanded
      ? Math.max(240, Math.floor(window.innerHeight * 0.62))
      : Math.max(minHeight, Math.floor(window.innerHeight * 0.6));
    el.style.height = `${Math.min(Math.max(minHeight, el.scrollHeight + 2), cap)}px`;
  }, [value, minHeight, expanded, fill]);

  useEffect(() => {
    if (autoFocus) taRef.current?.focus();
  }, [autoFocus]);

  const boxCls = fill
    ? "flex-1 min-h-0 w-full rounded-ctl border bg-panel2 p-3 text-[12.5px] leading-[1.7] text-fg select-text whitespace-pre-wrap break-words overflow-y-auto slim-scroll"
    : "";
  const writingCls = `w-full resize-none rounded-ctl border bg-panel2 p-3 text-[12px] font-mono leading-[1.7] text-fg outline-none slim-scroll transition-colors ${
    over ? "border-err/60 focus:border-err" : "border-line2 focus:border-acc"
  }`;

  return (
    <div className={fill ? "flex flex-col gap-1.5 flex-1 min-h-0" : "flex flex-col gap-1.5"}>
      <div className={fill ? "relative flex-1 min-h-0 flex flex-col" : "relative"}>
        {editing ? (
          <textarea
            ref={taRef}
            value={value}
            autoFocus={autoFocus}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setEditing(true)}
            onBlur={() => setEditing(false)}
            onWheel={(e) => e.stopPropagation()}
            placeholder={placeholder}
            spellCheck={false}
            style={fill ? undefined : { minHeight }}
            className={`${writingCls} ${fill ? "h-full flex-1 min-h-0" : ""}`}
          />
        ) : (
          <div
            role="button"
            tabIndex={0}
            onClick={() => setEditing(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setEditing(true);
            }}
            style={fill ? undefined : { minHeight }}
            className={`${boxCls || "w-full rounded-ctl border border-line2 bg-panel2 p-3 text-[12px] font-mono leading-[1.7] text-fg select-text whitespace-pre-wrap break-words overflow-y-auto slim-scroll cursor-text"} ${
              fill ? "border-line2 cursor-text" : ""
            }`}
          >
            {value.trim() ? highlightPrompt(value) : <span className="text-mut italic">{placeholder}</span>}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={copy}
            disabled={!value.trim()}
            className="inline-flex items-center gap-1 h-6 px-2 rounded-ctl border border-line2 bg-panel2 text-[10.5px] font-semibold text-dim hover:text-fg hover:border-line2/80 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
          >
            {copied ? <Check size={11} weight="bold" className="text-ok" /> : <Copy size={11} />}
            <span>{copied ? "Đã chép" : "Copy Prompt"}</span>
          </button>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 h-6 px-2 rounded-ctl border border-line2 bg-panel2 text-[10.5px] font-semibold text-dim hover:text-fg hover:border-line2/80 transition-colors cursor-pointer"
            title="Phóng to khung soạn prompt"
          >
            <ArrowsOut size={11} weight="bold" />
            <span>{expanded ? "Thu gọn" : "Phóng to"}</span>
          </button>
          {footerRight}
        </div>
        <span className={`text-[10px] font-mono tabular-nums ${over ? "text-err font-bold" : "text-mut"}`}>
          {words} từ · {value.length}
          {maxChars ? `/${maxChars}` : ""} ký tự
        </span>
      </div>
    </div>
  );
}

/**
 * Centered modal used by "Mở rộng" on the node body: the same editor, wide,
 * without leaving the canvas.
 */
export function PromptEditorModal({
  open,
  title,
  value,
  onChange,
  onClose,
  placeholder,
  maxChars,
  footer,
}: {
  open: boolean;
  title: string;
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
  placeholder?: string;
  maxChars?: number;
  footer?: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] grid place-items-center bg-black/65 backdrop-blur-sm p-4"
      onClick={onClose}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* Kích thước CỐ ĐỊNH: trước đây khung co giãn theo nội dung nên nhảy
          kích thước khi chuyển giữa chế độ xem và soạn thảo. */}
      <div
        className="w-full max-w-[820px] h-[86vh] max-h-[86vh] rounded-panel border border-line2 bg-panel shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 px-4 h-12 border-b border-line2 bg-panel2 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="grid place-items-center size-6 rounded-ctl bg-acc/15 text-acc shrink-0">
              <ImageIcon size={13} />
            </span>
            <span className="text-[12.5px] font-bold text-fg truncate">{title}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-7 px-2.5 rounded-ctl border border-line2 bg-panel text-[11px] font-semibold text-dim hover:text-fg cursor-pointer transition-colors"
          >
            Đóng (Esc)
          </button>
        </header>
        <div className="flex-1 min-h-0 p-4 overflow-y-auto slim-scroll flex flex-col gap-3">
          <PromptEditor
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            minHeight={280}
            maxChars={maxChars}
            autoFocus
            fill
          />
          {footer}
        </div>
      </div>
    </div>
  );
}

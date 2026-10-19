import type { ButtonHTMLAttributes, ReactNode } from "react";
import { CircleNotch, Info } from "@phosphor-icons/react";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-panel border border-line bg-panel ${className}`}>{children}</section>;
}

export type BtnVariant = "primary" | "ghost" | "solid" | "danger";

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 rounded-ctl px-3.5 h-9 text-[13.5px] font-semibold " +
  "transition-colors duration-150 select-none active:translate-y-px " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acc/80 " +
  "disabled:opacity-45 disabled:pointer-events-none";

const BTN_STYLES: Record<BtnVariant, string> = {
  primary: "bg-acc text-accink hover:bg-acc2",
  ghost: "border border-line2 text-dim hover:text-fg hover:border-mut/70",
  solid: "border border-line2 bg-panel2 text-fg hover:bg-line",
  danger: "border border-err/40 text-err hover:bg-err/10",
};

/** Shared class string so anchors can render as buttons too. */
export function btnCls(variant: BtnVariant = "ghost", extra = ""): string {
  return `${BTN_BASE} ${BTN_STYLES[variant]} ${extra}`;
}

export function Btn({
  variant = "ghost",
  busy = false,
  icon,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  busy?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button className={btnCls(variant, className)} disabled={busy || rest.disabled} {...rest}>
      {busy ? <CircleNotch className="animate-spin" size={15} /> : icon}
      {children}
    </button>
  );
}

export function IconBtn({
  label,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={
        "inline-grid place-items-center size-9 rounded-ctl border border-line2 text-dim " +
        "hover:text-fg hover:border-mut/70 transition-colors duration-150 active:translate-y-px " +
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-acc/80 " +
        "disabled:opacity-45 disabled:pointer-events-none " + className
      }
      {...rest}
    >
      {children}
    </button>
  );
}

type Tone = "neutral" | "ok" | "acc" | "warn" | "err";

const DOT: Record<Tone, string> = {
  neutral: "bg-mut",
  ok: "bg-ok",
  acc: "bg-acc",
  warn: "bg-warn",
  err: "bg-err",
};

export function Chip({
  tone = "neutral",
  live = false,
  children,
  className = "",
  title,
}: {
  tone?: Tone;
  live?: boolean;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={
        "inline-flex items-center gap-1.5 rounded-full border border-line2 bg-panel2/70 px-2.5 h-7 " +
        "text-[11.5px] font-medium text-dim whitespace-nowrap " + className
      }
    >
      <span className={`size-1.5 rounded-full ${DOT[tone]} ${live ? "animate-pulse" : ""}`} />
      {children}
    </span>
  );
}

export function InfoTip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children?: ReactNode;
  side?: "top" | "bottom" | "right";
}) {
  return (
    <span className="group relative inline-flex items-center cursor-help">
      {children || (
        <span className="text-mut hover:text-fg transition-colors">
          <Info size={13} weight="bold" />
        </span>
      )}
      <span
        role="tooltip"
        className={`pointer-events-none absolute z-50 invisible opacity-0 group-hover:visible group-hover:opacity-100 transition-all duration-150 rounded-ctl border border-line2 bg-panel px-2.5 py-1.5 text-[11.5px] leading-relaxed text-fg shadow-2xl whitespace-normal w-60 sm:w-72 ${
          side === "top"
            ? "bottom-full left-1/2 -translate-x-1/2 mb-1.5"
            : side === "bottom"
            ? "top-full left-1/2 -translate-x-1/2 mt-1.5"
            : "left-full top-1/2 -translate-y-1/2 ml-1.5"
        }`}
      >
        {content}
      </span>
    </span>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  info,
  right,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  info?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <label htmlFor={htmlFor} className="text-[12.5px] font-semibold text-dim">
            {label}
          </label>
          {info && <InfoTip content={info} />}
        </div>
        {right}
      </div>
      {children}
      {hint ? <p className="text-[11px] leading-relaxed text-mut">{hint}</p> : null}
    </div>
  );
}

export function Spinner({ size = 14, className = "" }: { size?: number; className?: string }) {
  return <CircleNotch className={`animate-spin ${className}`} size={size} />;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; icon?: ReactNode; badge?: string }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-line2 bg-panel px-2 pt-1.5 slim-scroll">
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
              isActive
                ? "border-acc text-acc"
                : "border-transparent text-dim hover:text-fg"
            }`}
          >
            {t.icon}
            <span>{t.label}</span>
            {t.badge ? (
              <span className="ml-0.5 rounded-full bg-acc/15 px-1.5 py-0.5 text-[10px] font-bold text-acc">
                {t.badge}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

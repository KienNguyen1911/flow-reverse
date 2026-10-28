import { useEffect, type ReactNode } from "react";
import { X } from "@phosphor-icons/react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
  extraHeader?: ReactNode;
  children: ReactNode;
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  icon,
  badge,
  extraHeader,
  children,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="w-[80vw] h-[80vh] flex flex-col rounded-panel border border-line2 bg-panel shadow-2xl overflow-hidden relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-panel2 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            {icon && (
              <span className="grid place-items-center size-7 rounded-ctl bg-acc/15 text-acc shrink-0">
                {icon}
              </span>
            )}
            <div className="flex items-center gap-2 min-w-0">
              <h2 className="text-[15px] font-bold text-fg truncate">{title}</h2>
              {badge}
            </div>
            {subtitle && (
              <span className="hidden md:inline text-[12px] text-mut border-l border-line pl-2.5 truncate">
                {subtitle}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {extraHeader}
            <button
              type="button"
              onClick={onClose}
              className="inline-grid place-items-center size-8 rounded-ctl text-mut hover:text-fg hover:bg-line transition-colors cursor-pointer"
              title="Đóng (Esc)"
              aria-label="Đóng"
            >
              <X size={18} weight="bold" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 min-h-0 overflow-y-auto slim-scroll p-4 sm:p-6 bg-ink/30">
          {children}
        </div>
      </div>
    </div>
  );
}

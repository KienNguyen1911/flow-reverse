import { useState } from "react";
import { X } from "@phosphor-icons/react";
import type { ToastInfo } from "./types";

export function useToast() {
  const [toast, setToast] = useState<ToastInfo | null>(null);

  const showToast = (message: string, type: "ok" | "info" | "err" = "ok") => {
    const id = Date.now();
    setToast({ id, message, type });
    setTimeout(() => {
      setToast((cur) => (cur?.id === id ? null : cur));
    }, 3200);
  };

  const dismissToast = () => setToast(null);

  return { toast, showToast, dismissToast };
}

export function ToastBanner({ toast, onDismiss }: { toast: ToastInfo | null; onDismiss: () => void }) {
  if (!toast) return null;
  return (
    <div className="fixed top-5 right-5 z-50 flex items-center gap-2.5 rounded-ctl border border-line2 bg-panel px-4 py-3 shadow-2xl backdrop-blur-md animate-fade-in text-[12.5px]">
      <span
        className={`size-2 rounded-full ${
          toast.type === "ok" ? "bg-ok" : toast.type === "err" ? "bg-err" : "bg-acc"
        }`}
      />
      <span className="font-medium text-fg">{toast.message}</span>
      <button
        onClick={() => onDismiss()}
        className="ml-2 text-mut hover:text-fg cursor-pointer"
      >
        <X size={14} />
      </button>
    </div>
  );
}

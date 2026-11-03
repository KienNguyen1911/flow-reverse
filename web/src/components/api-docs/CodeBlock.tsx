import { useState } from "react";
import { Check, Copy } from "@phosphor-icons/react";

/** Monospace block with a copy button, used for every sample in the catalogue. */
export function CodeBlock({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => undefined);
  };

  return (
    <div className="overflow-hidden rounded-ctl border border-line2 bg-ink">
      <div className="flex items-center justify-between border-b border-line2 bg-panel px-3 py-1.5">
        <span className="font-mono text-[10.5px] font-semibold uppercase tracking-wider text-mut">
          {label}
        </span>
        <button
          type="button"
          onClick={copy}
          className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold transition-colors ${
            copied ? "text-ok" : "text-mut hover:text-fg"
          }`}
        >
          {copied ? <Check size={12} weight="bold" /> : <Copy size={12} />}
          {copied ? "Đã copy" : "Copy"}
        </button>
      </div>
      <pre className="slim-scroll overflow-x-auto px-3 py-2.5 font-mono text-[11.5px] leading-[1.6] text-dim">
        {code}
      </pre>
    </div>
  );
}

import { useState } from "react";
import { CaretDown, Code, Play } from "@phosphor-icons/react";
import { Spinner } from "./ui";
import { useLimits } from "../hooks";
import { BASE } from "./api-docs/base";
import { CodeBlock } from "./api-docs/CodeBlock";
import { GROUPS, TOTAL_EPS } from "./api-docs/catalog";
import type { Ep, Method } from "./api-docs/types";

const METHOD_CLS: Record<Method, string> = {
  GET: "border-ok/40 text-ok bg-ok/10",
  POST: "border-acc/40 text-acc bg-acc/10",
  PATCH: "border-warn/40 text-warn bg-warn/10",
  DELETE: "border-err/40 text-err bg-err/10",
};

function TryIt({ path }: { path: string }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [out, setOut] = useState("");

  const run = async () => {
    setState("loading");
    try {
      const r = await fetch(path);
      const text = await r.text();
      if (!r.ok) {
        setOut(`HTTP ${r.status}\n${text}`);
        setState("error");
        return;
      }
      let pretty = text;
      try {
        pretty = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        /* không phải JSON, giữ nguyên */
      }
      setOut(pretty.length > 4000 ? `${pretty.slice(0, 4000)}\n... (cắt bớt)` : pretty);
      setState("done");
    } catch (e) {
      setOut(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  };

  return (
    <div className="rounded-ctl border border-line2 bg-panel2 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void run()}
          disabled={state === "loading"}
          className="inline-flex h-7 items-center gap-1.5 rounded-[7px] border border-line2 px-2.5 text-[11.5px] font-semibold text-dim transition-colors hover:border-mut/70 hover:text-fg disabled:opacity-45"
        >
          {state === "loading" ? <Spinner size={12} /> : <Play size={12} />}
          Chạy thử
        </button>
        <span className="font-mono text-[11px] text-mut">GET {path}</span>
      </div>
      {state !== "idle" ? (
        <pre
          className={`slim-scroll max-h-64 overflow-auto rounded border border-line2 bg-ink px-3 py-2 font-mono text-[11.5px] leading-[1.6] ${
            state === "error" ? "text-err" : "text-ok"
          }`}
        >
          {out}
        </pre>
      ) : null}
    </div>
  );
}

function EndpointCard({ ep }: { ep: Ep }) {
  const [open, setOpen] = useState(false);
  const limits = useLimits();
  // Notes chứa placeholder để tài liệu không lệch với giới hạn backend thật.
  const fill = (s: string) =>
    s
      .replaceAll("{max_prompt}", String(limits.max_prompt_chars))
      .replaceAll("{max_batch}", String(limits.max_batch_items));

  return (
    <div className="overflow-hidden rounded-ctl border border-line2 bg-panel2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-line/40 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-acc/70"
      >
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] font-bold ${METHOD_CLS[ep.method]}`}
        >
          {ep.method}
        </span>
        <code className="min-w-0 break-all font-mono text-[12px] text-fg">{ep.path}</code>
        <span className="ml-auto hidden shrink-0 text-[11.5px] text-mut md:block">{ep.title}</span>
        <CaretDown
          size={14}
          className={`shrink-0 text-mut transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <div className="flex flex-col gap-2.5 border-t border-line2 px-3.5 py-3">
          <p className="text-[12.5px] leading-relaxed text-dim">{ep.desc}</p>

          {ep.notes?.length ? (
            <ul className="list-disc list-inside space-y-1.5 text-[12px] leading-relaxed text-mut marker:text-mut">
              {ep.notes.map((n, i) => (
                <li key={i}>{fill(n)}</li>
              ))}
            </ul>
          ) : null}

          {ep.body ? <CodeBlock label="Request body" code={ep.body} /> : null}
          <CodeBlock label="curl" code={ep.curl} />
          {ep.res ? <CodeBlock label="Response 200" code={ep.res} /> : null}
          {ep.tryIt ? <TryIt path={ep.path} /> : null}
        </div>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- //

export function ApiDocsPanel() {
  const [tab, setTab] = useState("start");
  const group = GROUPS.find((g) => g.key === tab) ?? GROUPS[0];

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="grid size-8 place-items-center rounded-ctl bg-acc/15 text-acc">
          <Code size={18} weight="bold" />
        </div>
        <div>
          <h2 className="text-[15.5px] font-bold text-fg">Tài liệu API Client</h2>
          <p className="text-[11.5px] text-mut">
            Gọi thẳng Flow Bench từ script, bot hoặc client riêng qua HTTP JSON
          </p>
        </div>
      </div>

      {/* Meta strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-ctl border border-line2 bg-panel2 px-3.5 py-2.5 text-[12px] text-mut">
        <span className="inline-flex items-center gap-2">
          Base URL
          <code className="font-mono font-semibold text-acc">{BASE}</code>
        </span>
        <span>{TOTAL_EPS} endpoint</span>
        <span>JSON, không cần auth</span>
        <span>Nguồn: src/WebUI/app.py</span>
      </div>

      {/* Inner tabs */}
      <div className="slim-scroll flex gap-1 overflow-x-auto rounded-ctl border border-line2 bg-panel2 p-1">
        {GROUPS.map((g) => (
          <button
            key={g.key}
            type="button"
            onClick={() => setTab(g.key)}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-[7px] px-3 py-1.5 text-[12px] font-semibold transition-colors ${
              tab === g.key ? "bg-acc/15 text-acc" : "text-dim hover:bg-line/50 hover:text-fg"
            }`}
          >
            {g.icon}
            <span>{g.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex flex-col gap-3">
        {group.extra}
        {group.endpoints.map((ep) => (
          <EndpointCard key={`${ep.method} ${ep.path}`} ep={ep} />
        ))}
      </div>
    </div>
  );
}

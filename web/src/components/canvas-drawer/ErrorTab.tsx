import { useMemo, useState } from "react";
import { ArrowsCounterClockwise, Copy, Warning } from "@phosphor-icons/react";
import type { Job } from "../../types";
import { diagnoseError } from "./errorDiagnosis";
import type { CanvasDrawerNode } from "./types";

interface Props {
  node: CanvasDrawerNode;
  job: Job | null;
  maxPromptChars: number;
  onRunNode: (id: string, dry: boolean) => void;
}

/** Error tab: diagnosis of the failure reason with fix hints and retry / dry-run actions. */
export function ErrorTab({ node, job, maxPromptChars, onRunNode }: Props) {
  const [copiedError, setCopiedError] = useState(false);

  const diagnosis = useMemo(() => {
    return diagnoseError(
      node?.reason || job?.error || (job?.result?.reason as string),
      maxPromptChars,
    );
  }, [node?.reason, job?.error, job?.result, maxPromptChars]);

  const copyErrorText = () => {
    if (!node) return;
    const txt = `[${diagnosis.code}] ${diagnosis.title}\n\nLý do: ${node.reason || "Không rõ"}\n\nGiải thích: ${diagnosis.explanation}\n\nGợi ý khắc phục:\n${diagnosis.fixHint}`;
    navigator.clipboard.writeText(txt);
    setCopiedError(true);
    setTimeout(() => setCopiedError(false), 2000);
  };

  return (
    <div className="flex flex-col gap-3.5">
      {/* Error code & badge */}
      <div className="rounded-panel border border-err/35 bg-err/5 p-4 flex flex-col gap-2.5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid place-items-center size-6 rounded-full bg-err/20 text-err">
              <Warning size={14} weight="fill" />
            </span>
            <span className="font-bold text-[13px] text-err">{diagnosis.title}</span>
          </div>
          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-err/15 text-err border border-err/25">
            {diagnosis.code}
          </span>
        </div>

        {/* Raw reason text */}
        <div className="rounded-ctl bg-ink/70 border border-err/20 p-2.5 font-mono text-[11px] leading-relaxed text-err break-all select-text">
          {node.reason || job?.error || "Không có thông tin chi tiết lỗi."}
        </div>

        <div className="flex justify-end">
          <button
            onClick={copyErrorText}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-ctl border border-err/30 bg-err/10 hover:bg-err/20 text-err text-[11px] font-semibold cursor-pointer transition-colors"
          >
            <Copy size={12} />
            <span>{copiedError ? "Đã sao chép!" : "Sao chép thông báo lỗi"}</span>
          </button>
        </div>
      </div>

      {/* Detailed Explanation */}
      <div className="rounded-panel border border-line2 bg-panel2 p-3.5 flex flex-col gap-1.5">
        <span className="text-[11px] font-bold text-fg uppercase tracking-wider">Nguyên nhân chi tiết</span>
        <p className="text-[12px] text-dim leading-relaxed">{diagnosis.explanation}</p>
      </div>

      {/* Actionable Fix Hint */}
      <div className="rounded-panel border border-acc/35 bg-acc/5 p-3.5 flex flex-col gap-2">
        <div className="flex items-center gap-1.5 text-acc font-bold text-[12px]">
          <span>💡 Hướng dẫn khắc phục</span>
        </div>
        <div className="text-[12px] text-dim leading-relaxed whitespace-pre-line font-normal">
          {diagnosis.fixHint}
        </div>
      </div>

      {/* Retry Button inside error view */}
      <div className="pt-2 flex items-center gap-2">
        <button
          onClick={() => onRunNode(node.id, false)}
          className="flex-1 h-9 rounded-ctl bg-acc hover:bg-acc2 text-accink font-bold text-[12px] inline-flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
        >
          <ArrowsCounterClockwise size={14} weight="bold" />
          <span>Thử chạy lại ngay</span>
        </button>
        <button
          onClick={() => onRunNode(node.id, true)}
          className="h-9 px-3.5 rounded-ctl border border-line2 bg-panel2 hover:border-line hover:text-fg text-dim font-semibold text-[12px] cursor-pointer transition-colors"
        >
          Dry-run
        </button>
      </div>
    </div>
  );
}

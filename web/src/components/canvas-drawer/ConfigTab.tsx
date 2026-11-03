import { useEffect, useRef } from "react";
import { ImageSquare, Timer } from "@phosphor-icons/react";
import { PromptEditor } from "../prompt/PromptBits";
import type { NodeMediaOptions } from "../../types";
import { AiPrompterPanel } from "./AiPrompterPanel";
import { ImageParams, VideoParams } from "./ComposerParams";
import { ItemOptions } from "./ItemOptions";
import type { CanvasDrawerNode, DrawerSection } from "./types";
import { UpstreamSources } from "./UpstreamSources";
import type { AiPrompter } from "./useAiPrompter";

interface Props {
  node: CanvasDrawerNode;
  allNodes: CanvasDrawerNode[];
  opts: NodeMediaOptions | null;
  maxPromptChars: number;
  initialSection: DrawerSection;
  ai: AiPrompter;
  onShowPreview: () => void;
  onUpdatePrompt?: (id: string, prompt: string) => void;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** Config tab: AI prompter, composer params, product-item options, upstream sources and the prompt editor. */
export function ConfigTab({
  node,
  allNodes,
  opts,
  maxPromptChars,
  initialSection,
  ai,
  onShowPreview,
  onUpdatePrompt,
  onUpdateNode,
}: Props) {
  const promptAnchorRef = useRef<HTMLDivElement>(null);
  const sourcesAnchorRef = useRef<HTMLDivElement>(null);

  /** Bật "Tác nhân" ⇒ Flow ẩn hết cấu hình; node chỉ gửi prompt. */
  const agentLocks = !!opts?.agent?.locks_config;
  const agentOn = !!node.agentMode;

  // Scroll thẳng tới vùng được yêu cầu (Prompt / Nguồn kết nối) ngay sau khi tab render.
  useEffect(() => {
    const anchor =
      initialSection === "prompt" ? promptAnchorRef.current
      : initialSection === "sources" ? sourcesAnchorRef.current
      : null;
    if (!anchor) return;
    const t = window.setTimeout(() => anchor.scrollIntoView({ block: "start", behavior: "smooth" }), 80);
    return () => window.clearTimeout(t);
  }, [node.id]);

  return (
    <div className="flex flex-col gap-3">
      {(node.type === "image" || node.type === "video") && (
        <AiPrompterPanel node={node} ai={ai} onUpdateNode={onUpdateNode} />
      )}

      {/* Agent ("Tác nhân") — bằng chứng: bật lên thì Flow rỗng hoá
          button.settings-trigger-button (0×0), không còn chip cấu hình. */}
      {agentLocks && (node.type === "image" || node.type === "video") && (
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={agentOn}
            onChange={(e) => onUpdateNode?.(node.id, { agentMode: e.target.checked })}
            className="mt-0.5 h-3.5 w-3.5 accent-[var(--color-acc)] cursor-pointer"
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold text-dim">
              Tác nhân (Agent){" "}
              <span className="font-normal text-mut">— Flow tự quyết cấu hình</span>
            </span>
            <span className="text-[10px] text-mut leading-snug">
              {opts?.agent?.note ??
                "Bật 'Tác nhân' thì Flow ẩn toàn bộ model/tỷ lệ/độ phân giải/thời lượng/số lượng."}
            </span>
          </span>
        </label>
      )}

      {agentOn && (node.type === "image" || node.type === "video") && (
        <div className="rounded-ctl border border-warn/40 bg-warn/10 px-2.5 py-2 text-[10.5px] text-warn leading-snug">
          Cấu hình do tác nhân quyết định — node chỉ gửi prompt. Tắt “Tác nhân” để chọn
          model / tỷ lệ / độ phân giải / thời lượng / số lượng như composer.
        </div>
      )}

      {node.type === "image" && !agentOn && <ImageParams node={node} opts={opts} onUpdateNode={onUpdateNode} />}

      {node.type === "image" && <ItemOptions node={node} onUpdateNode={onUpdateNode} />}

      {node.type === "video" && !agentOn && <VideoParams node={node} opts={opts} onUpdateNode={onUpdateNode} />}

      {node.type === "last_frame" && (
        <label className="rounded-ctl border border-line2 bg-panel2 p-2.5 flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={node.removeWatermark ?? true}
            onChange={(e) => onUpdateNode?.(node.id, { removeWatermark: e.target.checked })}
            className="h-3.5 w-3.5 accent-[var(--color-acc)] cursor-pointer"
          />
          <span className="text-[11px] font-semibold text-dim">Tự động xóa watermark Flow</span>
        </label>
      )}

      <UpstreamSources node={node} allNodes={allNodes} anchorRef={sourcesAnchorRef} onUpdateNode={onUpdateNode} />

      {/* Prompt đặt SAU nhóm cấu hình: phần cấu hình (tỷ lệ, seed, ảnh sản phẩm,
          nguồn kết nối) là thứ cần chỉnh trước, còn prompt dài chiếm trọn phần
          còn lại của drawer nên không bị đẩy xuống dưới cùng. */}
      <div ref={promptAnchorRef} className="flex flex-col gap-1.5 scroll-mt-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold text-dim">Prompt</span>
            <span className="text-[9.5px] text-mut">
              {node.type === "video" ? "· chuyển động 8s" : "· mô tả ảnh"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {node.elapsedS != null && (
              <span
                className="inline-flex items-center gap-1 h-6 px-2 rounded-full border border-line2 bg-panel2 text-[10.5px] font-mono text-dim"
                title="Thời gian thực thi của lần chạy gần nhất"
              >
                <Timer size={11} className="text-mut" />
                {node.elapsedS.toFixed(1)}s
              </span>
            )}
            <button
              type="button"
              onClick={onShowPreview}
              disabled={!node.fileUrl && !node.videoUrl}
              className="inline-flex items-center gap-1 h-6 px-2 rounded-ctl border border-line2 bg-panel2 text-[10.5px] font-semibold text-dim hover:text-fg hover:border-line2/80 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
              title="Xem kết quả ảnh / video của node"
            >
              <ImageSquare size={11} />
              <span>Kết quả</span>
            </button>
          </div>
        </div>
        <PromptEditor
          value={node.prompt}
          onChange={(v) => onUpdatePrompt?.(node.id, v)}
          placeholder={
            node.type === "video"
              ? "Prompt chuyển động cho video 8s…"
              : "Prompt mô tả ảnh cần tạo…"
          }
          minHeight={220}
          maxChars={maxPromptChars}
        />
      </div>
    </div>
  );
}

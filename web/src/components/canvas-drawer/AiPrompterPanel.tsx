import { Sparkle } from "@phosphor-icons/react";
import type { AiPrompter } from "./useAiPrompter";
import type { CanvasDrawerNode } from "./types";
import { Spinner } from "../ui";

interface Props {
  node: CanvasDrawerNode;
  ai: AiPrompter;
  onUpdateNode?: (id: string, patch: Partial<CanvasDrawerNode>) => void;
}

/** "AI Prompter Director": pick skill / clip / style hint and regenerate the node prompt. */
export function AiPrompterPanel({ node, ai, onUpdateNode }: Props) {
  const {
    aiGenerating,
    customHint,
    setCustomHint,
    selectedSkill,
    setSelectedSkill,
    selectedClip,
    setSelectedClip,
    scriptClips,
    skillsList,
    handleDrawerGeneratePrompt,
  } = ai;

  return (
    <div className="rounded-ctl border border-acc/35 bg-acc/5 p-3 flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[11.5px] font-bold text-fg flex items-center gap-1.5">
          <Sparkle size={13} weight="fill" className="text-acc" />
          <span>AI Prompter Director</span>
        </span>
        <button
          type="button"
          disabled={aiGenerating}
          onClick={handleDrawerGeneratePrompt}
          className="inline-flex items-center gap-1 px-2.5 h-6 rounded-ctl bg-acc text-accink text-[10.5px] font-bold hover:bg-acc2 transition-colors cursor-pointer disabled:opacity-40"
        >
          {aiGenerating ? <Spinner size={10} /> : <Sparkle size={10} weight="fill" />}
          <span>{aiGenerating ? "Đang sinh…" : "Tạo lại Prompt"}</span>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {skillsList.length > 0 && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-mut font-semibold">Chọn Skill quy chuẩn:</label>
            <select
              value={selectedSkill}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedSkill(val);
                onUpdateNode?.(node.id, { agentSkillId: val });
              }}
              className="h-7 rounded-ctl border border-line2 bg-panel px-2 text-[11px] text-fg outline-none focus:border-acc"
            >
              <option value="">Tự động chọn theo loại node (V1 Push / V2 Showcase)</option>
              {skillsList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {node.type === "video" && scriptClips.length > 0 && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-mut font-semibold">
              Clip trong kịch bản:
            </label>
            <select
              value={selectedClip}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedClip(val);
                onUpdateNode?.(node.id, { clipId: val || null });
              }}
              className="h-7 rounded-ctl border border-line2 bg-panel px-2 text-[11px] text-fg outline-none focus:border-acc"
              title="Clip quyết định vai (hook/showcase), nhịp beats và shots mà agent đọc được"
            >
              <option value="">(Chưa chọn — agent không thấy nhịp)</option>
              {scriptClips.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} · {c.role} · {c.duration_s}s
                  {c.has_beats ? " · có nhịp" : ""}
                </option>
              ))}
            </select>
            {!selectedClip && (
              <p className="text-[10px] text-warn leading-snug">
                Chưa chọn clip ⇒ prompt bỏ qua nhịp 0–2s / 2–5s / 5–8s và mục tiêu riêng
                của clip.
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-mut font-semibold">Ghi chú phong cách bổ sung (tùy chọn):</label>
          <input
            type="text"
            value={customHint}
            onChange={(e) => {
              const val = e.target.value;
              setCustomHint(val);
              onUpdateNode?.(node.id, { agentCustomHint: val });
            }}
            placeholder="Ví dụ: Áo len cổ lọ màu be, phong cách tối giản studio..."
            className="h-7 rounded-ctl border border-line2 bg-panel px-2 text-[11px] text-fg outline-none focus:border-acc"
          />
        </div>
      </div>
    </div>
  );
}

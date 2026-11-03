import { Sparkle } from "@phosphor-icons/react";
import { Spinner } from "../../ui";

/** "Prompt …" label + AI-skill picker + "AI Prompt" button shown above a node's prompt card. */
export function PromptAgentRow({
  label,
  skills,
  skillId,
  onSkillChange,
  skillTitle,
  autoOptionLabel,
  onGenerate,
  generating,
  disabled,
  generateTitle,
}: {
  label: string;
  skills: { id: string; name: string }[];
  skillId: string | null | undefined;
  onSkillChange: (skillId: string | null) => void;
  skillTitle: string;
  autoOptionLabel: string;
  onGenerate?: () => void;
  generating: boolean;
  disabled: boolean;
  generateTitle: string;
}) {
  return (
    <div className="flex items-center justify-between mt-0.5 gap-1.5 min-w-0">
      <span className="text-[10px] font-semibold text-mut shrink-0">{label}</span>
      <div className="flex items-center gap-1 min-w-0 flex-1 justify-end">
        {skills && skills.length > 0 && (
          <select
            value={skillId ?? ""}
            onChange={(e) => onSkillChange(e.target.value || null)}
            className="h-5 min-w-0 flex-1 max-w-[135px] rounded border border-line2 bg-panel px-1 text-[9px] text-fg focus:border-acc outline-none cursor-pointer"
            title={skillTitle}
          >
            <option value="">{autoOptionLabel}</option>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
        {onGenerate && (
          <button
            type="button"
            disabled={disabled}
            onClick={onGenerate}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] border border-acc/40 bg-acc/10 text-[9.5px] font-bold text-acc hover:bg-acc/20 hover:border-acc/70 transition-all cursor-pointer disabled:opacity-40 shrink-0 whitespace-nowrap"
            title={generateTitle}
          >
            {generating ? (
              <>
                <Spinner size={9} />
                <span>Đang tạo…</span>
              </>
            ) : (
              <>
                <Sparkle size={10} weight="fill" className="text-acc" />
                <span>AI Prompt</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

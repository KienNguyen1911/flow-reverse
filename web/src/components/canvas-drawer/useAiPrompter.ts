import { useEffect, useState } from "react";
import { api } from "../../api";
import { useScriptClips } from "../../hooks";
import type { CanvasDrawerNode } from "./types";

//: Kịch bản mặc định — cùng đường dẫn với `CanvasPanel` và `DeliveryModal`.
const SCRIPT_PATH = "configs/lookbook_script.json";

/** State + handler of the "AI Prompter Director" panel (skill / clip / hint selection and prompt generation). */
export function useAiPrompter({
  node,
  allNodes,
  onUpdatePrompt,
}: {
  node: CanvasDrawerNode | null;
  allNodes: CanvasDrawerNode[];
  onUpdatePrompt?: (id: string, prompt: string) => void;
}) {
  const [aiGenerating, setAiGenerating] = useState(false);
  const [customHint, setCustomHint] = useState("");
  const [selectedSkill, setSelectedSkill] = useState("");
  const [selectedClip, setSelectedClip] = useState("");
  const scriptClips = useScriptClips();
  const [skillsList, setSkillsList] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    if (node) {
      setSelectedSkill(node.agentSkillId ?? "");
      setCustomHint(node.agentCustomHint ?? "");
      setSelectedClip(node.clipId ?? "");
    }
  }, [node?.id, node?.agentSkillId, node?.agentCustomHint, node?.clipId]);

  useEffect(() => {
    api.agentSkills().then((res) => {
      if (res.skills) {
        setSkillsList(res.skills.map((s) => ({ id: s.id, name: s.name })));
      }
    }).catch(() => {});
  }, []);

  const handleDrawerGeneratePrompt = async () => {
    if (!node) return;
    setAiGenerating(true);
    try {
      const sids = node.type === "image" && node.sourceImageIds && node.sourceImageIds.length > 0
        ? node.sourceImageIds
        : node.sourceImageId ? [node.sourceImageId] : [];
      const urls: string[] = [];
      for (const sid of sids) {
        const p = allNodes.find((x) => x.id === sid);
        if (p?.fileUrl) urls.push(p.fileUrl);
        else if (p?.videoUrl) urls.push(p.videoUrl);
      }
      const isCont = node.type === "video" && !!node.sourceImageId &&
        (() => {
          const p = allNodes.find((x) => x.id === node.sourceImageId);
          return p?.type === "last_frame" || p?.type === "video";
        })();

      const targetSkill = selectedSkill || node.agentSkillId || undefined;
      const targetHint = customHint.trim() || node.agentCustomHint || undefined;

      const res = await api.generateNodePrompt({
        node_id: node.id,
        node_type: node.type as "image" | "video",
        upstream_media_urls: urls,
        skill_id: targetSkill,
        custom_hint: targetHint,
        is_video_continuation: isCont,
        // Thiếu `clip_id` thì agent không đọc được role/shots/chain_from/beats và mọi node video
        // sinh ra cùng một prompt.
        clip_id: node.type === "video" ? (selectedClip || node.clipId || undefined) : undefined,
        clip_role:
          node.type === "video"
            ? scriptClips.find((c) => c.id === (selectedClip || node.clipId))?.role
            : undefined,
        script_path: node.type === "video" ? SCRIPT_PATH : undefined,
        // Thiếu 2 trường này thì node bảng phối bị coi là node ảnh lookbook: agent dùng
        // skill vẽ người mẫu thay vì dựng coordinate sheet.
        is_item: !!node.isItem,
        item_name: node.isItem ? node.itemName || undefined : undefined,
      });

      if (res.ok && res.prompt) {
        onUpdatePrompt?.(node.id, res.prompt);
      }
    } catch (err: any) {
      alert(`Lỗi sinh prompt: ${err?.message || err}`);
    } finally {
      setAiGenerating(false);
    }
  };

  return {
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
  };
}

export type AiPrompter = ReturnType<typeof useAiPrompter>;

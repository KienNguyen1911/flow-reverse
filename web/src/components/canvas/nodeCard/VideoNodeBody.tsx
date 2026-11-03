import { useMemo } from "react";
import { NodeDropdownPill, PromptPreviewCard } from "../../canvasNodeBits";
import type { CanvasNode } from "../types";
import { PromptAgentRow } from "./PromptAgentRow";
import { sourceLabel, type NodeSources } from "./nodeSources";
import type { NodeOptionLists } from "./optionLists";
import type { CardDropdown, NodeBodyActions } from "./types";

/** Video-generation node body: frame source, prompt and option pills. */
export function VideoNodeBody({
  n,
  options,
  sources,
  nodeSkills,
  dropdown,
  actions,
  wfBusy,
  aiGeneratingId,
  onGenerateAiPrompt,
}: {
  n: CanvasNode;
  options: NodeOptionLists;
  sources: NodeSources;
  nodeSkills: { id: string; name: string }[];
  dropdown: CardDropdown;
  actions: NodeBodyActions;
  wfBusy: boolean;
  aiGeneratingId?: string | null;
  onGenerateAiPrompt?: (id: string) => void;
}) {
  const {
    videoRatios,
    resolutions,
    videoModels,
    videoCounts,
    videoDefaultModel,
    videoSubModeLabels,
  } = options;
  const { sourceOptions, upstream, textToVideo, sourceBlocked } = sources;

  const activeVideoModel = useMemo(() => {
    if (!videoModels.length) return null;
    return videoModels.find((m) => m.id === (n.videoModel ?? "")) ?? videoModels[0] ?? null;
  }, [videoModels, n.videoModel]);

  const videoSubModeItems = useMemo(() => {
    return [
      {
        value: "frames",
        label: videoSubModeLabels["frames"] ?? "Khung hình",
        hint: "Ảnh → Video",
      },
      {
        value: "ingredients",
        label: videoSubModeLabels["ingredients"] ?? "Thành phần",
        hint: "Prompt → Video",
      },
    ];
  }, [videoSubModeLabels]);

  const videoModelItems = useMemo(() => {
    return videoModels.map((m) => ({
      value: m.id,
      label: m.label,
      hint: m.id === videoDefaultModel ? "Mặc định" : undefined,
    }));
  }, [videoModels, videoDefaultModel]);

  const videoRatioItems = useMemo(() => {
    const base = activeVideoModel?.aspect_ratios ?? (videoRatios.length ? videoRatios : ["16:9", "9:16"]);
    const list = base.includes(n.videoRatio) ? base : [n.videoRatio, ...base];
    const hints: Record<string, string> = {
      "9:16": "Dọc (TikTok, Shorts)",
      "16:9": "Ngang (YouTube)",
      "1:1": "Vuông (Instagram)",
    };
    return list.map((r) => ({
      value: r,
      label: r,
      hint: hints[r],
    }));
  }, [activeVideoModel, videoRatios, n.videoRatio]);

  const resolutionItems = useMemo(() => {
    const base = activeVideoModel?.resolutions ?? (resolutions.length ? resolutions : ["720p", "1080p"]);
    const list = base.includes(n.resolution) ? base : [n.resolution, ...base];
    return list.map((r) => ({
      value: r,
      label: r,
      hint: r === "1080p" ? "Full HD" : r === "720p" ? "HD" : undefined,
    }));
  }, [activeVideoModel, resolutions, n.resolution]);

  const videoDurationItems = useMemo(() => {
    const list = activeVideoModel?.durations_s ?? [4, 6, 8, 10];
    return list.map((d) => ({
      value: d,
      label: `${d} giây`,
      hint: `${d}s`,
    }));
  }, [activeVideoModel]);

  const videoCountItems = useMemo(() => {
    const list = videoCounts.length ? videoCounts : [1, 2, 3, 4];
    return list.map((c) => ({
      value: c,
      label: `${c} video`,
      hint: `x${c}`,
    }));
  }, [videoCounts]);

  const frameSourceItems = useMemo(() => {
    const items = [
      {
        value: "",
        label: "Tự tạo ảnh khung",
        hint: "Auto",
      },
    ];
    for (const src of sourceOptions) {
      items.push({
        value: src.id,
        label: sourceLabel(src),
        hint: src.type === "last_frame" ? "Nối tiếp" : "Ảnh",
      });
    }
    return items;
  }, [sourceOptions]);

  return (
    <>
      {/* "Thành phần" = text→video (`YhhmEf`): không có ô chọn ảnh khung vì Flow
          không gửi frame nào trong payload của sub-mode này. */}
      {textToVideo ? (
        <p className="text-[10px] text-mut leading-snug">
          Thành phần (text→video): chỉ cần prompt, không dùng ảnh khung.
        </p>
      ) : (
        <>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] font-semibold text-mut">Nguồn ảnh khung hình</span>
            <select
              value={n.sourceImageId ?? ""}
              onChange={(e) => actions.onSourceChange(e.target.value)}
              className="h-7 rounded-ctl border border-line2 bg-panel2 px-1.5 text-[11px] text-fg focus:border-acc outline-none"
            >
              <option value="">Tự tạo ảnh khung (auto)</option>
              {sourceOptions.map((i) => (
                <option key={i.id} value={i.id}>
                  {sourceLabel(i)}
                </option>
              ))}
            </select>
          </label>
          {sourceBlocked && (
            <p className="text-[10px] text-warn leading-snug">
              Node nguồn chưa chạy xong — video sẽ chờ/bỏ qua khi chạy workflow.
            </p>
          )}
        </>
      )}

      <PromptAgentRow
        label="Prompt video"
        skills={nodeSkills}
        skillId={n.agentSkillId}
        onSkillChange={(agentSkillId) => actions.onFieldChange({ agentSkillId })}
        skillTitle="Chọn skill quy chuẩn AI tạo prompt cho video"
        autoOptionLabel="(Tự động: V1 Push / V2 Showcase)"
        onGenerate={onGenerateAiPrompt ? () => onGenerateAiPrompt(n.id) : undefined}
        generating={aiGeneratingId === n.id}
        disabled={aiGeneratingId === n.id || wfBusy}
        generateTitle="Local AI Agent sẽ nhìn vào ảnh First Frame hoặc Last Frame nguồn để viết prompt chuyển động nối tiếp chuẩn xác"
      />

      <PromptPreviewCard
        prompt={n.prompt}
        placeholder="Prompt chuyển động cho video 8s… bấm để sửa"
        onExpand={() => actions.onOpenPromptEditor(n.id)}
      />

      {/* Summary pills: Bấm mở dropdown chọn option trực tiếp thay vì mở drawer */}
      <div className="flex items-center gap-1 flex-wrap">
        {n.agentMode ? (
          <NodeDropdownPill
            tone="warn"
            value="Tác nhân quyết định"
            title="Flow đang bật 'Tác nhân' — bấm để tắt hoặc mở Cấu hình"
            isOpen={dropdown.open === "agent"}
            onToggle={() => dropdown.toggle("agent")}
            onClose={dropdown.close}
            header="Tác nhân"
            items={[
              { value: "off", label: "Tắt Tác nhân", hint: "Tự chọn model & thông số" },
              { value: "drawer", label: "Mở Cấu hình", hint: "Xem trong Drawer" },
            ]}
            onSelect={(val) => {
              if (val === "off") actions.onFieldChange({ agentMode: false });
              else actions.onOpenDrawer(n.id, "config");
            }}
          />
        ) : (
          <>
            <NodeDropdownPill
              label="Sub"
              value={
                videoSubModeLabels[n.videoSubMode ?? "frames"] ??
                (n.videoSubMode === "ingredients" ? "Thành phần" : "Khung hình")
              }
              title="Sub-mode video — bấm để đổi"
              id="videoSubMode"
              isOpen={dropdown.open === "videoSubMode"}
              onToggle={() => dropdown.toggle("videoSubMode")}
              onClose={dropdown.close}
              header="Chế độ video"
              width="min-w-[180px]"
              items={videoSubModeItems}
              selectedValue={n.videoSubMode ?? "frames"}
              onSelect={(val) => actions.onFieldChange({ videoSubMode: String(val) })}
            />
            <NodeDropdownPill
              label="Model"
              value={
                videoModels.find((m) => m.id === (n.videoModel ?? ""))?.label ??
                videoModels.find((m) => m.id === (videoDefaultModel || ""))?.label ??
                videoModels[0]?.label ??
                n.videoModel ??
                "—"
              }
              title="Model video của composer Flow — bấm để đổi"
              id="videoModel"
              isOpen={dropdown.open === "videoModel"}
              onToggle={() => dropdown.toggle("videoModel")}
              onClose={dropdown.close}
              header="Chọn Model video"
              width="min-w-[190px]"
              items={videoModelItems}
              selectedValue={n.videoModel ?? videoDefaultModel ?? videoModels[0]?.id}
              onSelect={(nextId) => {
                const nextModel = videoModels.find((m) => m.id === nextId);
                const patch: Partial<CanvasNode> = { videoModel: String(nextId) };
                if (nextModel) {
                  if (!nextModel.has_resolution) {
                    patch.resolution = nextModel.resolutions[1] ?? nextModel.resolutions[0] ?? "720p";
                  } else if (!nextModel.resolutions.includes(n.resolution)) {
                    patch.resolution = nextModel.resolutions[0];
                  }
                  if (!nextModel.has_duration) {
                    patch.videoDurationS = nextModel.durations_s[0] ?? 8;
                  } else if (!nextModel.durations_s.includes(n.videoDurationS ?? 8)) {
                    patch.videoDurationS = nextModel.durations_s[0];
                  }
                  if (!nextModel.aspect_ratios.includes(n.videoRatio)) {
                    patch.videoRatio = nextModel.aspect_ratios[0];
                  }
                }
                actions.onFieldChange(patch);
              }}
            />
            <NodeDropdownPill
              value={n.videoRatio}
              title={`Tỷ lệ video: ${n.videoRatio} — bấm để đổi`}
              id="videoRatio"
              isOpen={dropdown.open === "videoRatio"}
              onToggle={() => dropdown.toggle("videoRatio")}
              onClose={dropdown.close}
              header="Tỷ lệ video"
              items={videoRatioItems}
              selectedValue={n.videoRatio}
              onSelect={(val) => actions.onFieldChange({ videoRatio: String(val) })}
            />
            <NodeDropdownPill
              value={n.resolution}
              title={
                activeVideoModel && !activeVideoModel.has_resolution
                  ? `Model ${activeVideoModel.label} cố định độ phân giải (${n.resolution})`
                  : `Độ phân giải: ${n.resolution} — bấm để đổi`
              }
              id="resolution"
              isOpen={dropdown.open === "resolution"}
              onToggle={() => {
                if (activeVideoModel && !activeVideoModel.has_resolution) return;
                dropdown.toggle("resolution");
              }}
              onClose={dropdown.close}
              header="Độ phân giải"
              items={resolutionItems}
              selectedValue={n.resolution}
              onSelect={(val) => actions.onFieldChange({ resolution: String(val) })}
            />
            <NodeDropdownPill
              value={`${n.videoDurationS ?? 8}s`}
              title={
                activeVideoModel && !activeVideoModel.has_duration
                  ? `Model ${activeVideoModel.label} cố định thời lượng (${n.videoDurationS ?? 8}s)`
                  : "Thời lượng mỗi video — bấm để đổi"
              }
              id="videoDuration"
              isOpen={dropdown.open === "videoDuration"}
              onToggle={() => {
                if (activeVideoModel && !activeVideoModel.has_duration) return;
                dropdown.toggle("videoDuration");
              }}
              onClose={dropdown.close}
              header="Thời lượng video"
              items={videoDurationItems}
              selectedValue={n.videoDurationS ?? 8}
              onSelect={(val) => actions.onFieldChange({ videoDurationS: Number(val) })}
            />
            <NodeDropdownPill
              value={`x${n.videoCount ?? 1}`}
              title="Số video mỗi lần chạy (x1..x4) — bấm để đổi"
              id="videoCount"
              isOpen={dropdown.open === "videoCount"}
              onToggle={() => dropdown.toggle("videoCount")}
              onClose={dropdown.close}
              header="Số lượng video"
              align="right"
              width="min-w-[120px]"
              items={videoCountItems}
              selectedValue={n.videoCount ?? 1}
              onSelect={(val) => actions.onFieldChange({ videoCount: Number(val) })}
            />
            <NodeDropdownPill
              label="Frame"
              value={
                (n.videoSubMode ?? "frames") === "ingredients"
                  ? "Không cần"
                  : upstream
                    ? (upstream.type === "last_frame" ? "Nối tiếp" : "Node Ảnh")
                    : "Auto"
              }
              title="Ảnh khung nguồn — bấm để chọn nguồn"
              id="frameSource"
              isOpen={dropdown.open === "frameSource"}
              onToggle={() => {
                if ((n.videoSubMode ?? "frames") === "ingredients") return;
                dropdown.toggle("frameSource");
              }}
              onClose={dropdown.close}
              header="Nguồn ảnh khung"
              width="min-w-[190px]"
              items={frameSourceItems}
              selectedValue={n.sourceImageId ?? ""}
              onSelect={(val) => actions.onSourceChange(String(val))}
            />
          </>
        )}
      </div>
    </>
  );
}

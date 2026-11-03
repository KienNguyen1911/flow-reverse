import type { AspectRatio, ReuseSource } from "./types";

export interface ReuseSettings {
  prompt1?: string;
  prompt2?: string;
  firstFramePath?: string | null;
  firstFrameUrl?: string | null;
  aspectRatio: string;
  runId: string;
}

/** Normalises the prompt / first-frame / aspect settings of a finished run manifest or a job. */
export function extractReuseSettings(run: ReuseSource): ReuseSettings {
  const params = ("params" in run ? run.params : undefined) as Record<string, string> | undefined;
  return {
    prompt1: "video_prompt_1" in run ? run.video_prompt_1 : params?.video_prompt_1,
    prompt2: "video_prompt_2" in run ? run.video_prompt_2 : params?.video_prompt_2,
    firstFramePath: "first_frame_path" in run ? run.first_frame_path : params?.first_frame_path,
    firstFrameUrl: "first_frame_url" in run ? run.first_frame_url : undefined,
    aspectRatio: ("aspect_ratio" in run ? run.aspect_ratio : params?.aspect_ratio) || "9:16",
    runId: "run_id" in run ? run.run_id : "",
  };
}

export function isAspectRatio(v: string): v is AspectRatio {
  return v === "9:16" || v === "16:9";
}

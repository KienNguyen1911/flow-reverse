import { useMemo } from "react";
import type { Job, TryOnRunManifest } from "../../types";
import { STEPS_CHAIN, STEPS_SINGLE } from "./constants";
import type { StepView } from "./types";

/**
 * Derives everything the stage inspector needs from the inspected job / selected run:
 * linked manifest, current step, per-step statuses, failed step and the displayable result.
 */
export function useTryOnPipeline({
  inspectedJob,
  selectedResultRun,
  historyRuns,
  isSingleMode,
}: {
  inspectedJob: Job | null;
  selectedResultRun: TryOnRunManifest | null;
  historyRuns: TryOnRunManifest[];
  isSingleMode: boolean;
}) {
  const isJobSingle = useMemo(() => {
    if (!inspectedJob) return isSingleMode;
    const p = inspectedJob.params as Record<string, unknown> | undefined;
    if (p && typeof p.single_video === "boolean") return p.single_video;
    return isSingleMode;
  }, [inspectedJob, isSingleMode]);

  const activeSteps = isJobSingle ? STEPS_SINGLE : STEPS_CHAIN;

  // Resolve any run manifest associated with selectedResultRun or inspectedJob (even if failed)
  const linkedRunManifest: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun) return selectedResultRun;
    if (!inspectedJob) return null;

    const jobRes = inspectedJob.result as unknown as TryOnRunManifest | undefined;
    let detectedRunId = jobRes?.run_id || "";

    if (!detectedRunId && inspectedJob.events) {
      for (const ev of inspectedJob.events) {
        const m = ev.message.match(/\b(tryon_\d{8}_\d{6})\b/);
        if (m) {
          detectedRunId = m[1];
          break;
        }
      }
    }

    const fromHistory = detectedRunId
      ? historyRuns.find((r) => r.run_id === detectedRunId) || null
      : null;

    if (fromHistory && jobRes?.run_id) {
      return { ...fromHistory, ...jobRes, steps: jobRes.steps?.length ? jobRes.steps : fromHistory.steps };
    }
    if (fromHistory) return fromHistory;
    if (jobRes?.run_id) return jobRes;
    return null;
  }, [selectedResultRun, inspectedJob, historyRuns]);

  // Determine step reached from job event logs
  const reachedStepFromEvents = useMemo(() => {
    if (!inspectedJob) return 0;
    const events = inspectedJob.events || [];
    let step = 1;
    for (const ev of events) {
      const msg = ev.message.toLowerCase();
      if (isJobSingle) {
        if (msg.includes("xóa watermark") || msg.includes("hoàn tất")) {
          step = Math.max(step, 2);
        }
      } else {
        if (msg.includes("nối") || msg.includes("ghép") || msg.includes("bước 4/4") || msg.includes("bước 8")) {
          step = Math.max(step, 4);
        } else if (msg.includes("video 2") || msg.includes("bước 3/4") || msg.includes("bước 7")) {
          step = Math.max(step, 3);
        } else if (msg.includes("last frame") || msg.includes("trích xuất") || msg.includes("bước 2/4") || msg.includes("bước 6")) {
          step = Math.max(step, 2);
        } else if (msg.includes("video 1") || msg.includes("bước 1/4") || msg.includes("bước 5")) {
          step = Math.max(step, 1);
        }
      }
    }
    return step;
  }, [inspectedJob, isJobSingle]);

  // Determine current pipeline step
  const currentStep = useMemo(() => {
    if (linkedRunManifest?.status === "succeeded" || inspectedJob?.state === "succeeded") {
      return isJobSingle ? 2 : 4;
    }
    if (linkedRunManifest?.failed_step) {
      return linkedRunManifest.failed_step;
    }
    if (linkedRunManifest?.current_step) {
      return linkedRunManifest.current_step;
    }
    if (!inspectedJob) return 0;
    return reachedStepFromEvents || 1;
  }, [inspectedJob, linkedRunManifest, isJobSingle, reachedStepFromEvents]);

  // Compute detailed status for each step in activeSteps
  const stepStatuses = useMemo<StepView[]>(() => {
    const isFailed =
      (selectedResultRun && selectedResultRun.status !== "succeeded") ||
      (!selectedResultRun && (inspectedJob?.state === "failed" || inspectedJob?.state === "rejected"));
    const isSucceeded =
      selectedResultRun?.status === "succeeded" ||
      (!selectedResultRun && inspectedJob?.state === "succeeded");
    const isRunning = !selectedResultRun && inspectedJob?.state === "running";

    const failStepId =
      linkedRunManifest?.failed_step ||
      (isFailed ? Math.max(1, reachedStepFromEvents || 1) : null);

    return activeSteps.map((s) => {
      const manifestStep = linkedRunManifest?.steps?.find((ms) => ms.id === s.id);
      if (manifestStep && (isFailed || isSucceeded || selectedResultRun)) {
        return {
          ...s,
          status: manifestStep.status as "pending" | "running" | "succeeded" | "failed",
          error: manifestStep.error || null,
        };
      }
      if (isSucceeded) {
        return { ...s, status: "succeeded" as const, error: null };
      }
      if (isRunning) {
        if (s.id < currentStep) return { ...s, status: "succeeded" as const, error: null };
        if (s.id === currentStep) return { ...s, status: "running" as const, error: null };
        return { ...s, status: "pending" as const, error: null };
      }
      if (isFailed && failStepId !== null) {
        if (s.id < failStepId) return { ...s, status: "succeeded" as const, error: null };
        if (s.id === failStepId) {
          return {
            ...s,
            status: "failed" as const,
            error: inspectedJob?.error || linkedRunManifest?.error || null,
          };
        }
        return { ...s, status: "pending" as const, error: null };
      }
      return { ...s, status: "pending" as const, error: null };
    });
  }, [activeSteps, linkedRunManifest, selectedResultRun, inspectedJob, currentStep, reachedStepFromEvents]);

  const failedStepInfo = useMemo(() => {
    return stepStatuses.find((s) => s.status === "failed") || null;
  }, [stepStatuses]);

  // Active result to display in full completed viewer (only when succeeded, or when user explicitly inspects a completed run)
  const activeResult: TryOnRunManifest | null = useMemo(() => {
    if (selectedResultRun && selectedResultRun.status === "succeeded") return selectedResultRun;
    if (
      !selectedResultRun &&
      inspectedJob?.state === "succeeded" &&
      linkedRunManifest?.run_id
    ) {
      return linkedRunManifest;
    }
    return null;
  }, [selectedResultRun, inspectedJob?.state, linkedRunManifest]);

  return {
    isJobSingle,
    activeSteps,
    linkedRunManifest,
    currentStep,
    stepStatuses,
    failedStepInfo,
    activeResult,
  };
}

export type TryOnPipeline = ReturnType<typeof useTryOnPipeline>;

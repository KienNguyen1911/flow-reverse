import { useCallback, useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { api } from "../../api";
import { isTerminal, waitForJob } from "../../jobWatcher";
import { ACTIVE } from "./constants";
import { getNodeSourceIds, isVideoContinuation, resolveSource, type SourceResult } from "./graph";
import { buildPromptRequest, jobPatch } from "./jobs";
import { buildRunUnits, unitMembers } from "./runPlan";
import type { CanvasGroup, CanvasNode, ConfirmTarget, Graph, ShowToast } from "./types";

/**
 * Execution of nodes against the backend: single-node runs, the whole-workflow
 * run (per group, isolated failure), AI-prompt generation, and live job polling.
 */
export function useNodeRunner(params: {
  nodes: CanvasNode[];
  nodesRef: MutableRefObject<CanvasNode[]>;
  groupsRef: MutableRefObject<CanvasGroup[]>;
  selectedRef: MutableRefObject<string[]>;
  setGraph: Dispatch<SetStateAction<Graph>>;
  patchNode: (id: string, patch: Partial<CanvasNode>) => void;
  showToast: ShowToast;
  setConfirmTarget: Dispatch<SetStateAction<ConfirmTarget | null>>;
  clipRoleOf: (clipId?: string | null) => string | undefined;
  workspaceProjectId?: string | null;
  onAssetGenerated?: () => void;
}) {
  const {
    nodes,
    nodesRef,
    groupsRef,
    selectedRef,
    setGraph,
    patchNode,
    showToast,
    setConfirmTarget,
    clipRoleOf,
  } = params;

  const [wfBusy, setWfBusy] = useState(false);
  const [aiGeneratingId, setAiGeneratingId] = useState<string | null>(null);
  const [jitPromptEnabled, setJitPromptEnabled] = useState<boolean>(true);

  //: One abort handle per in-flight node run, so a run can be cancelled (or dropped on unmount)
  //: instead of a click handler staying pinned until the job finishes.
  const runSignals = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const signals = runSignals.current;
    return () => {
      for (const c of signals.values()) c.abort();
      signals.clear();
    };
  }, []);

  // -- poll jobs for nodes with an active job --------------------------------- //
  const activeJobKey = nodes
    .filter((n) => n.jobId && ACTIVE.has(n.status))
    .map((n) => n.jobId)
    .join("|");

  useEffect(() => {
    if (!activeJobKey) return;
    let stop = false;
    const tick = async () => {
      try {
        const { jobs } = await api.jobs(100);
        if (stop) return;
        const map = new Map(jobs.map((j) => [j.id, j]));
        setGraph((g) => {
          let changed = false;
          const next = g.nodes.map((n) => {
            if (!n.jobId || !ACTIVE.has(n.status)) return n;
            const j = map.get(n.jobId);
            if (!j || j.state === n.status) return n;
            changed = true;
            return { ...n, ...jobPatch(n, j) };
          });
          return changed ? { ...g, nodes: next } : g;
        });
      } catch {
        /* transient */
      }
    };
    tick();
    const t = window.setInterval(tick, 1200);
    return () => {
      stop = true;
      window.clearInterval(t);
    };
  }, [activeJobKey]);

  // -- run one node (submit + await terminal) --------------------------------- //
  const runNodeNow = useCallback(
    async (nodeId: string, dry: boolean): Promise<{ ok: boolean; fileUrl?: string | null }> => {
      const n = nodesRef.current.find((x) => x.id === nodeId);
      if (!n) return { ok: false };

      // Nút "Chạy node" trên thẻ đã bị `canRun` chặn prompt rỗng, nhưng workflow theo
      // nhóm và nút "Chạy lại" trong drawer gọi thẳng vào đây. Không chặn ở tầng này thì
      // request rỗng bay tới backend và quay về 422 "prompt: String should have at least
      // 1 character" — một lỗi trông như lỗi mạng, không chỉ ra được node nào.
      if (!dry && n.type !== "ref" && n.type !== "last_frame" && !n.prompt.trim()) {
        const reason = "Prompt đang rỗng — nhập prompt hoặc bấm AI Prompt trước khi chạy.";
        patchNode(nodeId, { status: "failed", reason });
        showToast(reason, "err", nodeId);
        return { ok: false };
      }

      patchNode(nodeId, { status: "queued", reason: null });
      const controller = new AbortController();
      runSignals.current.get(nodeId)?.abort();
      runSignals.current.set(nodeId, controller);
      try {
        if (n.type === "ref") return { ok: !!n.fileUrl, fileUrl: n.fileUrl };

        const srcRes: SourceResult = resolveSource(nodesRef.current, n, dry);
        if (!srcRes.ok) {
          patchNode(nodeId, { status: "failed", reason: srcRes.reason });
          showToast(`Lỗi node: ${srcRes.reason}`, "err", nodeId);
          return { ok: false };
        }

        let promise: Promise<{ job_id: string }>;
        if (n.type === "image") {
          promise = api.nodeImage({
            prompt: n.prompt.trim(),
            aspect_ratio: n.aspectRatio,
            seed: n.seed,
            model: n.imageModel ?? undefined,
            count: n.imageCount ?? 1,
            agent_mode: !!n.agentMode,
            reference_image_path: srcRes.url,
            reference_image_paths: srcRes.urls,
            project_id: undefined,
            workspace_project_id: params.workspaceProjectId ?? null,
            // Server chép ảnh vào `out/items/<project>/` ngay sau khi sinh xong — không
            // phải đợi tới lúc xuất bộ dựng phim mới copy tay.
            is_item: !!n.isItem,
            item_name: n.isItem ? n.itemName || n.label || n.id : undefined,
            dry_run: dry,
            confirm: !dry,
          });
        } else if (n.type === "video") {
          const subMode = n.videoSubMode ?? "frames";
          const needsFrame = subMode === "frames";
          const isIngredients = subMode === "ingredients";
          const framePath = needsFrame ? srcRes.url : undefined;
          const autoImage = needsFrame && !framePath;
          const refPaths = isIngredients && srcRes.urls && srcRes.urls.length > 0 ? srcRes.urls : undefined;
          promise = api.nodeVideo({
            prompt: n.prompt.trim(),
            aspect_ratio: n.videoRatio,
            sub_mode: subMode,
            model: n.videoModel ?? undefined,
            count: n.videoCount ?? 1,
            agent_mode: !!n.agentMode,
            frame_path: framePath,
            reference_image_path: isIngredients ? (refPaths?.[0] ?? undefined) : undefined,
            reference_image_paths: isIngredients ? refPaths : undefined,
            auto_image: autoImage,
            image_prompt: autoImage && n.autoImagePrompt.trim() ? n.autoImagePrompt.trim() : undefined,
            image_aspect_ratio: autoImage ? n.imageAspectRatio : undefined,
            seed: n.seed,
            resolution: n.resolution,
            duration_s: n.videoDurationS ?? 8,
            project_id: undefined,
            workspace_project_id: params.workspaceProjectId ?? null,
            dry_run: dry,
            confirm: !dry,
          });
        } else {
          // last_frame
          if (dry) {
            patchNode(nodeId, { status: "succeeded", reason: null, elapsedS: 0 });
            return { ok: true, fileUrl: null };
          }
          if (!srcRes.url) {
            patchNode(nodeId, { status: "failed", reason: "Chưa có file video nguồn để trích xuất frame." });
            return { ok: false };
          }
          promise = api.nodeLastFrame({
            video_path: srcRes.url,
            remove_watermark: n.removeWatermark ?? true,
            workspace_project_id: params.workspaceProjectId ?? null,
          });
        }

        const { job_id } = await promise;
        patchNode(nodeId, { jobId: job_id, status: "queued" });

        // await terminal state
        const final = await waitForJob(job_id, {
          intervalMs: 1200,
          signal: controller.signal,
          onState: (j) => {
            if (!isTerminal(j.state)) {
              patchNode(nodeId, { status: j.state === "running" ? "running" : "queued" });
            }
          },
        });
        const patch = jobPatch(n, final);
        patchNode(nodeId, patch);
        Object.assign(n, patch);
        if (nodesRef.current) {
          nodesRef.current = nodesRef.current.map((x) => (x.id === nodeId ? { ...x, ...patch } : x));
        }
        const ok = final.state === "succeeded";
        if (ok && !dry) {
          params.onAssetGenerated?.();
        } else if (!ok && !dry) {
          const typeName =
            n.type === "image" ? "ảnh" : n.type === "video" ? "video" : "frame cuối";
          showToast(
            `Node ${typeName} thất bại: ${patch.reason ?? final.state}`,
            "err",
            nodeId,
          );
        }
        return { ok, fileUrl: patch.fileUrl };
      } catch (e) {
        // A run aborted by the caller (unmount, retry, explicit cancel) is not a failure: leave the
        // node to whoever aborted it rather than painting an error the user did not cause.
        if (e instanceof DOMException && e.name === "AbortError") return { ok: false };
        const errText =
          e instanceof Error ? e.message : typeof e === "object" ? JSON.stringify(e) : String(e);
        patchNode(nodeId, {
          status: "failed",
          reason: errText,
        });
        showToast(errText || "Lỗi khi gửi job", "err", nodeId);
        return { ok: false };
      } finally {
        if (runSignals.current.get(nodeId) === controller) runSignals.current.delete(nodeId);
      }
    },
    [patchNode, showToast],
  );

  // -- Local AI Prompt Agent generator ------------------------------------- //
  const handleGenerateAiPrompt = useCallback(
    async (nodeId: string) => {
      const current = nodesRef.current;
      const target = current.find((x) => x.id === nodeId);
      if (!target || (target.type !== "image" && target.type !== "video")) return;

      const sRes = resolveSource(current, target, false);
      const isCont = isVideoContinuation(current, target);

      setAiGeneratingId(nodeId);
      showToast("Local AI Agent đang phân tích ảnh nguồn để tạo prompt...", "info", nodeId);

      try {
        const res = await api.generateNodePrompt(
          buildPromptRequest(target, sRes.ok ? sRes.urls : [], isCont, clipRoleOf),
        );

        if (res.ok && res.prompt) {
          patchNode(nodeId, { prompt: res.prompt });
          showToast(`Đã tối ưu prompt bằng ${res.agent.toUpperCase()} (${res.elapsed_s}s)`, "ok", nodeId);
        } else {
          showToast("AI Agent không tạo được prompt.", "err", nodeId);
        }
      } catch (err: any) {
        showToast(`Lỗi AI Agent: ${err?.message || err}`, "err", nodeId);
      } finally {
        setAiGeneratingId(null);
      }
    },
    [patchNode, showToast],
  );

  // -- run whole workflow (per group, isolated failure) ------------------------- //
  // Each Visual Group is an independent execution unit. A node failure aborts
  // only the unit that owns it; the following units still run from scratch.
  const runWorkflow = useCallback(
    async (dry: boolean) => {
      if (wfBusy) return;
      setWfBusy(true);
      setConfirmTarget(null);
      try {
        const current = nodesRef.current;
        const units = buildRunUnits(current, groupsRef.current, selectedRef.current);

        if (units.length === 0) {
          showToast("Không có node nào để chạy.", "err");
          return;
        }

        const srcOk = new Map<string, boolean>();
        for (const n of current.filter((x) => x.type === "ref")) srcOk.set(n.id, !!n.fileUrl);

        const executable = units.reduce((acc, u) => acc + unitMembers(current, u).length, 0);
        if (executable === 0) {
          showToast("Không có node ảnh/video nào để chạy.", "err");
          return;
        }

        const aborted: string[] = [];

        for (const unit of units) {
          const members = unitMembers(current, unit);
          if (members.length === 0) continue;

          if (units.length > 1) {
            showToast(`▶ Bắt đầu ${unit.name} (${members.length} node)`, "info", members[0].id);
          }

          let unitFailed = false;
          for (const item of members) {
            const n = nodesRef.current.find((x) => x.id === item.id) || item;

            if (unitFailed) {
              patchNode(n.id, {
                status: "skipped",
                reason: `Đã hủy vì ${unit.name} gặp lỗi trước đó.`,
              });
              srcOk.set(n.id, false);
              continue;
            }

            const sids = getNodeSourceIds(n);
            if (sids.some((sid) => srcOk.get(sid) === false)) {
              patchNode(n.id, {
                status: "skipped",
                reason: "Node nguồn không thành công — bỏ qua node này.",
              });
              srcOk.set(n.id, false);
              continue;
            }

            // Dynamic JIT prompt generation before running
            if (!dry && jitPromptEnabled && (n.type === "image" || n.type === "video")) {
              const sRes = resolveSource(nodesRef.current, n, false);
              if (sRes.ok && sRes.urls.length > 0) {
                setAiGeneratingId(n.id);
                try {
                  showToast(`JIT Agent: Đang phân tích kết quả node trước để tối ưu prompt...`, "info", n.id);
                  const aiRes = await api.generateNodePrompt(
                    buildPromptRequest(
                      n,
                      sRes.ok ? sRes.urls : [],
                      isVideoContinuation(nodesRef.current, n),
                      clipRoleOf,
                    ),
                  );
                  if (aiRes.ok && aiRes.prompt) {
                    patchNode(n.id, { prompt: aiRes.prompt });
                    n.prompt = aiRes.prompt;
                    item.prompt = aiRes.prompt;
                  }
                } catch (e: any) {
                  console.warn("Lỗi sinh prompt JIT, tiếp tục với prompt sẵn có:", e);
                } finally {
                  setAiGeneratingId(null);
                }
              }
            }

            const r = await runNodeNow(n.id, dry);
            srcOk.set(n.id, r.ok);
            if (!r.ok && !dry) {
              unitFailed = true;
              aborted.push(unit.name);
              showToast(
                `Dừng ${unit.name}: node lỗi. Chuyển sang nhóm tiếp theo.`,
                "err",
                n.id,
              );
            }
          }
        }

        if (aborted.length > 0) {
          showToast(
            dry
              ? "Dry-run hoàn tất."
              : `Workflow kết thúc — ${aborted.length} nhóm bị dừng: ${aborted.join(", ")}.`,
            "err",
          );
        } else {
          showToast(dry ? "Dry-run workflow hoàn tất." : "Workflow hoàn tất!", "ok");
        }
      } finally {
        setWfBusy(false);
      }
    },
    [wfBusy, jitPromptEnabled, runNodeNow, patchNode, showToast],
  );

  return {
    wfBusy,
    aiGeneratingId,
    jitPromptEnabled,
    setJitPromptEnabled,
    runNodeNow,
    handleGenerateAiPrompt,
    runWorkflow,
  };
}

import { useCallback, useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { api } from "../../api";
import type { WorkspaceCanvasState } from "../../types";
import { canvasStateToGraph, graphToCanvasState } from "./serialization";
import type { CanvasGroup, CanvasNode, Graph, View, WorkspaceSaveState } from "./types";

/**
 * Workspace persistence: hydrates the graph/viewport from the active project's
 * saved canvas, then autosaves (debounced) on every graph/viewport change.
 * Returns the serializer and an immediate `flushSave` for the imperative handle.
 */
export function useWorkspacePersistence(params: {
  workspaceProjectId: string | null;
  workspaceCanvasState?: WorkspaceCanvasState | null;
  onWorkspaceSaveState?: (state: WorkspaceSaveState) => void;
  onWorkspaceSaved?: (projectId: string) => void;
  graph: Graph;
  view: View;
  setGraph: Dispatch<SetStateAction<Graph>>;
  setView: Dispatch<SetStateAction<View>>;
  nodesRef: MutableRefObject<CanvasNode[]>;
  groupsRef: MutableRefObject<CanvasGroup[]>;
  viewRef: MutableRefObject<View>;
  /** Reset transient UI state (selection, marquee, …) once a new canvas is in place. */
  resetTransientState: () => void;
}) {
  const {
    workspaceProjectId,
    workspaceCanvasState,
    graph,
    view,
    setGraph,
    setView,
    nodesRef,
    groupsRef,
    viewRef,
  } = params;

  const projectIdRef = useRef<string | null>(workspaceProjectId);
  projectIdRef.current = workspaceProjectId;
  const onSaveStateRef = useRef(params.onWorkspaceSaveState);
  onSaveStateRef.current = params.onWorkspaceSaveState;
  const onSavedRef = useRef(params.onWorkspaceSaved);
  onSavedRef.current = params.onWorkspaceSaved;
  const resetTransientRef = useRef(params.resetTransientState);
  resetTransientRef.current = params.resetTransientState;

  const saveStateRef = useRef<WorkspaceSaveState>("idle");
  const saveTimerRef = useRef<number | null>(null);
  const dirtyRef = useRef(false);
  const lastSavedJsonRef = useRef<string>("");
  const hydratedProjectRef = useRef<string | null>(null);

  const emitSaveState = useCallback((state: WorkspaceSaveState) => {
    if (saveStateRef.current === state) return;
    saveStateRef.current = state;
    onSaveStateRef.current?.(state);
  }, []);

  const buildState = useCallback(
    () => graphToCanvasState(nodesRef.current, groupsRef.current, viewRef.current),
    [],
  );

  const persistNow = useCallback(
    async (pid: string, state: WorkspaceCanvasState) => {
      const json = JSON.stringify(state);
      emitSaveState("saving");
      try {
        await api.saveWorkspaceCanvas(pid, state);
        lastSavedJsonRef.current = json;
        dirtyRef.current = false;
        emitSaveState("saved");
        onSavedRef.current?.(pid);
      } catch {
        emitSaveState("error");
      }
    },
    [emitSaveState],
  );

  const flushSave = useCallback(async () => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const pid = projectIdRef.current;
    if (!pid) return;
    if (hydratedProjectRef.current !== pid) return;
    const state = buildState();
    if (JSON.stringify(state) === lastSavedJsonRef.current) return;
    await persistNow(pid, state);
  }, [buildState, persistNow]);

  // Hydrate during render so the committed graph always belongs to the active
  // project; an effect would leave one frame where a stale graph could be
  // autosaved into the newly selected project.
  const [hydratedPid, setHydratedPid] = useState<string | null>(null);
  if (
    workspaceProjectId &&
    workspaceCanvasState &&
    hydratedPid !== workspaceProjectId
  ) {
    const { graph: nextGraph, view: nextView } = canvasStateToGraph(workspaceCanvasState);
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    setGraph(nextGraph);
    setView(nextView);
    setHydratedPid(workspaceProjectId);
    hydratedProjectRef.current = workspaceProjectId;
    lastSavedJsonRef.current = JSON.stringify(
      graphToCanvasState(nextGraph.nodes, nextGraph.groups, nextView),
    );
    dirtyRef.current = false;
  }

  // Reset transient UI state once the new canvas is in place.
  useEffect(() => {
    if (!hydratedPid) return;
    resetTransientRef.current();
    saveStateRef.current = "saved";
    onSaveStateRef.current?.("saved");
  }, [hydratedPid]);

  // Debounced autosave on any graph or viewport change.
  useEffect(() => {
    const pid = workspaceProjectId;
    if (!pid || !workspaceCanvasState) return;
    if (hydratedProjectRef.current !== pid) return;
    const state = buildState();
    const json = JSON.stringify(state);
    if (json === lastSavedJsonRef.current) {
      // Hydration or a no-op re-render: nothing to persist.
      dirtyRef.current = false;
      emitSaveState("saved");
      return;
    }
    dirtyRef.current = true;
    emitSaveState("saving");
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      const pidNow = projectIdRef.current;
      if (!pidNow || hydratedProjectRef.current !== pidNow) return;
      const latest = buildState();
      if (JSON.stringify(latest) === lastSavedJsonRef.current) {
        dirtyRef.current = false;
        emitSaveState("saved");
        return;
      }
      void persistNow(pidNow, latest);
    }, 800);
  }, [graph, view, workspaceProjectId, buildState, emitSaveState, persistNow]);

  // Last-chance save when the tab is hidden/closed or the panel unmounts.
  useEffect(() => {
    const flushBeacon = () => {
      const pid = projectIdRef.current;
      if (!pid || !dirtyRef.current) return;
      const state = buildState();
      const json = JSON.stringify(state);
      if (json === lastSavedJsonRef.current) return;
      lastSavedJsonRef.current = json;
      dirtyRef.current = false;
      api.saveWorkspaceCanvasBeacon(pid, state);
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushBeacon();
    };
    window.addEventListener("pagehide", flushBeacon);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", flushBeacon);
      document.removeEventListener("visibilitychange", onVisibility);
      flushBeacon();
    };
  }, [buildState]);

  return { buildState, flushSave };
}

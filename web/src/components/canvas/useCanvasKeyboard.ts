import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { ContextMenuState, LinkingState } from "./types";

/**
 * Canvas keyboard shortcuts.
 * - Escape cancels, in order: context menu → linking → drawer → selection.
 * - Ctrl/Cmd+G groups the current selection (ignored while typing in a field).
 */
export function useCanvasKeyboard(params: {
  contextMenu: ContextMenuState | null;
  setContextMenu: Dispatch<SetStateAction<ContextMenuState | null>>;
  linking: LinkingState | null;
  setLinking: Dispatch<SetStateAction<LinkingState | null>>;
  drawerNodeId: string | null;
  setDrawerNodeId: Dispatch<SetStateAction<string | null>>;
  selectedRef: MutableRefObject<string[]>;
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  onGroupSelection: () => void;
}) {
  const {
    contextMenu,
    setContextMenu,
    linking,
    setLinking,
    drawerNodeId,
    setDrawerNodeId,
    selectedRef,
    setSelectedIds,
    onGroupSelection,
  } = params;

  // -- escape cancels linking, context menu, drawer, or clears the selection --- //
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (contextMenu) setContextMenu(null);
      else if (linking) setLinking(null);
      else if (drawerNodeId) setDrawerNodeId(null);
      else if (selectedRef.current.length > 0) setSelectedIds([]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [linking, drawerNodeId, contextMenu]);

  // -- Ctrl/Cmd+G groups the current selection ------------------------------- //
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "g") {
        e.preventDefault();
        onGroupSelection();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onGroupSelection]);
}

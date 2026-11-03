import { useCallback, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { GROUP_COLORS } from "./constants";
import { nextId } from "./graph";
import type { CanvasGroup, Graph, ShowToast } from "./types";

/** Node selection and visual-group editing (create / rename / dissolve / membership). */
export function useSelectionGroups(params: {
  setGraph: Dispatch<SetStateAction<Graph>>;
  groupsRef: MutableRefObject<CanvasGroup[]>;
  selectedRef: MutableRefObject<string[]>;
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  showToast: ShowToast;
}) {
  const { setGraph, groupsRef, selectedRef, setSelectedIds, showToast } = params;

  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);

  // -- selection -------------------------------------------------------------- //
  const toggleSelect = useCallback((id: string, additive: boolean) => {
    setSelectedIds((cur) => {
      if (!additive) return cur.length === 1 && cur[0] === id ? [] : [id];
      return cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    });
  }, []);

  const selectGroup = useCallback((groupId: string) => {
    const g = groupsRef.current.find((x) => x.id === groupId);
    if (!g) return;
    setSelectedIds(g.nodeIds);
  }, []);

  // -- group actions ---------------------------------------------------------- //
  const createGroupFromSelection = useCallback(() => {
    const sel = selectedRef.current;
    if (sel.length === 0) {
      showToast("Chọn node trước (Shift + click hoặc quét chuột) để tạo nhóm.", "err");
      return;
    }
    const existing = groupsRef.current;
    const taken = new Set(existing.flatMap((g) => g.nodeIds));
    const ids = sel.filter((id) => !taken.has(id));
    if (ids.length === 0) {
      showToast("Các node đã chọn đều thuộc nhóm khác — giải tán nhóm cũ trước.", "err");
      return;
    }
    const group: CanvasGroup = {
      id: nextId("group"),
      name: `Nhóm ${existing.length + 1}`,
      nodeIds: ids,
      color: GROUP_COLORS[existing.length % GROUP_COLORS.length],
    };
    setGraph((g) => ({ ...g, groups: [...g.groups, group] }));
    setEditingGroupId(group.id);
    showToast(`Đã tạo "${group.name}" gồm ${ids.length} node.`, "ok");
  }, [showToast]);

  const renameGroup = useCallback((groupId: string, name: string) => {
    setGraph((g) => ({
      ...g,
      groups: g.groups.map((gr) => (gr.id === groupId ? { ...gr, name } : gr)),
    }));
  }, []);

  const dissolveGroup = useCallback(
    (groupId: string) => {
      const g = groupsRef.current.find((x) => x.id === groupId);
      setGraph((cur) => ({ ...cur, groups: cur.groups.filter((gr) => gr.id !== groupId) }));
      if (g) showToast(`Đã giải tán "${g.name}".`, "info");
    },
    [showToast],
  );

  const addSelectionToGroup = useCallback(
    (groupId: string) => {
      const sel = new Set(selectedRef.current);
      if (sel.size === 0) {
        showToast("Chưa chọn node nào để thêm vào nhóm.", "err");
        return;
      }
      const target = groupsRef.current.find((gr) => gr.id === groupId);
      if (!target) return;
      const added = Array.from(sel).filter((id) => !target.nodeIds.includes(id)).length;
      setGraph((g) => ({
        ...g,
        groups: g.groups
          .map((gr) => {
            if (gr.id !== groupId) {
              // Nodes can only belong to one group.
              return { ...gr, nodeIds: gr.nodeIds.filter((id) => !sel.has(id)) };
            }
            return { ...gr, nodeIds: Array.from(new Set([...gr.nodeIds, ...sel])) };
          })
          .filter((gr) => gr.nodeIds.length > 0),
      }));
      showToast(added > 0 ? `Đã thêm ${added} node vào nhóm.` : "Các node này đã ở trong nhóm.", "ok");
    },
    [showToast],
  );

  const removeFromGroup = useCallback(
    (groupId: string) => {
      const sel = new Set(selectedRef.current);
      if (sel.size === 0) return;
      setGraph((g) => ({
        ...g,
        groups: g.groups
          .map((gr) =>
            gr.id === groupId
              ? { ...gr, nodeIds: gr.nodeIds.filter((id) => !sel.has(id)) }
              : gr,
          )
          .filter((gr) => gr.nodeIds.length > 0),
      }));
      showToast("Đã bỏ node khỏi nhóm.", "info");
    },
    [showToast],
  );

  return {
    editingGroupId,
    setEditingGroupId,
    toggleSelect,
    selectGroup,
    createGroupFromSelection,
    renameGroup,
    dissolveGroup,
    addSelectionToGroup,
    removeFromGroup,
  };
}

import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { TEMPLATES_KEY } from "./constants";
import { buildBuiltinTemplate } from "./templates";
import type { CanvasGroup, CanvasNode, CustomTemplate, Graph, ShowToast, View } from "./types";

/**
 * Built-in + user-saved (localStorage) canvas templates: save, delete, resolve
 * to a graph, and load one onto the canvas.
 */
export function useTemplates(params: {
  graph: Graph;
  setGraph: Dispatch<SetStateAction<Graph>>;
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  setView: Dispatch<SetStateAction<View>>;
  showToast: ShowToast;
  onTemplatesChange?: (templates: { id: string; name: string }[]) => void;
}) {
  const { graph, setGraph, setSelectedIds, setView, showToast, onTemplatesChange } = params;

  const [customTemplates, setCustomTemplates] = useState<CustomTemplate[]>(() => {
    try {
      const raw = localStorage.getItem(TEMPLATES_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    onTemplatesChange?.(customTemplates.map((t) => ({ id: t.id, name: t.name })));
  }, [customTemplates, onTemplatesChange]);

  const saveCurrentTemplate = useCallback(
    (name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      try {
        const newTpl: CustomTemplate = {
          id: `custom_tpl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          name: trimmed,
          createdAt: Date.now(),
          nodes: graph.nodes,
          groups: graph.groups || [],
        };
        const updated = [newTpl, ...customTemplates.filter((x) => x.name.toLowerCase() !== trimmed.toLowerCase())];
        setCustomTemplates(updated);
        localStorage.setItem(TEMPLATES_KEY, JSON.stringify(updated));
        showToast(`Đã lưu Mẫu Template: "${trimmed}"`, "ok");
      } catch (err: any) {
        showToast(`Lỗi lưu template: ${err?.message || err}`, "err");
      }
    },
    [graph.nodes, graph.groups, customTemplates, showToast],
  );

  const deleteCustomTemplate = useCallback(
    (id: string) => {
      const updated = customTemplates.filter((x) => x.id !== id);
      setCustomTemplates(updated);
      localStorage.setItem(TEMPLATES_KEY, JSON.stringify(updated));
      showToast("Đã xóa Mẫu Template.", "info");
    },
    [customTemplates, showToast],
  );

  const resolveTemplateGraph = useCallback(
    (nameOrId: string): { nodes: CanvasNode[]; groups: CanvasGroup[]; label: string } | null => {
      const builtin = buildBuiltinTemplate(nameOrId);
      if (builtin) return builtin;

      const custom = customTemplates.find((x) => x.id === nameOrId || x.name === nameOrId);
      if (custom && Array.isArray(custom.nodes)) {
        return { nodes: custom.nodes, groups: custom.groups || [], label: custom.name };
      }
      return null;
    },
    [customTemplates],
  );

  const loadTemplate = useCallback(
    (nameOrId: string) => {
      const tpl = resolveTemplateGraph(nameOrId);
      if (!tpl) {
        showToast("Không tìm thấy mẫu template.", "err");
        return;
      }
      setGraph({ nodes: tpl.nodes, groups: tpl.groups });
      setSelectedIds([]);
      setView({ x: 30, y: 20, z: 0.72 });
      showToast(`Đã khởi tạo Mẫu: ${tpl.label}`, "ok");
    },
    [resolveTemplateGraph, showToast],
  );

  return {
    customTemplates,
    saveCurrentTemplate,
    deleteCustomTemplate,
    resolveTemplateGraph,
    loadTemplate,
  };
}

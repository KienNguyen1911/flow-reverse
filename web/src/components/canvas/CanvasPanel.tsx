import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import type { LibraryItem, NodeMediaOptions } from "../../types";
import { useLimits, useScriptClips } from "../../hooks";
import { CanvasDrawer } from "../CanvasDrawer";
import { PromptEditorModal } from "../prompt/PromptBits";
import { DeliveryModal } from "../DeliveryModal";
import { MediaPreviewModal, type PreviewMediaItem } from "../MediaPreviewModal";
import { CanvasContextMenu } from "./CanvasContextMenu";
import {
  AssetDrawerToggle,
  CanvasToast,
  DeliveryButton,
  EmptyCanvasHint,
  FileDropOverlay,
  LinkingBanner,
  NavigationHint,
  RefHoverTooltip,
  SelectionToolbar,
  ZoomControls,
} from "./CanvasOverlays";
import { EdgesLayer, GroupFrames, MarqueeRect } from "./GraphLayers";
import { RunConfirmModal } from "./RunConfirmModal";
import { ACTIVE } from "./constants";
import { getNodeSourceIds } from "./graph";
import { buildRunUnits } from "./runPlan";
import { graphToCanvasState, loadGraph } from "./serialization";
import { CanvasNodeCard } from "./nodeCard/CanvasNodeCard";
import { deriveNodeOptionLists } from "./nodeCard/optionLists";
import type {
  CanvasNode,
  CanvasPanelHandle,
  CanvasPanelProps,
  ConfirmTarget,
  ContextMenuState,
  DrawerSection,
  FocusLink,
  Graph,
  HoverRefInfo,
  LinkingState,
  ToastInfo,
} from "./types";
import { useCanvasKeyboard } from "./useCanvasKeyboard";
import { useCanvasViewport } from "./useCanvasViewport";
import { useNodeActions } from "./useNodeActions";
import { useNodeRunner } from "./useNodeRunner";
import { useSelectionGroups } from "./useSelectionGroups";
import { useTemplates } from "./useTemplates";
import { useWorkspacePersistence } from "./useWorkspacePersistence";

export const CanvasPanel = forwardRef<CanvasPanelHandle, CanvasPanelProps>(function CanvasPanel(
  props,
  ref,
) {
  const [graph, setGraph] = useState<Graph>(loadGraph);
  const limits = useLimits();
  const scriptClips = useScriptClips();
  //: `clip_id` → `role`, lấy từ `/api/node/options`. Backend cần cả hai để nói rõ vai clip khi
  //: script không đọc được, nên không để nó tự suy ngược từ id.
  const clipRoleOf = useCallback(
    (clipId?: string | null) =>
      (clipId && scriptClips.find((c) => c.id === clipId)?.role) || undefined,
    [scriptClips],
  );
  const [opts, setOpts] = useState<NodeMediaOptions | null>(null);
  const [linking, setLinking] = useState<LinkingState | null>(null);
  const [previewMedia, setPreviewMedia] = useState<PreviewMediaItem | null>(null);
  const [deliveryOpen, setDeliveryOpen] = useState(false);

  const [toast, setToast] = useState<ToastInfo | null>(null);
  const [canvasDrag, setCanvasDrag] = useState(false);
  const [drawerNodeId, setDrawerNodeId] = useState<string | null>(null);
  const [drawerSection, setDrawerSection] = useState<DrawerSection>("config");
  const [promptEditorNodeId, setPromptEditorNodeId] = useState<string | null>(null);
  /** Hover trên chip `#n` → tô sáng đúng edge + node nguồn. */
  const [focusLink, setFocusLink] = useState<FocusLink | null>(null);
  /** Tooltip xem nhanh ảnh tham chiếu — toạ độ viewport (portal, không bị strip cắt). */
  const [hoverRef, setHoverRef] = useState<HoverRefInfo | null>(null);
  const [skillsList, setSkillsList] = useState<{ id: string; name: string }[]>([]);
  // Thư viện ảnh sản phẩm của project (`out/items/<project_id>/`). Không phụ thuộc script.
  const [itemLibrary, setItemLibrary] = useState<LibraryItem[]>([]);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [nodeHeights, setNodeHeights] = useState<Record<string, number>>({});
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  const nodes = graph.nodes;
  const groups = graph.groups;
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const groupsRef = useRef(groups);
  groupsRef.current = groups;
  const selectedRef = useRef(selectedIds);
  selectedRef.current = selectedIds;

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const heightRef = useRef<Record<string, number>>({});
  heightRef.current = nodeHeights;

  const measureNode = useCallback((id: string, h: number) => {
    if (h <= 0) return;
    setNodeHeights((cur) => (Math.abs((cur[id] ?? 0) - h) < 1 ? cur : { ...cur, [id]: h }));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastInfo["type"] = "ok", nodeId?: string) => {
      const id = Date.now();
      setToast({ id, message, type, nodeId });
      window.setTimeout(() => setToast((cur) => (cur?.id === id ? null : cur)), 4200);
    },
    [],
  );

  const viewport = useCanvasViewport({
    nodesRef,
    heightRef,
    selectedRef,
    setGraph,
    setSelectedIds,
    setLinking,
    contextMenu,
    setContextMenu,
  });
  const { view, setView, viewRef, viewportRef, marquee } = viewport;

  const { buildState, flushSave } = useWorkspacePersistence({
    workspaceProjectId: props.workspaceProjectId ?? null,
    workspaceCanvasState: props.workspaceCanvasState,
    onWorkspaceSaveState: props.onWorkspaceSaveState,
    onWorkspaceSaved: props.onWorkspaceSaved,
    graph,
    view,
    setGraph,
    setView,
    nodesRef,
    groupsRef,
    viewRef,
    resetTransientState: () => {
      setSelectedIds([]);
      setLinking(null);
      setContextMenu(null);
      viewport.setMarquee(null);
      setNodeHeights({});
    },
  });

  // -- node options & agent skills ------------------------------------------ //
  useEffect(() => {
    api
      .nodeOptions()
      .then(setOpts)
      .catch(() => {
        /* fallback */
      });

    api
      .agentSkills()
      .then((res) => {
        if (res.skills) {
          setSkillsList(res.skills.map((s) => ({ id: s.id, name: s.name })));
        }
      })
      .catch(() => {});
  }, []);

  // Thư viện món đồ đổi theo project ⇒ nạp lại khi đổi project.
  useEffect(() => {
    api
      .itemLibrary(props.workspaceProjectId ?? null)
      .then((res) => setItemLibrary(res.items))
      .catch(() => {
        /* chưa có thư viện cũng chạy bình thường — chỉ mất danh sách gợi ý */
      });
  }, [props.workspaceProjectId]);

  const patchNode = useCallback((id: string, patch: Partial<CanvasNode>) => {
    if (nodesRef.current) {
      nodesRef.current = nodesRef.current.map((n) => (n.id === id ? { ...n, ...patch } : n));
    }
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    }));
  }, []);

  const { wfBusy, aiGeneratingId, jitPromptEnabled, setJitPromptEnabled, runNodeNow, handleGenerateAiPrompt, runWorkflow } =
    useNodeRunner({
      nodes,
      nodesRef,
      groupsRef,
      selectedRef,
      setGraph,
      patchNode,
      showToast,
      setConfirmTarget,
      clipRoleOf,
      workspaceProjectId: props.workspaceProjectId,
      onAssetGenerated: props.onAssetGenerated,
    });

  // Run id của từng clip trong script, suy từ node canvas theo template chuẩn.
  // Nối bằng id node (không đoán theo thứ tự) để đổi template vẫn ra đúng cặp.
  const deliveryRuns = useMemo<Record<string, string | null | undefined>>(() => {
    const byNodeId = new Map(nodes.map((n) => [n.id, n]));
    return {
      clip1: byNodeId.get("lb_video_1")?.runId ?? null,
      clip2: byNodeId.get("lb_video_2")?.runId ?? null,
    };
  }, [nodes]);

  // Ảnh sản phẩm đã sinh: node ảnh nào tick `isItem` và đã có run thì đưa vào bộ dựng phim.
  // Không cần khớp `items[]` của script — tên file lấy từ `itemName` người dùng đặt.
  const deliveryItems = useMemo(() => {
    return nodes
      .filter((n) => n.type === "image" && n.isItem && !!n.runId)
      .map((n) => ({
        name: n.itemName || n.label || n.id,
        run_id: n.runId as string,
      }));
  }, [nodes]);

  const {
    editingGroupId,
    setEditingGroupId,
    toggleSelect,
    selectGroup,
    createGroupFromSelection,
    renameGroup,
    dissolveGroup,
    addSelectionToGroup,
    removeFromGroup,
  } = useSelectionGroups({ setGraph, groupsRef, selectedRef, setSelectedIds, showToast });

  const openDrawer = useCallback((id: string, section: DrawerSection = "config") => {
    setDrawerSection(section);
    setDrawerNodeId(id);
  }, []);

  useCanvasKeyboard({
    contextMenu,
    setContextMenu,
    linking,
    setLinking,
    drawerNodeId,
    setDrawerNodeId,
    selectedRef,
    setSelectedIds,
    onGroupSelection: createGroupFromSelection,
  });

  const { addNodeAt, addNode, removeNode, uploadRef, addReferenceNode, dropFiles, handleDotClick } =
    useNodeActions({
      nodes,
      opts,
      setGraph,
      patchNode,
      showToast,
      viewRef,
      viewportRef,
      setContextMenu,
      setSelectedIds,
      linking,
      setLinking,
      drawerNodeId,
      setDrawerNodeId,
      setCanvasDrag,
      workspaceProjectId: props.workspaceProjectId,
      onAssetGenerated: props.onAssetGenerated,
    });

  // -- edges ------------------------------------------------------------------- //
  const edges = useMemo(() => {
    const list: { from: CanvasNode; to: CanvasNode }[] = [];
    for (const v of nodes) {
      if (v.type === "ref") continue;
      const sids = getNodeSourceIds(v);
      for (const sid of sids) {
        const src = nodes.find((n) => n.id === sid);
        if (src) list.push({ from: src, to: v });
      }
    }
    return list;
  }, [nodes]);

  const imageNodes = nodes.filter((n) => n.type === "image");
  const videoNodes = nodes.filter((n) => n.type === "video");
  const lastFrameNodes = nodes.filter((n) => n.type === "last_frame");
  const jobNodes = nodes.filter((n) => n.type !== "ref");
  const nRunning = jobNodes.filter((n) => ACTIVE.has(n.status)).length;
  const nDone = jobNodes.filter((n) => n.status === "succeeded").length;
  const nPending = jobNodes.filter(
    (n) => n.status === "idle" || n.status === "failed" || n.status === "rejected",
  ).length;

  const optionLists = deriveNodeOptionLists(opts);

  const drawerNode = nodes.find((n) => n.id === drawerNodeId) ?? null;
  const promptEditorNode = nodes.find((n) => n.id === promptEditorNodeId) ?? null;

  // Execution plan preview for the confirm modal + TopBar.
  const runUnits = useMemo(
    () => buildRunUnits(nodes, groups, selectedIds),
    [nodes, groups, selectedIds],
  );

  const {
    customTemplates,
    saveCurrentTemplate,
    deleteCustomTemplate,
    resolveTemplateGraph,
    loadTemplate,
  } = useTemplates({
    graph,
    setGraph,
    setSelectedIds,
    setView,
    showToast,
    onTemplatesChange: props.onTemplatesChange,
  });

  useImperativeHandle(
    ref,
    () => {
      const handle: CanvasPanelHandle = {
        addNode,
        addReferenceNode,
        loadTemplate,
        saveCurrentTemplate,
        deleteCustomTemplate,
        getCustomTemplates: () => customTemplates,
        runWorkflow,
        openConfirmWorkflow: () => setConfirmTarget({ mode: "workflow" }),
        getCanvasState: () => buildState(),
        getTemplateCanvasState: (name: string) => {
          const tpl = resolveTemplateGraph(name);
          if (!tpl) return null;
          return graphToCanvasState(tpl.nodes, tpl.groups, { x: 30, y: 20, z: 0.72 });
        },
        flushSave,
      };
      if (typeof window !== "undefined") (window as any).__canvas = handle;
      return handle;
    },
    [
      addNode,
      addReferenceNode,
      loadTemplate,
      saveCurrentTemplate,
      deleteCustomTemplate,
      customTemplates,
      runWorkflow,
      buildState,
      resolveTemplateGraph,
      flushSave,
    ],
  );

  const onStatsChange = props.onStatsChange;
  useEffect(() => {
    onStatsChange?.({
      imageCount: imageNodes.length,
      videoCount: videoNodes.length,
      lastFrameCount: lastFrameNodes.length,
      nRunning,
      nDone,
      nPending,
      groupCount: groups.length,
      selectedCount: selectedIds.length,
      wfBusy,
      linking: !!linking,
    });
  }, [
    imageNodes.length,
    videoNodes.length,
    lastFrameNodes.length,
    nRunning,
    nDone,
    nPending,
    groups.length,
    selectedIds.length,
    wfBusy,
    linking,
    onStatsChange,
  ]);

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  return (
    <div className="flex flex-col w-full h-full relative overflow-hidden">
      {/* Toast Notification with Click-to-Open-Drawer */}
      {toast && (
        <CanvasToast
          toast={toast}
          onOpenLog={(nodeId) => {
            setDrawerNodeId(nodeId);
            setToast(null);
          }}
          onDismiss={() => setToast(null)}
        />
      )}

      {/* Linking Helper Bar */}
      {linking && <LinkingBanner />}

      {/* Canvas Viewport */}
      <div
        ref={viewportRef}
        className={`relative w-full h-full flex-1 bg-ink overflow-hidden select-none ${
          canvasDrag ? "border-2 border-acc" : ""
        }`}
        onContextMenu={viewport.onContextMenu}
        onDragOver={(e) => {
          if (!Array.from(e.dataTransfer.types).includes("Files")) return;
          e.preventDefault();
          setCanvasDrag(true);
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setCanvasDrag(false);
        }}
        onDrop={dropFiles}
        style={{
          backgroundImage: "radial-gradient(var(--color-line2) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
        }}
        onPointerDown={viewport.onPointerDown}
      >
        <SelectionToolbar
          selectedIds={selectedIds}
          groups={groups}
          nodeCount={nodes.length}
          onCreateGroup={createGroupFromSelection}
          onAddToGroup={addSelectionToGroup}
          onRemoveFromGroup={removeFromGroup}
          onClearSelection={() => setSelectedIds([])}
        />

        <DeliveryButton onClick={() => setDeliveryOpen(true)} />

        {props.onToggleAssetDrawer && !props.assetDrawerOpen && (
          <AssetDrawerToggle onClick={props.onToggleAssetDrawer} />
        )}

        <ZoomControls zoom={view.z} setView={setView} />
        <NavigationHint />

        {canvasDrag && <FileDropOverlay />}
        {nodes.length === 0 && <EmptyCanvasHint />}

        {/* Transformed graph layer */}
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})` }}
        >
          <EdgesLayer edges={edges} focusLink={focusLink} />

          {/* Rubber-band selection rectangle */}
          {marquee && (marquee.w > 2 || marquee.h > 2) && <MarqueeRect marquee={marquee} />}

          <GroupFrames
            groups={groups}
            nodeById={nodeById}
            nodeHeights={nodeHeights}
            selectedIds={selectedIds}
            editingGroupId={editingGroupId}
            setEditingGroupId={setEditingGroupId}
            wfBusy={wfBusy}
            onBeginDrag={viewport.beginGroupDrag}
            onRename={renameGroup}
            onRunGroup={(members) => {
              setSelectedIds(members);
              setConfirmTarget({ mode: "workflow" });
            }}
            onSelectGroup={selectGroup}
            onDissolve={dissolveGroup}
          />

          {nodes.map((n) => (
            <CanvasNodeCard
              key={n.id}
              n={n}
              allNodes={nodes}
              {...optionLists}
              linking={linking}
              wfBusy={wfBusy}
              onPromptChange={(prompt) => patchNode(n.id, { prompt })}
              onFieldChange={(patch) => patchNode(n.id, patch)}
              onSourceChange={(sid) =>
                patchNode(n.id, {
                  sourceImageId: sid || null,
                  sourceImageIds: sid ? [sid] : [],
                  status: "idle",
                  reason: null,
                })
              }
              onSourcesChange={(sids) =>
                patchNode(n.id, {
                  sourceImageIds: sids,
                  sourceImageId: sids[0] ?? null,
                  status: "idle",
                  reason: null,
                })
              }
              onRemove={() => removeNode(n.id)}
              onRun={() => {
                if (n.type === "last_frame") void runNodeNow(n.id, false);
                else setConfirmTarget({ mode: "node", nodeId: n.id });
              }}
              onDot={(side) => handleDotClick(n, side)}
              onUpload={(file) => void uploadRef(n.id, file)}
              onOpenDrawer={openDrawer}
              onOpenPromptEditor={(id) => setPromptEditorNodeId(id)}
              onPreviewMedia={setPreviewMedia}
              aiGeneratingId={aiGeneratingId}
              onGenerateAiPrompt={handleGenerateAiPrompt}
              skillsList={skillsList}
              itemLibrary={itemLibrary}
              selected={selectedIds.includes(n.id)}
              onSelect={(additive) => toggleSelect(n.id, additive)}
              onMeasure={measureNode}
              focusLink={focusLink}
              onFocusLink={setFocusLink}
              onHoverRef={setHoverRef}
              onHeaderDown={(e) => viewport.onNodeHeaderDown(n, e, toggleSelect)}
            />
          ))}
        </div>
      </div>

      {contextMenu && (
        <CanvasContextMenu
          menu={contextMenu}
          groups={groups}
          selectedCount={selectedIds.length}
          onAddNode={addNodeAt}
          onCreateGroup={createGroupFromSelection}
          onAddToGroup={addSelectionToGroup}
          onClose={closeContextMenu}
        />
      )}

      {/* Right Drawer for Logs & Errors */}
      <CanvasDrawer
        node={drawerNode}
        allNodes={nodes}
        initialSection={drawerSection}
        onClose={() => setDrawerNodeId(null)}
        onRunNode={(id, dry) => void runNodeNow(id, dry)}
        onRemoveNode={removeNode}
        onUpdatePrompt={(id, prompt) => patchNode(id, { prompt })}
        onUpdateNode={patchNode}
      />

      {/* Centered Prompt Editor Modal (mở từ khung Prompt trên node) */}
      <PromptEditorModal
        open={!!promptEditorNode}
        title={`Prompt — ${promptEditorNode?.label ?? (promptEditorNode?.type === "video" ? "Node Video" : "Node Ảnh")}`}
        value={promptEditorNode?.prompt ?? ""}
        onChange={(v) => {
          if (promptEditorNode) patchNode(promptEditorNode.id, { prompt: v });
        }}
        onClose={() => setPromptEditorNodeId(null)}
        placeholder="Mô tả ảnh / chuyển động cần tạo…"
        maxChars={limits.max_prompt_chars}
      />

      {confirmTarget && (
        <RunConfirmModal
          target={confirmTarget}
          selectedCount={selectedIds.length}
          runUnits={runUnits}
          nodeById={nodeById}
          imageNodeCount={imageNodes.length}
          videoNodeCount={videoNodes.length}
          lastFrameNodeCount={lastFrameNodes.length}
          jitPromptEnabled={jitPromptEnabled}
          onJitPromptChange={setJitPromptEnabled}
          onCancel={() => setConfirmTarget(null)}
          onConfirm={() => {
            if (confirmTarget.mode === "workflow") void runWorkflow(false);
            else void runNodeNow(confirmTarget.nodeId, false).then(() => setConfirmTarget(null));
          }}
        />
      )}

      {hoverRef && <RefHoverTooltip info={hoverRef} />}

      {/* Media Preview Modal (Large Split View) */}
      <MediaPreviewModal
        item={previewMedia}
        onClose={() => setPreviewMedia(null)}
        onInsertToCanvas={(it) => addReferenceNode(it.url, it.name)}
      />
      <DeliveryModal
        open={deliveryOpen}
        onClose={() => setDeliveryOpen(false)}
        runsByClip={deliveryRuns}
        itemsByNode={deliveryItems}
      />
    </div>
  );
});

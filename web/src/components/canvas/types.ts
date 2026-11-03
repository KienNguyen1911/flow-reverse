import type { WorkspaceCanvasState } from "../../types";
import type { CanvasDrawerNode } from "../CanvasDrawer";

export type NodeStatus =
  | "idle"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "rejected"
  | "skipped";
export type NodeType = "ref" | "image" | "video" | "last_frame";

/** Tab / section the Right Inspector should focus when opened from the node body. */
export type DrawerSection = "config" | "prompt" | "sources" | "preview" | "logs" | "error";

export type CanvasNode = CanvasDrawerNode;

/**
 * Visual Group / Scope: a labelled frame that owns a set of nodes.
 * Failure policy: when a node inside a group fails, the rest of THAT group is
 * skipped and the workflow continues with the next group.
 */
export interface CanvasGroup {
  id: string;
  name: string;
  nodeIds: string[];
  color?: string | null;
  /** Manual frame override (set when the user drags/resizes the frame itself). */
  x?: number | null;
  y?: number | null;
  w?: number | null;
  h?: number | null;
}

export interface Graph {
  nodes: CanvasNode[];
  groups: CanvasGroup[];
}

export interface View {
  x: number;
  y: number;
  z: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** One isolated execution unit: a visual group, or a connected set of ungrouped nodes. */
export interface RunUnit {
  id: string;
  name: string;
  color: string | null;
  kind: "group" | "loose";
  nodeIds: string[];
}

export interface ToastInfo {
  id: number;
  message: string;
  type: "ok" | "info" | "err";
  nodeId?: string;
}

export type ShowToast = (message: string, type?: ToastInfo["type"], nodeId?: string) => void;

export interface LinkingState {
  id: string;
  kind: NodeType;
  side: "in" | "out";
}

export interface FocusLink {
  from: string;
  to: string;
}

/** Quick-look tooltip of a reference image (viewport coordinates). */
export interface HoverRefInfo {
  src: CanvasNode;
  index: number;
  x: number;
  y: number;
}

export interface ContextMenuState {
  x: number;
  y: number;
  canvasX: number;
  canvasY: number;
}

export type ConfirmTarget = { mode: "workflow" } | { mode: "node"; nodeId: string };

export type DragState =
  | { kind: "pan"; sx: number; sy: number; ox: number; oy: number }
  | { kind: "node"; id: string; sx: number; sy: number; ox: number; oy: number }
  | { kind: "group"; id: string; sx: number; sy: number; origin: { id: string; x: number; y: number }[] }
  | {
      kind: "marquee";
      sx: number;
      sy: number;
      cx: number;
      cy: number;
      additive: boolean;
      base: string[];
      moved: boolean;
      keep: boolean;
    };

export interface CustomTemplate {
  id: string;
  name: string;
  createdAt: number;
  nodes: CanvasNode[];
  groups?: CanvasGroup[];
}

export interface CanvasStats {
  imageCount: number;
  videoCount: number;
  lastFrameCount: number;
  nRunning: number;
  nDone: number;
  nPending: number;
  groupCount: number;
  selectedCount: number;
  wfBusy: boolean;
  linking: boolean;
}

export interface CanvasPanelHandle {
  addNode: (type: NodeType) => void;
  addReferenceNode: (url: string, fileName?: string) => void;
  loadTemplate: (name: string) => void;
  saveCurrentTemplate: (name: string) => void;
  deleteCustomTemplate: (id: string) => void;
  getCustomTemplates: () => CustomTemplate[];
  runWorkflow: (dry: boolean) => Promise<void>;
  openConfirmWorkflow: () => void;
  /** Current serialized canvas, including viewport and derived edges. */
  getCanvasState: () => WorkspaceCanvasState;
  /** Built-in/custom template as a standalone canvas state (for new projects). */
  getTemplateCanvasState: (name: string) => WorkspaceCanvasState | null;
  /** Persist any pending debounced edit immediately. */
  flushSave: () => Promise<void>;
}

export type WorkspaceSaveState = "idle" | "saving" | "saved" | "error";

export interface CanvasPanelProps {
  /** Active workspace project (local canvas group). */
  workspaceProjectId?: string | null;
  /** Persisted canvas of the active project; hydrated once per project id. */
  workspaceCanvasState?: WorkspaceCanvasState | null;
  onWorkspaceSaveState?: (state: WorkspaceSaveState) => void;
  onWorkspaceSaved?: (projectId: string) => void;
  onStatsChange?: (stats: CanvasStats) => void;
  onToggleAssetDrawer?: () => void;
  assetDrawerOpen?: boolean;
  onTemplatesChange?: (templates: { id: string; name: string }[]) => void;
  onAssetGenerated?: () => void;
}

import type { LibraryItem } from "../../../types";
import type { PreviewMediaItem } from "../../MediaPreviewModal";
import type { CanvasNode, DrawerSection, FocusLink, HoverRefInfo, LinkingState } from "../types";
import type { NodeOptionLists } from "./optionLists";

/** Per-card dropdown open-state: at most one pill dropdown is open at a time. */
export interface CardDropdown {
  open: string | null;
  toggle: (id: string) => void;
  close: () => void;
}

/** Callbacks + context a node body needs to edit its node. */
export interface NodeBodyActions {
  onFieldChange: (patch: Partial<CanvasNode>) => void;
  onSourceChange: (sid: string) => void;
  onSourcesChange: (sids: string[]) => void;
  onOpenDrawer: (id: string, section?: DrawerSection) => void;
  onOpenPromptEditor: (id: string) => void;
  onPreviewMedia?: (item: PreviewMediaItem) => void;
}

export interface CanvasNodeCardProps extends NodeOptionLists {
  n: CanvasNode;
  allNodes: CanvasNode[];
  linking: LinkingState | null;
  wfBusy: boolean;
  onPromptChange: (v: string) => void;
  onFieldChange: (patch: Partial<CanvasNode>) => void;
  onSourceChange: (sid: string) => void;
  onSourcesChange: (sids: string[]) => void;
  onRemove: () => void;
  onRun: () => void;
  onDot: (side: "in" | "out") => void;
  onUpload: (file: File) => void;
  onOpenDrawer: (id: string, section?: DrawerSection) => void;
  onOpenPromptEditor: (id: string) => void;
  onPreviewMedia?: (item: PreviewMediaItem) => void;
  aiGeneratingId?: string | null;
  onGenerateAiPrompt?: (id: string) => void;
  skillsList?: { id: string; name: string }[];
  itemLibrary?: LibraryItem[];
  /** Cặp (nguồn → đích) đang được hover để tô sáng edge + node nguồn. */
  focusLink?: FocusLink | null;
  onFocusLink?: (link: FocusLink | null) => void;
  onHoverRef?: (info: HoverRefInfo | null) => void;
  selected?: boolean;
  onSelect?: (additive: boolean) => void;
  onMeasure?: (id: string, height: number) => void;
  onHeaderDown: (e: React.PointerEvent) => void;
}

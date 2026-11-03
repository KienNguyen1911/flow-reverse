// Public entry of the node canvas. The implementation lives in `./canvas/`.
export { CanvasPanel } from "./canvas/CanvasPanel";
export { BUILTIN_TEMPLATES } from "./canvas/templates";
export { canvasStateToGraph, graphToCanvasState } from "./canvas/serialization";
export type {
  CanvasPanelHandle,
  CanvasPanelProps,
  CanvasStats,
  CustomTemplate,
  DrawerSection,
  WorkspaceSaveState,
} from "./canvas/types";

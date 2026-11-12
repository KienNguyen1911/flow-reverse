//: Kịch bản mặc định — cùng đường dẫn với `DeliveryModal` và `script_contract.load_default_script`.
export const SCRIPT_PATH = "configs/lookbook_script.json";

// --------------------------------------------------------------------------- //
// Canvas node graph — image nodes feed video nodes (image-to-video chains).
// Backend: POST /api/node/image, POST /api/node/video, POST /api/node/last_frame
// Chaining works because resolve_input_path() accepts /api/node/files/... URLs
// as attachments, so an image node's file_url becomes a video node's frame_path,
// and a last_frame node extracts the final frame of a video to feed the next video/image.
// --------------------------------------------------------------------------- //

export const NODE_W = 280;
export const ANCHOR_Y = 22;
export const GROUP_PAD = 26;
export const GROUP_HEADER_H = 40;
export const FALLBACK_NODE_H = 220;
export const GROUP_COLORS = ["#7c9cff", "#4ade80", "#f59e0b", "#c084fc", "#f472b6", "#22d3ee"];
export const STORAGE_KEY = "fb_canvas_graph_v1";
export const TEMPLATES_KEY = "fb_custom_templates_v1";

/**
 * Job lifecycle lives in `web/src/jobWatcher.ts` — it owns the terminal set, so this module
 * re-exports it instead of keeping a second copy that can drift.
 */
export { TERMINAL_STATES, isTerminal } from "../../jobWatcher";

export const ACTIVE = new Set(["queued", "running"]);


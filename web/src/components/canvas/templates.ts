import { GROUP_COLORS } from "./constants";
import type { CanvasGroup, CanvasNode } from "./types";

export const BUILTIN_TEMPLATES = [
  { id: "lookbook_8s", name: "Lookbook 16s (Plate → Video 1 → Video 2)" },
  { id: "tryon", name: "Video Thử Đồ (Try-On 16s)" },
] as const;

function createLookbook8sTemplate(): { nodes: CanvasNode[]; groups: CanvasGroup[] } {
  const nodes: CanvasNode[] = [
    // --- Nhóm 1: Plate → Video 1 → Frame cuối → Video 2 ---
    // Board có cột item đã bị bỏ: AI video không vẽ được chữ/logic UI. Lớp dựng
    // (HyperFrames desktop) lo card/kinetic text và tự canh vị trí, nên plate không
    // cần chừa cột trái nữa — chỉ cần nền sạch và người mẫu đúng khung.
    {
      id: "lb_ref_model",
      type: "ref",
      label: "Ảnh tham chiếu (ảnh sản phẩm gốc)",
      x: 60,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: null,
      fileName: null,
    },
    {
      id: "lb_plate",
      type: "image",
      label: "Plate (chỉ người mẫu, nền sạch)",
      x: 420,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_ref_model",
      sourceImageIds: ["lb_ref_model"],
      agentSkillId: "try-on-image-prompter",
      agentCustomHint: "plate first frame",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_video_1",
      type: "video",
      label: "Video 1 (8s: hook)",
      x: 780,
      y: 80,
      prompt: "Prompt chuyển động cho clip hook 8s...",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_plate",
      sourceImageIds: ["lb_plate"],
      agentSkillId: "lookbook-video-prompter",
      clipId: "clip1",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_last_frame",
      type: "last_frame",
      label: "Frame Cuối Video 1",
      x: 1140,
      y: 80,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_video_1",
      sourceImageIds: ["lb_video_1"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "lb_video_2",
      type: "video",
      label: "Video 2 (8s: showcase)",
      x: 1500,
      y: 80,
      prompt: "Prompt chuyển động cho clip showcase 8s...",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_last_frame",
      sourceImageIds: ["lb_last_frame"],
      agentSkillId: "lookbook-video-prompter",
      clipId: "clip2",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },

    // --- Nhóm 2: Cutout sản phẩm cho lớp card (không phải first frame) ---
    {
      id: "lb_ref_garment_upload",
      type: "ref",
      label: "Ảnh Shopee (lifestyle, kéo thả)",
      x: 60,
      y: 690,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: null,
      fileName: null,
    },
    {
      id: "lb_node_cutout_front",
      type: "image",
      label: "Cutout sản phẩm",
      x: 420,
      y: 690,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "lb_ref_garment_upload",
      sourceImageIds: ["lb_ref_garment_upload"],
      agentSkillId: "lookbook-item-cutout-prompter",
      isItem: true,
      itemName: "",
      itemScope: "top",
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "1:1",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
  ];

  // Mỗi món đúng MỘT node cutout — một mặt trước là đủ, không có node mặt sau.
  // Thẻ sản phẩm trên timeline chỉ cần một ảnh; ảnh lưng là chi phí credit không đổi lại
  // được gì (nó chỉ xuất hiện ở một shot 2–3s và có thể bị che bởi chữ).
  // Template chỉ cấp MỘT node mẫu: người bán có bao nhiêu món cũng dùng lại được bằng
  // cách nhân bản node và đặt `itemName`, không phải khai danh sách vào script.
  const cutoutIds = nodes
    .filter((n) => n.id.startsWith("lb_node_cutout_"))
    .map((n) => n.id);

  const groups: CanvasGroup[] = [
    {
      id: "lb_group_video_8s",
      name: "Nhóm 1: Plate → Video 1 → Video 2 (nền cho HyperFrames)",
      nodeIds: ["lb_ref_model", "lb_plate", "lb_video_1", "lb_last_frame", "lb_video_2"],
      color: GROUP_COLORS[0],
    },
    {
      id: "lb_group_items",
      name: "Nhóm 2: Cutout sản phẩm (lớp card, không phải first frame)",
      nodeIds: ["lb_ref_garment_upload", ...cutoutIds],
      color: GROUP_COLORS[1],
    },
  ];

  return { nodes, groups };
}

function createTryOnTemplate(): CanvasNode[] {
  return [
    {
      id: "tryon_ref_model",
      type: "ref",
      label: "Ảnh Người Mẫu (Nabi)",
      x: 60,
      y: 90,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: "/api/assets/nabi_model.png",
      fileName: "nabi_model.png",
    },
    {
      id: "tryon_ref_garment",
      type: "ref",
      label: "Ảnh Trang Phục",
      x: 60,
      y: 430,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: null,
      sourceImageIds: [],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
      fileUrl: "/api/assets/sample_garment.png",
      fileName: "sample_garment.png",
    },
    {
      id: "tryon_node_image",
      type: "image",
      label: "Node Ảnh (First Frame)",
      x: 420,
      y: 220,
      prompt: "@nabi wearing this outfit, elegant studio fashion portrait, full body shot, high resolution, 8k, photorealistic",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_ref_model",
      sourceImageIds: ["tryon_ref_model", "tryon_ref_garment"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_video_1",
      type: "video",
      label: "Node Video 1 (8s)",
      x: 780,
      y: 220,
      prompt: "Nabi stands elegantly, smooth camera slow zoom in, gentle movement showing garment drape, natural studio lighting, 8 seconds",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_image",
      sourceImageIds: ["tryon_node_image"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_last_frame",
      type: "last_frame",
      label: "Frame Cuối (Video 1)",
      x: 1140,
      y: 220,
      prompt: "",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_video_1",
      sourceImageIds: ["tryon_node_video_1"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
    {
      id: "tryon_node_video_2",
      type: "video",
      label: "Node Video 2 (8s Nối tiếp)",
      x: 1500,
      y: 220,
      prompt: "Nabi turns slightly to showcase side profile and back of the outfit, natural fashion pose, seamless motion continuation, 8 seconds",
      aspectRatio: "9:16",
      seed: null,
      sourceImageId: "tryon_node_last_frame",
      sourceImageIds: ["tryon_node_last_frame"],
      videoRatio: "9:16",
      resolution: "1080p",
      imageAspectRatio: "9:16",
      autoImagePrompt: "",
      removeWatermark: true,
      jobId: null,
      status: "idle",
    },
  ];
}

/** Built-in template graph by id; `null` for ids that are not built in (custom templates). */
export function buildBuiltinTemplate(
  nameOrId: string,
): { nodes: CanvasNode[]; groups: CanvasGroup[]; label: string } | null {
  if (nameOrId === "tryon") {
    return {
      nodes: createTryOnTemplate(),
      groups: [
        {
          id: "tryon_group_image",
          name: "Nhóm 1: Sinh ảnh Lookbook",
          nodeIds: ["tryon_ref_model", "tryon_ref_garment", "tryon_node_image"],
          color: GROUP_COLORS[0],
        },
        {
          id: "tryon_group_video",
          name: "Nhóm 2: Render Video Try-on",
          nodeIds: ["tryon_node_video_1", "tryon_node_last_frame", "tryon_node_video_2"],
          color: GROUP_COLORS[1],
        },
      ],
      label: "Video Thử Đồ (Try-On 16s)",
    };
  }

  if (nameOrId === "lookbook_8s") {
    // Template chỉ cấp MỘT node cutout mẫu: người bán có bao nhiêu món cũng nhân bản
    // node rồi đặt tên, không phải khai danh sách món vào script.
    const tpl = createLookbook8sTemplate();
    return { ...tpl, label: "Lookbook 16s (Plate → Video 1 → Video 2)" };
  }

  return null;
}

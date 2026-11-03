export const SAMPLE_FIRST_FRAME_PATH = "assets/sample_first_frame.png";

export const STEPS_CHAIN = [
  { id: 1, label: "Tạo Video 1 (8s)", desc: "Upload First Frame & render Video 1" },
  { id: 2, label: "Trích xuất Last Frame", desc: "FFmpeg cắt frame chính xác 100%" },
  { id: 3, label: "Tạo Video 2 (8s)", desc: "Upload Last Frame & render Video 2" },
  { id: 4, label: "Ghép hoàn chỉnh 16s", desc: "Nối liền mạch 2 video không giật" },
];

export const STEPS_SINGLE = [
  { id: 1, label: "Tạo Video (8s)", desc: "Upload First Frame & render Video 8s" },
  { id: 2, label: "Hậu kỳ & Xóa Watermark", desc: "Làm sạch watermark & xuất MP4" },
];

export const PRESETS_V1 = [
  {
    label: "👗 Xoay dáng tự nhiên",
    prompt:
      "A photorealistic young woman wearing the outfit, turns gently to showcase the dress, elegant natural movement, soft studio lighting, high details, 8 seconds",
  },
  {
    label: "🚶‍♀️ Bước đi nhìn camera",
    prompt:
      "A young woman walking slowly forward towards the camera, smiling naturally, fabric flowing softly, cinematic depth of field, 8 seconds",
  },
];

export const PRESETS_V2 = [
  {
    label: "✨ Xoay 180° khoe lưng",
    prompt:
      "Continuing seamlessly from the last frame, the young woman turns 180 degrees to showcase the back details of the garment, then looks over her shoulder with a graceful smile, smooth motion, 8 seconds",
  },
  {
    label: "📸 Cận cảnh tà áo & nụ cười",
    prompt:
      "Continuing smoothly from the last frame, the young woman steps closer to camera, adjusting the outfit sleeve, confident lifestyle fashion pose, 8 seconds",
  },
];

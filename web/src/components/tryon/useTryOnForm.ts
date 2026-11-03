import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { SAMPLE_FIRST_FRAME_PATH } from "./constants";
import type { AspectRatio, ShowToast, UploadedFile } from "./types";

/** Setup-studio form state (first frame, prompts, project, render options) and upload handlers. */
export function useTryOnForm({
  selectedProjectId,
  showToast,
}: {
  selectedProjectId: string | null;
  showToast: ShowToast;
}) {
  // Setup form states
  const [firstFrame, setFirstFrame] = useState<UploadedFile | null>(null);
  const [firstFrameUploading, setFirstFrameUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const [videoPrompt1, setVideoPrompt1] = useState(
    "A photorealistic young woman wearing the outfit, turns gently to showcase the dress, elegant natural movement, soft studio lighting, high details, 8 seconds"
  );
  const [videoPrompt2, setVideoPrompt2] = useState(
    "Continuing seamlessly from the last frame, the young woman turns 180 degrees to showcase the back details of the garment, then looks over her shoulder with a graceful smile, smooth motion, 8 seconds"
  );

  const [targetProjectId, setTargetProjectId] = useState<string>(selectedProjectId || "");
  const [autoStitch, setAutoStitch] = useState(true);
  const [removeWatermark, setRemoveWatermark] = useState<boolean>(
    () => (localStorage.getItem("fb_tryon_rm_wm") ?? "1") !== "0"
  );
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("9:16");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Keep target project in sync with TopBar
  useEffect(() => {
    if (selectedProjectId && !targetProjectId) {
      setTargetProjectId(selectedProjectId);
    }
  }, [selectedProjectId, targetProjectId]);

  // Upload handler
  const handleUploadFile = async (file: File) => {
    setFirstFrameUploading(true);
    try {
      const res = await api.upload(file);
      setFirstFrame({
        path: res.path,
        filename: res.filename,
        url: res.url,
        size: res.size,
      });
      showToast("Tải ảnh First Frame thành công!", "ok");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Tải ảnh thất bại", "err");
    } finally {
      setFirstFrameUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleUseSampleFirstFrame = () => {
    setFirstFrame({
      path: SAMPLE_FIRST_FRAME_PATH,
      filename: "sample_first_frame.png",
      url: `/api/assets/sample_first_frame.png`,
      size: 684203,
    });
    showToast("Đã nạp ảnh mẫu First Frame", "info");
  };

  return {
    firstFrame,
    setFirstFrame,
    firstFrameUploading,
    isDragging,
    setIsDragging,
    videoPrompt1,
    setVideoPrompt1,
    videoPrompt2,
    setVideoPrompt2,
    targetProjectId,
    setTargetProjectId,
    autoStitch,
    setAutoStitch,
    removeWatermark,
    setRemoveWatermark,
    aspectRatio,
    setAspectRatio,
    fileInputRef,
    handleUploadFile,
    handleUseSampleFirstFrame,
  };
}

export type TryOnForm = ReturnType<typeof useTryOnForm>;

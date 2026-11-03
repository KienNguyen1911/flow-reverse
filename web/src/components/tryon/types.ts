import type { Job, TryOnRunManifest } from "../../types";

export interface UploadedFile {
  path: string;
  filename: string;
  url: string;
  size?: number;
}

export interface ToastInfo {
  id: number;
  message: string;
  type: "ok" | "info" | "err";
}

export type ShowToast = (message: string, type?: ToastInfo["type"]) => void;

export type AspectRatio = "9:16" | "16:9";
export type ViewMode = "studio" | "history";
export type DockTab = "all" | "running" | "queued" | "done";
export type ResultTab = "final" | "subvideos" | "frames" | "prompts";
export type HistoryStatusFilter = "all" | "succeeded" | "failed";

/** A pipeline step enriched with its computed progress state. */
export interface StepView {
  id: number;
  label: string;
  desc: string;
  status: "pending" | "running" | "succeeded" | "failed";
  error: string | null;
}

export type ReuseSource = TryOnRunManifest | Job;

export function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return "0s";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

export function formatRelativeTime(ms?: number | null): string {
  if (!ms) return "";
  const diffSec = Math.floor((Date.now() - ms) / 1000);
  if (diffSec < 60) return `${diffSec}s trước`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m trước`;
  return `${Math.floor(diffSec / 3600)}h trước`;
}

export function sanitizePromptClient(raw: string): string {
  if (!raw) return "";
  let s = raw
    .replace(/\b(of\s+)?(the\s+)?exact\s+(young\s+)?(korean\s+|asian\s+)?(woman|girl|model|lady)(\s+from\s+the\s+reference\s+(image|photo))?\b/gi, "of the fashion model")
    .replace(/\b(young\s+)?(korean|asian|japanese|chinese)\s+(woman|girl|model|lady)\b/gi, "fashion model")
    .replace(/\bfrom\s+the\s+reference\s+(image|photo)(\s+pose)?\b/gi, "in the scene")
    .replace(/\b(strictly\s+)?lock(ed)?\s+facial\s+(identity|features|structure)(\s+and\s+hairstyle)?\b/gi, "natural expression")
    .replace(/\b(strictly\s+)?maintain(ing)?\s+(exact\s+)?facial\s+(identity|features)\b/gi, "natural expression")
    .replace(/\b(celebrity|idol|actress|k-pop|famous\s+person)\b/gi, "model")
    .replace(/Camera\s*&\s*Realism:[\s\S]*$/i, "Smooth natural movement, realistic fabric drape, soft lighting, 24fps, 8 seconds.")
    .replace(/-\s*0s\s*to\s*2s\s*\([^)]*\):\s*/gi, "")
    .replace(/-\s*2s\s*to\s*6s\s*\([^)]*\):\s*/gi, " ")
    .replace(/-\s*6s\s*to\s*8s\s*\([^)]*\):\s*/gi, " ");
  return s.replace(/\s{2,}/g, " ").trim();
}

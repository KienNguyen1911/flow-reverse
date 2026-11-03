export function fmtTime(ts?: number | string | null): string {
  if (!ts) return "";
  let d: Date;
  if (typeof ts === "number") {
    d = new Date(ts < 10000000000 ? ts * 1000 : ts);
  } else {
    d = new Date(ts);
    if (isNaN(d.getTime())) {
      const num = Number(ts);
      if (!isNaN(num)) d = new Date(num < 10000000000 ? num * 1000 : num);
    }
  }
  if (isNaN(d.getTime())) return String(ts);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}`;
}

export function getTimestamp(ts?: number | string | null): number {
  if (!ts) return 0;
  if (typeof ts === "number") {
    return ts < 10000000000 ? ts * 1000 : ts;
  }
  const d = new Date(ts);
  if (!isNaN(d.getTime())) return d.getTime();
  const num = Number(ts);
  return !isNaN(num) ? (num < 10000000000 ? num * 1000 : num) : 0;
}

export function fmtBytes(b?: number): string {
  if (!b || b <= 0) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export function cleanDisplayName(name: string): string {
  return name.replace(/^(\d{12,14})_/, "");
}

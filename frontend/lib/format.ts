export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function fmtDelay(min: number | null | undefined): string {
  if (min === null || min === undefined) return "—";
  const v = Math.round(min * 10) / 10;
  return v <= 0 ? "On time" : `+${v} min`;
}

export function fmtDelayShort(min: number | null | undefined): string {
  if (min === null || min === undefined) return "—";
  const v = Math.round(min * 10) / 10;
  return `+${v}`;
}

export function fmtSigned(min: number | null | undefined): string {
  if (min === null || min === undefined) return "—";
  const v = Math.round(min * 10) / 10;
  return v > 0 ? `+${v}` : `${v}`;
}

export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}

export function countdown(iso: string | null | undefined): string {
  if (!iso) return "—";
  const target = new Date(iso).getTime();
  if (isNaN(target)) return "—";
  const diff = Math.floor((target - Date.now()) / 1000);
  if (diff <= 0) return "due now";
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function riskColor(label: string): string {
  switch (label) {
    case "NORMAL": return "text-green-600";
    case "LOW": return "text-sky-600";
    case "MEDIUM": return "text-amber-600";
    case "HIGH": return "text-orange-600";
    case "VERY HIGH": return "text-red-600";
    default: return "text-gray-500";
  }
}

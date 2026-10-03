"use client";

import { fmtAgo, countdown } from "@/lib/format";

export default function LiveUpdateIndicator({
  updatedAt, nextRefresh, degraded,
}: { updatedAt: string | null; nextRefresh: string | null; degraded: boolean }) {
  return (
    <div className="rounded-md border border-gray-300 bg-white px-4 py-2.5 text-right text-[11px] leading-relaxed">
      <div className="flex items-center justify-end gap-1.5">
        <span className={`h-2 w-2 rounded-full ${degraded ? "bg-amber-500" : "bg-green-500 animate-pulse"}`} />
        <span className="font-bold text-gray-800">{degraded ? "Degraded" : "Monitoring"}</span>
      </div>
      <div className="text-gray-500">Last updated: <span className="text-gray-700">{fmtAgo(updatedAt)}</span></div>
      <div className="text-gray-500">Next refresh: <span className="text-sky-600">{countdown(nextRefresh)}</span></div>
      {degraded && (
        <div className="mt-1 max-w-[220px] text-[10px] text-amber-600">
          External data temporarily unavailable — showing last valid prediction.
        </div>
      )}
    </div>
  );
}

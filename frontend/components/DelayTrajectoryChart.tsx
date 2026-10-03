"use client";

import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  ReferenceLine, CartesianGrid,
} from "recharts";
import type { TrajectoryPoint } from "@/types";

interface Row {
  name: string;
  observed: number | null;
  predicted: number | null;
  bandLow: number | null;
  bandHigh: number | null;
}

function minutesBetween(isoA: string | null, isoB: string | null): number | null {
  if (!isoA || !isoB) return null;
  const diff = (new Date(isoB).getTime() - new Date(isoA).getTime()) / 60000;
  return isNaN(diff) ? null : Math.round(diff * 10) / 10;
}

export default function DelayTrajectoryChart({ trajectory }: { trajectory: TrajectoryPoint[] }) {
  const rows: Row[] = trajectory.map((p) => {
    const half = minutesBetween(p.predicted_arrival, p.eta_upper) ?? minutesBetween(p.predicted_arrival, p.eta_lower);
    const delay = p.delay_minutes ?? 0;
    return {
      name: p.station_name.length > 14 ? p.station_name.slice(0, 13) + "…" : p.station_name,
      observed: p.kind === "observed" || p.kind === "current" ? delay : null,
      predicted: p.kind === "predicted" || p.kind === "current" ? delay : null,
      bandLow: p.kind === "predicted" && half != null ? Math.max(0, delay - half) : null,
      bandHigh: p.kind === "predicted" && half != null ? delay + half : null,
    };
  });

  // Recharts needs contiguous band values; forward-fill from the current point
  let lastLow: number | null = null;
  let lastHigh: number | null = null;
  for (const row of rows) {
    if (row.bandLow != null) { lastLow = row.bandLow; lastHigh = row.bandHigh; }
    else if (lastLow != null && (row.predicted != null || row.observed != null)) {
      row.bandLow = lastLow; row.bandHigh = lastHigh;
    }
  }

  return (
    <section className="panel p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="panel-title">Delay trajectory · observed vs predicted</h3>
        <span className="text-[10px] text-gray-500">shaded band = estimated ETA range</span>
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
            <defs>
              <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.04} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fill: "#6b7280", fontSize: 10 }} interval={0} angle={-18} height={48} textAnchor="end" />
            <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} unit=" min" />
            <Tooltip
              contentStyle={{ background: "#ffffff", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#374151" }}
              formatter={(value: number | string, name: string) => [`${value} min`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" label={{ value: "schedule", fill: "#6b7280", fontSize: 10, position: "insideTopLeft" }} />
            <Area type="monotone" dataKey="bandHigh" stroke="none" fill="url(#band)" name="confidence band" legendType="none" connectNulls />
            <Area type="monotone" dataKey="bandLow" stroke="none" fill="#ffffff" fillOpacity={0.9} name="band-low" legendType="none" connectNulls />
            <Line type="monotone" dataKey="observed" name="Observed delay" stroke="#d97706" strokeWidth={2.5} dot={{ r: 3, fill: "#d97706" }} connectNulls />
            <Line type="monotone" dataKey="predicted" name="Predicted delay" stroke="#2563eb" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 3, fill: "#2563eb" }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

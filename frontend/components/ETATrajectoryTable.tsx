import type { TrajectoryPoint } from "@/types";
import { fmtTime, fmtDelayShort } from "@/lib/format";

export default function ETATrajectoryTable({ trajectory }: { trajectory: TrajectoryPoint[] }) {
  const predicted = trajectory.filter((p) => p.kind === "predicted");
  if (!predicted.length) {
    return (
      <section className="panel p-5 text-sm text-gray-500">
        No forecast shown — the journey is complete, or the train is idle
        (flip it to LIVE to generate the station-by-station forecast).
      </section>
    );
  }

  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-gray-200 px-5 py-3">
        <h3 className="panel-title">ETA trajectory table · station by station</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-[10px] uppercase tracking-wider text-gray-500">
              <th className="px-5 py-2 font-semibold">Station</th>
              <th className="px-3 py-2 font-semibold">Scheduled ETA</th>
              <th className="px-3 py-2 font-semibold">Predicted ETA</th>
              <th className="px-3 py-2 font-semibold">Pred. delay</th>
              <th className="px-3 py-2 font-semibold">Recovery</th>
              <th className="px-3 py-2 font-semibold">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {predicted.map((p, i) => (
              <tr key={p.station_code + i} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-5 py-2.5">
                  <span className="font-semibold text-gray-800">{p.station_name}</span>
                  <span className="ml-2 font-mono text-[10px] text-gray-500">{p.station_code}</span>
                  {i === predicted.length - 1 && (
                    <span className="ml-2 badge border border-amber-300 bg-amber-100 text-amber-700">DEST</span>
                  )}
                </td>
                <td className="px-3 py-2.5 font-mono text-gray-600">{fmtTime(p.scheduled_arrival)}</td>
                <td className="px-3 py-2.5 font-mono font-bold text-gray-900">
                  {fmtTime(p.predicted_arrival)}
                  <span className="ml-2 font-sans text-[10px] font-normal text-gray-500">
                    {p.eta_lower && p.eta_upper ? `${fmtTime(p.eta_lower)}–${fmtTime(p.eta_upper)}` : ""}
                  </span>
                </td>
                <td className={`px-3 py-2.5 font-mono font-bold ${(p.delay_minutes ?? 0) > 10 ? "text-red-600" : (p.delay_minutes ?? 0) > 0 ? "text-amber-600" : "text-green-600"}`}>
                  {fmtDelayShort(p.delay_minutes)}
                </td>
                <td className="px-3 py-2.5 font-mono text-green-600">{p.recovery_minutes ? `-${Math.round(p.recovery_minutes * 10) / 10}` : "0"}</td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-14 overflow-hidden rounded-full bg-gray-200">
                      <div className="h-full rounded-full bg-purple-500" style={{ width: `${p.confidence ?? 0}%` }} />
                    </div>
                    <span className="font-mono text-[11px] text-gray-600">{p.confidence != null ? `${Math.round(p.confidence)}%` : "—"}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

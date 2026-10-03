import type { PredictionFactor } from "@/types";
import { fmtSigned } from "@/lib/format";

export default function FactorPanel({
  factors,
}: {
  factors: PredictionFactor[];
}) {
  const maxImpact = Math.max(1, ...factors.map((f) => Math.abs(f.impact_minutes ?? 0)));

  return (
    <section className="panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="panel-title">Why this prediction?</h3>
      </div>

      {!factors.length && (
        <p className="rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500">
          No forecast yet — flip this train to LIVE (or check live once) so the
          engine has fresh data to explain.
        </p>
      )}
      <div className="space-y-3">
        {factors.map((f) => {          const impact = f.impact_minutes ?? 0;
          const width = Math.max(6, (Math.abs(impact) / maxImpact) * 100);
          const isRecovery = f.direction === "recovery";
          const barColor = isRecovery
            ? "bg-green-500"
            : impact > 8 ? "bg-red-500"
            : impact > 3 ? "bg-amber-500"
            : "bg-gray-400";
          return (
            <div key={f.name}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="font-semibold text-gray-800">
                  {f.name}
                </span>
                <span className="font-mono text-[11px] text-gray-500">
                  {f.value} · <span className={isRecovery ? "text-green-600" : "text-gray-700"}>{fmtSigned(impact)} min</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-200">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${width}%`, marginLeft: isRecovery ? 0 : `${100 - width}%` }}
                />
              </div>
              {f.explanation && <p className="mt-1 text-[10px] leading-snug text-gray-500">{f.explanation}</p>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

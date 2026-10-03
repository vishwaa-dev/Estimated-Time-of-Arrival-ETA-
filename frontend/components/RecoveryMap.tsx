import type { RecoverySection } from "@/types";

const CLASS_STYLES: Record<string, { bar: string; text: string; dot: string }> = {
  HIGH: { bar: "from-green-500/70 to-green-300/30", text: "text-green-600", dot: "bg-green-500" },
  MEDIUM: { bar: "from-amber-500/70 to-amber-300/30", text: "text-amber-600", dot: "bg-amber-500" },
  LOW: { bar: "from-red-500/70 to-red-300/30", text: "text-red-600", dot: "bg-red-500" },
};

export default function RecoveryMap({
  sections,
  summary,
}: {
  sections: RecoverySection[];
  summary: { applied_recovery_minutes: number; raw_recoverable_minutes: number; capped_by: string | null };
}) {
  return (
    <section className="panel p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="panel-title">Recovery feasibility map · estimated potential per section</h3>
        <span className="badge border border-green-300 bg-green-100 text-green-700">
          RECOVERY: ESTIMATED
        </span>
      </div>

      <div className="space-y-3">
        {sections.map((s, i) => {
          const style = CLASS_STYLES[s.classification] ?? CLASS_STYLES.LOW;
          return (
            <div key={i}>
              <div className="flex flex-wrap items-baseline justify-between gap-1 text-xs">
                <span className="font-semibold text-gray-800">
                  {s.from_station_name} <span className="text-sky-600">→</span> {s.to_station_name}
                  <span className="ml-2 font-mono text-[10px] text-gray-500">{Math.round(s.distance_km)} km</span>
                </span>
                <span className="text-[11px]">
                  <span className={`font-bold ${style.text}`}>{s.classification}</span>
                  <span className="ml-2 font-mono text-gray-500">
                    {Math.round(s.recovery_potential_minutes * 10) / 10} min recoverable
                  </span>
                </span>
              </div>
              <div className="mt-1 flex h-2.5 gap-1">
                <div className={`h-full rounded-l-full rounded-r-full bg-gradient-to-r ${style.bar}`} style={{ width: "70%" }} />
                <div className="h-full flex-1 rounded-r-full bg-gray-200" />
              </div>
              <p className="mt-1 text-[10px] text-gray-500">
                {s.reason} · scheduled run {Math.round(s.scheduled_running_minutes)} min · slack{" "}
                {Math.round(s.slack_minutes * 10) / 10} min
                {s.dwell_recovery_minutes > 0 && ` · dwell compression ${Math.round(s.dwell_recovery_minutes * 10) / 10} min`}
              </p>
            </div>
          );
        })}
        {!sections.length && (
          <p className="text-xs text-gray-500">No upcoming sections — journey complete or awaiting departure.</p>
        )}
      </div>

      <p className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-2.5 text-[10px] leading-snug text-gray-500">
        Applied recovery in this forecast: <span className="font-bold text-green-600">
        {Math.round(summary.applied_recovery_minutes * 10) / 10} min</span> of an estimated{" "}
        {Math.round(summary.raw_recoverable_minutes * 10) / 10} min available
        {summary.capped_by ? ` — bounded by ${summary.capped_by}.` : "."} Recovery can never exceed the
        current delay or the configured maximum. Section labels are estimates, not proven railway bottlenecks.
      </p>
    </section>
  );
}

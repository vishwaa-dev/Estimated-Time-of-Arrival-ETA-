import type { PredictionPayload } from "@/types";
import { fmtTime, fmtDelay } from "@/lib/format";

function Card({
  label, value, sub, accent, wide,
}: { label: string; value: string; sub?: string; accent: string; wide?: boolean }) {
  return (
    <div className={`panel px-4 py-3 ${wide ? "col-span-2 sm:col-span-1" : ""}`}>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${accent}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-gray-500">{sub}</div>}
    </div>
  );
}

export default function MetricCards({ data }: { data: PredictionPayload }) {
  const p = data.prediction;
  const c = data.current_state;
  const idle = data.forecast_available === false;
  const finalDelay = p.final_predicted_delay_minutes;
  const delayColor =
    finalDelay == null ? "text-gray-500"
    : finalDelay > 15 ? "text-red-600"
    : finalDelay > 5 ? "text-amber-600"
    : "text-green-600";

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Card
        label="Current delay"
        value={fmtDelay(c.current_delay_minutes)}
        sub={`observed · ${c.data_source}`}
        accent={c.current_delay_minutes > 5 ? "text-red-600" : c.current_delay_minutes > 0 ? "text-amber-600" : "text-green-600"}
      />
      <Card
        label="Predicted final delay"
        value={fmtDelay(finalDelay)}
        sub={idle ? "go live for a forecast" : `${data.primary_reason.toLowerCase()} driving`}
        accent={delayColor}
      />
      <Card
        label="Estimated ETA"
        value={fmtTime(p.predicted_eta)}
        sub={p.scheduled_arrival ? `scheduled ${fmtTime(p.scheduled_arrival)}` : undefined}
        accent="text-gray-900"
        wide
      />
      <Card
        label="ETA range"
        value={p.eta_lower_bound && p.eta_upper_bound ? `${fmtTime(p.eta_lower_bound)} – ${fmtTime(p.eta_upper_bound)}` : "—"}
        sub="estimated interval"
        accent="text-sky-600"
      />
      <Card
        label="Confidence"
        value={p.confidence != null ? `${Math.round(p.confidence)}%` : "—"}
        sub={p.confidence_label}
        accent="text-purple-600"
      />
      <Card
        label="Recovery potential"
        value={idle ? "—" : `${Math.round(data.recovery_summary.applied_recovery_minutes)} min`}
        sub={idle ? "no forecast while idle" : data.recovery_summary.capped_by ? `capped: ${data.recovery_summary.capped_by}` : "from route slack"}
        accent="text-green-600"
      />
    </section>
  );
}

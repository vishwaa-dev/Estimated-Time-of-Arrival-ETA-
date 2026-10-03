import type { EventItem } from "@/types";
import { fmtClock } from "@/lib/format";

function cleanMsg(msg: string): string {
  return msg.replace(" — SIMULATED", "").replace("(simulated journey loop)", "(journey restarted)");
}

const TYPE_STYLES: Record<string, { icon: string; color: string }> = {
  arrival: { icon: "🚉", color: "bg-sky-400" },
  departure: { icon: "🚆", color: "bg-sky-400" },
  prediction: { icon: "🧮", color: "bg-purple-400" },
  weather: { icon: "🌦️", color: "bg-amber-400" },
  simulation: { icon: "🧪", color: "bg-purple-400" },
  system: { icon: "⚙️", color: "bg-gray-400" },
};

export default function EventTimeline({ events }: { events: EventItem[] }) {
  return (
    <section className="panel p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="panel-title">Event timeline</h3>
        <span className="text-[10px] text-gray-500">{events.length} recent</span>
      </div>
      <div className="max-h-80 space-y-0 overflow-y-auto pr-1">
        {events.map((e, i) => {
          const style = TYPE_STYLES[e.type] ?? TYPE_STYLES.system;
          return (
            <div key={i} className="relative flex gap-3 pb-4 last:pb-0">
              {i < events.length - 1 && (
                <div className="absolute left-[7px] top-5 h-full w-px bg-gray-200" />
              )}
              <div className={`mt-1 h-[15px] w-[15px] shrink-0 rounded-full border border-gray-300 bg-white ${style.color} flex items-center justify-center text-[8px]`}>
                {style.icon}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-[11px] text-gray-500">{fmtClock(e.timestamp)}</span>
                </div>
                <p className="text-xs leading-snug text-gray-700">{cleanMsg(e.message)}</p>
              </div>
            </div>
          );
        })}
        {!events.length && <p className="text-xs text-gray-500">No events yet — waiting for the first refresh cycle.</p>}
      </div>
    </section>
  );
}

import type { WeatherPayload } from "@/types";
import { riskColor } from "@/lib/format";

function weatherIcon(condition: string | null): string {
  const c = (condition || "").toLowerCase();
  if (c.includes("thunder") || c.includes("storm")) return "⛈️";
  if (c.includes("heavy") && c.includes("rain")) return "🌧️";
  if (c.includes("rain") || c.includes("drizzle") || c.includes("shower")) return "🌦️";
  if (c.includes("cloud") || c.includes("overcast")) return "☁️";
  if (c.includes("mist") || c.includes("fog") || c.includes("haze")) return "🌫️";
  if (c.includes("snow")) return "❄️";
  return "☀️";
}

export default function WeatherPanel({ weather }: { weather: WeatherPayload }) {
  return (
    <section className="panel p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="panel-title">Weather at train location</h3>
        {!weather.is_simulated && weather.source === "LIVE" ? (
          <span className="badge border border-green-300 bg-green-100 text-green-700">WEATHER: LIVE</span>
        ) : !weather.is_simulated && weather.source === "CACHED" ? (
          <span className="badge border border-amber-300 bg-amber-100 text-amber-700">CACHED</span>
        ) : (
          <span className="badge border border-gray-300 bg-gray-100 text-gray-500">NO DATA</span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-4xl">{weatherIcon(weather.weather_condition)}</span>
        <div>
          <div className="text-lg font-bold text-gray-900">{weather.weather_condition ?? "—"}</div>
          <div className="text-[11px] text-gray-500">{weather.location ?? "location unknown"}</div>
        </div>
        <div className="ml-auto text-right">
          <div className={`text-xl font-bold ${riskColor(weather.weather_risk_label)}`}>
            {weather.weather_risk_label}
          </div>
          <div className="text-[10px] text-gray-500">risk {Math.round(weather.weather_risk_score)}/100</div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center">
        {[
          { label: "Temp", value: weather.temperature != null ? `${Math.round(weather.temperature)}°C` : "—" },
          { label: "Rain (1h)", value: weather.rainfall != null ? `${weather.rainfall} mm` : "—" },
          { label: "Wind", value: weather.wind_speed != null ? `${Math.round(weather.wind_speed)} m/s` : "—" },
          { label: "Visibility", value: weather.visibility != null ? `${weather.visibility} km` : "—" },
        ].map((m) => (
          <div key={m.label} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-2">
            <div className="text-[9px] uppercase tracking-wider text-gray-500">{m.label}</div>
            <div className="text-sm font-bold text-gray-800">{m.value}</div>
          </div>
        ))}
      </div>

      <p className="mt-3 text-[10px] leading-snug text-gray-500">
        <span className={`font-bold ${riskColor(weather.weather_risk_label)}`}>{weather.weather_risk_label} risk:</span>{" "}
        {weather.risk_reason}. Weather acts as a risk factor on the forecast — it is not treated as a
        deterministic cause of delay.
      </p>
    </section>
  );
}

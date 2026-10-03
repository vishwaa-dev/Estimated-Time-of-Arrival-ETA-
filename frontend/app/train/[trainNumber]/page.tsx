"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import type { PredictionPayload, WeatherPayload, EventItem } from "@/types";
import MetricCards from "@/components/MetricCards";
import DelayTrajectoryChart from "@/components/DelayTrajectoryChart";
import FactorPanel from "@/components/FactorPanel";
import ETATrajectoryTable from "@/components/ETATrajectoryTable";
import RecoveryMap from "@/components/RecoveryMap";
import WeatherPanel from "@/components/WeatherPanel";
import EventTimeline from "@/components/EventTimeline";
import LiveUpdateIndicator from "@/components/LiveUpdateIndicator";

export default function TrainDashboard() {
  const params = useParams<{ trainNumber: string }>();
  const trainNumber = params.trainNumber;

  const prediction = usePolling(() => api.prediction(trainNumber), 15000);
  const weather = usePolling(() => api.weather(trainNumber), 30000);
  const events = usePolling(() => api.events(trainNumber, 15), 30000);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const act = async (fn: () => Promise<PredictionPayload>, doneMessage?: string) => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await fn();
      setToast(result.message ?? doneMessage ?? "Prediction recalculated");
      await Promise.all([prediction.refresh(), events.refresh(), weather.refresh()]);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setTimeout(() => setToast(null), 4000);
    }
  };

  const data = prediction.data;
  const w = weather.data;
  const ev = events.data?.events ?? [];
  const messages = data?.messages ?? [];
  const mode = data?.data_mode ?? "DEMO";
  const simulated = data?.simulated ?? false;
  const liveOn = data?.live_enabled ?? false;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="panel flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <Link href="/" className="mt-1 text-gray-400 hover:text-gray-600" aria-label="Back">←</Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-mono text-2xl font-bold text-blue-700">{trainNumber}</h1>
              <h2 className="text-lg font-semibold text-gray-900">{data?.train_name ?? "Loading…"}</h2>
              {!simulated && mode === "LIVE" && (
                <span className="badge border border-green-300 bg-green-100 text-green-700">● LIVE DATA</span>
              )}
            </div>
            <p className="mt-0.5 text-sm text-gray-600">
              {data?.current_state.location ?? "—"} · {data?.current_state.status ?? "—"}
              {data?.current_state.current_speed_kmph != null && (
                <> · {Math.round(data.current_state.current_speed_kmph)} km/h</>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex flex-col gap-2">
            <button
              disabled={busy}
              onClick={() => act(() => api.setLive(trainNumber, !liveOn))}
              className={`btn disabled:opacity-40 ${
                liveOn
                  ? "border border-green-500 bg-green-50 text-green-700 hover:bg-green-100"
                  : "border border-gray-300 bg-white text-gray-700 hover:border-green-500 hover:text-green-700"
              }`}
              title="Only trains with LIVE ON are refreshed from RailRadar by the scheduler"
            >
              {liveOn ? "● LIVE TRACKING: ON" : "○ LIVE TRACKING: OFF"}
            </button>
            <button
              disabled={busy}
              onClick={() => act(() => api.refresh(trainNumber), "Live check complete")}
              className="btn border border-sky-500 bg-sky-50 text-sky-700 hover:bg-sky-100 disabled:opacity-40"
              title="Force one live fetch from RailRadar now (spends 1 API call)"
            >
              ⇡ Check live
            </button>
          </div>
          <LiveUpdateIndicator
            updatedAt={data?.last_state_update ?? data?.updated_at ?? null}
            nextRefresh={data?.next_refresh_at ?? null}
            degraded={messages.length > 0}
          />
        </div>
      </div>

      {messages.length > 0 && (
        <div className="panel border-amber-300 bg-amber-50 p-3 text-xs text-amber-700">
          ⚠ {messages.join(" · ")}
        </div>
      )}
      {data && data.forecast_available === false && (
        <div className="panel border-gray-300 bg-gray-50 p-3 text-xs text-gray-600">
          This train is idle — the numbers below are its last real snapshot, not a
          forecast. Toggle <span className="font-semibold">LIVE TRACKING</span> on, or
          press <span className="font-semibold">⇡ Check live</span> for a one-off fetch,
          and the forecast engine takes over.
        </div>
      )}
      {prediction.error && (
        <div className="panel border-red-300 bg-red-50 p-3 text-xs text-red-700">
          Backend unreachable — {prediction.error}. The dashboard will retry automatically.
        </div>
      )}

      {/* Core metrics */}
      {data && <MetricCards data={data} />}

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        {/* Delay trajectory chart */}
        {data && (
          <div className="space-y-5">
            <DelayTrajectoryChart trajectory={data.trajectory} />
            <ETATrajectoryTable trajectory={data.trajectory} />
            <RecoveryMap sections={data.recovery_map} summary={data.recovery_summary} />
          </div>
        )}

        {/* Right column */}
        <div className="space-y-5">
          {data && <FactorPanel factors={data.factors} />}
          {w && <WeatherPanel weather={w} />}
          <EventTimeline events={ev} />
        </div>
      </div>

      {busy && <div className="fixed bottom-4 right-4 rounded-md border border-gray-300 bg-white px-4 py-2 text-xs text-gray-700 shadow-lg">Recalculating…</div>}
      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-gray-300 bg-white px-4 py-2 text-xs font-semibold text-gray-800 shadow-lg">
          ✓ {toast}
        </div>
      )}
      {actionError && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-red-300 bg-white px-4 py-2 text-xs text-red-600 shadow-lg">
          {actionError}
        </div>
      )}
    </div>
  );
}

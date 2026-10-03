"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { fmtAgo, fmtDelay } from "@/lib/format";
import type { TrainCard } from "@/types";

function StatusDot({ status }: { status: string }) {
  const running = status === "running";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs capitalize">
      <span className={`h-2 w-2 rounded-full ${running ? "bg-green-500 animate-pulse" : status === "not-started" ? "bg-gray-400" : "bg-amber-500"}`} />
      {status.replace("-", " ")}
    </span>
  );
}

export default function HomePage() {
  const [query, setQuery] = useState("");

  const { data, error, loading, refresh } = usePolling(async () => {
    if (!query) {
      const all = await api.listTrains();
      return all.trains;
    }
    const res = await api.searchTrains({ q: query });
    return res.trains;
  }, 20000);

  const trains = useMemo(() => data ?? [], [data]);

  // Re-fetch immediately (debounced) whenever the search query changes,
  // instead of waiting up to 20s for the next polling tick.
  useEffect(() => {
    const id = setTimeout(() => refresh(), 400);
    return () => clearTimeout(id);
  }, [query, refresh]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <section className="panel px-6 py-6">
        <h1 className="text-lg font-bold text-gray-900">
          Train ETA forecasting
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          Tracks train delays and predicts final arrival times — recalculated
          continuously from the train&apos;s state, its schedule and the weather
          along the route.
        </p>
      </section>

      {/* Search */}
      <section className="panel p-5">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by train number or name — try 12637"
          className="w-full rounded-md border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-blue-500"
        />
      </section>

      {/* Results */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="panel-title">Tracked trains {query ? `matching “${query}”` : ""}</h2>
          <span className="text-xs text-gray-500">{trains.length} train(s)</span>
        </div>

        {error && (
          <div className="panel border-red-300 bg-red-50 p-4 text-sm text-red-700">
            Backend unreachable — {error}. Is the FastAPI server running on port 8000?
          </div>
        )}
        {loading && !trains.length && (
          <div className="panel p-8 text-center text-sm text-gray-500">Loading trains…</div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          {trains.map((t) => (
            <TrainCardView key={t.train_number} train={t} onChanged={refresh} />
          ))}
        </div>
      </section>
    </div>
  );
}

function TrainCardView({ train, onChanged }: { train: TrainCard; onChanged: () => void }) {
  const [live, setLive] = useState(train.live_enabled);
  const [busy, setBusy] = useState(false);

  const toggleLive = async () => {
    setBusy(true);
    try {
      await api.setLive(train.train_number, !live);
      setLive(!live);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel group p-5 transition-transform hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xl font-bold text-blue-700">{train.train_number}</span>
            <span className="text-base font-semibold text-gray-900">{train.train_name}</span>
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {train.source_name} <span className="text-sky-600">→</span> {train.destination_name}
          </p>
        </div>
        {train.data_mode === "LIVE" && !train.simulated && (
          <span className="badge border border-green-300 bg-green-100 text-green-700">LIVE</span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-md border border-gray-200 bg-gray-50 px-2 py-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Current delay</div>
          <div className={`text-lg font-bold ${train.current_delay_minutes > 5 ? "text-red-600" : train.current_delay_minutes > 0 ? "text-amber-600" : "text-green-600"}`}>
            {fmtDelay(train.current_delay_minutes)}
          </div>
        </div>
        <div className="rounded-md border border-gray-200 bg-gray-50 px-2 py-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Status</div>
          <div className="mt-1.5 flex justify-center"><StatusDot status={train.status} /></div>
        </div>
        <div className="rounded-md border border-gray-200 bg-gray-50 px-2 py-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Updated</div>
          <div className="mt-1.5 text-xs text-gray-700">{fmtAgo(train.last_updated)}</div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="truncate text-xs text-gray-500">{train.location ?? "Position pending"}</p>
        <button
          onClick={toggleLive}
          disabled={busy}
          title={live ? "Pause live tracking" : "Track this train with LIVE RailRadar data (uses API quota)"}
          className={`btn shrink-0 disabled:opacity-40 ${
            live
              ? "border border-green-500 bg-green-50 text-green-700 hover:bg-green-100"
              : "border border-gray-300 bg-white text-gray-500 hover:border-green-500 hover:text-green-700"
          }`}
        >
          {live ? "● LIVE ON" : "○ GO LIVE"}
        </button>
      </div>

      <Link
        href={`/train/${train.train_number}`}
        className="btn mt-4 w-full border border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100 hover:text-gray-900"
      >
        View ETA →
      </Link>
    </div>
  );
}


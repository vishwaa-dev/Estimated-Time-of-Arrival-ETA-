export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

import type {
  EventItem,
  PredictionPayload,
  TrainCard,
  WeatherPayload,
} from "@/types";

export const api = {
  listTrains: () => get<{ trains: TrainCard[] }>("/api/trains"),
  searchTrains: (params: { q?: string }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    return get<{ trains: TrainCard[]; count: number }>(`/api/trains/search?${qs.toString()}`);
  },

  prediction: (n: string) => get<PredictionPayload>(`/api/trains/${n}/prediction`),
  weather: (n: string) => get<WeatherPayload>(`/api/trains/${n}/weather`),
  events: (n: string, limit = 20) =>
    get<{ train_number: string; events: EventItem[] }>(`/api/trains/${n}/events?limit=${limit}`),

  refresh: (n: string) => post<PredictionPayload>(`/api/trains/${n}/refresh`),
  setLive: (n: string, enabled: boolean) =>
    post<PredictionPayload>(`/api/trains/${n}/live`, { enabled }),
};

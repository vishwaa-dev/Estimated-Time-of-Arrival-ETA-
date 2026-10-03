"""RailRadar API client — the ONLY place in the system that talks to RailRadar.

API-economy protections (the key has limited quota):
  1. In-memory TTL cache per train.
  2. Persistent cache in the `api_cache` table (survives restarts).
  3. Hourly call budget (settings.railradar_max_calls_per_hour).
  4. Failures raise ExternalAPIError; callers fall back to the last snapshot.
"""
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiCache
from app.utils.timeutil import parse_iso, utcnow


class ExternalAPIError(Exception):
    """Raised when an external API call fails or is rate-limited."""


@dataclass
class FetchResult:
    payload: dict
    source: str            # LIVE | CACHED
    fetched_at: datetime
    message: str | None = None


class RateLimiter:
    """Sliding-window call budget shared across the process."""

    def __init__(self, max_calls: int, window_seconds: int = 3600):
        self.max_calls = max_calls
        self.window = window_seconds
        self.calls: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self.calls = [t for t in self.calls if now - t < self.window]
            if len(self.calls) >= self.max_calls:
                return False
            self.calls.append(now)
            return True


_memory_cache: dict[str, tuple[float, dict]] = {}
_memory_lock = threading.Lock()
_limiter = RateLimiter(settings.railradar_max_calls_per_hour)


def _cache_get(key: str, ttl: int) -> dict | None:
    now = time.monotonic()
    with _memory_lock:
        hit = _memory_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    return None


def _cache_put(key: str, payload: dict) -> None:
    with _memory_lock:
        _memory_cache[key] = (time.monotonic(), payload)


def fetch_train_live(
    db: Session,
    train_number: str,
    force: bool = False,
    ttl_seconds: int | None = None,
) -> FetchResult:
    """Fetch live status for a train, honouring cache/TTL and call budget.

    Raises ExternalAPIError only when no usable payload (live or cached) exists.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.train_cache_ttl_seconds
    cache_key = f"railradar:train:{train_number}"

    if not force:
        cached = _cache_get(cache_key, ttl)
        if cached is not None:
            return FetchResult(cached, "CACHED", parse_iso(cached.get("_fetched_at")) or utcnow())

    if not settings.railradar_configured:
        raise ExternalAPIError("RailRadar API key is not configured.")

    if not _limiter.allow():
        raise ExternalAPIError("RailRadar hourly call budget exhausted — using cached data.")

    url = f"{settings.railradar_base_url.rstrip('/')}/trains/{train_number}/live"
    headers = {"Authorization": f"Bearer {settings.railradar_api_key}"}
    try:
        response = httpx.get(url, headers=headers, timeout=15.0)
    except httpx.HTTPError as exc:
        raise ExternalAPIError(f"RailRadar unreachable: {exc.__class__.__name__}") from exc

    if response.status_code == 429:
        raise ExternalAPIError("RailRadar rate limit hit (429) — using cached data.")
    if response.status_code in (401, 403):
        raise ExternalAPIError("RailRadar rejected the API key (401/403).")
    if response.status_code != 200:
        raise ExternalAPIError(f"RailRadar returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalAPIError("RailRadar returned malformed JSON.") from exc

    if payload.get("success") is False or not isinstance(payload.get("data"), dict):
        message = payload.get("message") or "RailRadar reported failure."
        raise ExternalAPIError(f"RailRadar error: {message}")

    payload.setdefault("_fetched_at", utcnow().isoformat())
    _cache_put(cache_key, payload)

    row = db.query(ApiCache).filter(ApiCache.cache_key == cache_key).first()
    if row is None:
        row = ApiCache(cache_key=cache_key)
        db.add(row)
    row.payload = payload
    row.fetched_at = utcnow()
    db.commit()

    return FetchResult(payload, "LIVE", parse_iso(payload.get("_fetched_at")) or utcnow())


def fetch_cached_only(db: Session, train_number: str) -> FetchResult | None:
    """Last good RailRadar payload from the persistent cache, if any."""
    cache_key = f"railradar:train:{train_number}"
    cached = _cache_get(cache_key, ttl=10**9)
    if cached:
        return FetchResult(cached, "CACHED", parse_iso(cached.get("_fetched_at")) or utcnow())
    row = db.query(ApiCache).filter(ApiCache.cache_key == cache_key).first()
    if row and isinstance(row.payload, dict):
        return FetchResult(row.payload, "CACHED", row.fetched_at)
    return None

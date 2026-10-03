"""Weather service (OpenWeather) + weather risk scoring.

Weather is a RISK input to the prediction engine — the prototype never claims
"X mm of rain causes Y minutes of delay"; it maps conditions to a 0-100 risk
score with a documented heuristic and explains it qualitatively.

Caching: weather is cached per rounded coordinate with its own TTL
(settings.weather_cache_ttl_seconds) and persisted in api_cache.
"""
import threading
import time
from dataclasses import dataclass, asdict

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import WeatherSnapshot
from app.services.railradar_service import ExternalAPIError
from app.utils.timeutil import utcnow

_memory_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


@dataclass
class WeatherResult:
    location: str | None
    temperature: float | None
    rainfall: float | None
    precipitation_probability: float | None
    wind_speed: float | None
    visibility: float | None
    weather_condition: str | None
    weather_risk_score: float
    weather_risk_label: str
    risk_reason: str
    is_simulated: bool
    source: str  # LIVE / CACHED / SIMULATED / UNAVAILABLE
    observed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- scenarios
WEATHER_SCENARIOS: dict[str, dict] = {
    "normal": dict(
        weather_condition="Clear Sky", temperature=31.0, rainfall=0.0,
        precipitation_probability=5.0, wind_speed=2.5, visibility=10.0,
    ),
    "light_rain": dict(
        weather_condition="Light Rain", temperature=28.0, rainfall=2.5,
        precipitation_probability=65.0, wind_speed=4.5, visibility=8.0,
    ),
    "heavy_rain": dict(
        weather_condition="Heavy Rain", temperature=25.0, rainfall=22.0,
        precipitation_probability=92.0, wind_speed=9.0, visibility=3.0,
    ),
    "severe": dict(
        weather_condition="Thunderstorm", temperature=24.0, rainfall=48.0,
        precipitation_probability=100.0, wind_speed=16.0, visibility=1.2,
    ),
}


def score_weather(
    condition: str | None,
    rainfall: float | None,
    wind_speed: float | None,
    visibility: float | None,
    precipitation_probability: float | None,
) -> tuple[float, str, str]:
    """Deterministic 0-100 weather risk score. Documented heuristic:

    base by condition family (Clear/Clouds ~10, Drizzle ~35, Rain ~55,
    Heavy rain ~80, Thunderstorm ~90, Snow ~70)
      + rainfall bonus  (min(30, mm*4) when measured rainfall exists)
      + wind bonus      (+15 if >10 m/s, +8 if >7 m/s)
      + visibility      (+20 if <2 km, +10 if <4 km)
    Label bands: <15 NORMAL, <35 LOW, <60 MEDIUM, <80 HIGH, else VERY HIGH.
    """
    cond = (condition or "").lower()
    score = 10.0
    if "thunder" in cond or "storm" in cond:
        score = 90.0
    elif "heavy" in cond and "rain" in cond:
        score = 80.0
    elif "rain" in cond or "shower" in cond:
        score = 45.0
    elif "drizzle" in cond:
        score = 30.0
    elif "snow" in cond or "sleet" in cond:
        score = 70.0
    elif "cloud" in cond or "overcast" in cond:
        score = 18.0
    elif "mist" in cond or "fog" in cond or "haze" in cond:
        score = 45.0

    if rainfall:
        score += min(30.0, rainfall * 4.0)
    if wind_speed is not None and wind_speed > 10:
        score += 15.0
    elif wind_speed is not None and wind_speed > 7:
        score += 8.0
    if visibility is not None and visibility < 2:
        score += 20.0
    elif visibility is not None and visibility < 4:
        score += 10.0
    if precipitation_probability is not None and precipitation_probability >= 70 and score < 55:
        score = max(score, 50.0)

    score = max(0.0, min(100.0, score))
    label = ("NORMAL" if score < 15 else "LOW" if score < 35 else
             "MEDIUM" if score < 60 else "HIGH" if score < 80 else "VERY HIGH")

    reasons: list[str] = []
    if rainfall and rainfall >= 15:
        reasons.append("heavy precipitation in the current/upcoming section")
    elif rainfall and rainfall > 0:
        reasons.append("light precipitation in the area")
    if wind_speed is not None and wind_speed > 10:
        reasons.append("strong winds")
    if visibility is not None and visibility < 4:
        reasons.append("reduced visibility")
    if not reasons:
        reasons.append("no significant weather stress")
    return round(score, 1), label, "; ".join(reasons).capitalize()


def _round_coord(lat: float, lng: float) -> str:
    return f"{round(lat, 2)},{round(lng, 2)}"


def _cache_get(key: str, ttl: int) -> dict | None:
    now = time.monotonic()
    with _lock:
        hit = _memory_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    return None


def _cache_put(key: str, payload: dict) -> None:
    with _lock:
        _memory_cache[key] = (time.monotonic(), payload)


def _simulate(scenario_key: str, location: str | None) -> WeatherResult:
    preset = WEATHER_SCENARIOS.get(scenario_key, WEATHER_SCENARIOS["normal"])
    score, label, reason = score_weather(
        preset["weather_condition"], preset["rainfall"], preset["wind_speed"],
        preset["visibility"], preset["precipitation_probability"],
    )
    return WeatherResult(
        location=location, **preset,
        weather_risk_score=score, weather_risk_label=label, risk_reason=reason,
        is_simulated=True, source="SIMULATED", observed_at=utcnow().isoformat(),
    )


def get_weather(
    db: Session,
    train_id: int,
    lat: float | None,
    lng: float | None,
    location: str | None = None,
    weather_mode: str = "stored",  # live | demo | stored
    persist: bool = True,
) -> WeatherResult:
    """Weather for the train's current location.

    Priority: explicit demo baseline (DEMO trains) > OpenWeather live
    (TTL-cached, LIVE trains) > last stored snapshot (IDLE / fallback) >
    unavailable-but-neutral placeholder.
    """
    if weather_mode == "demo":
        return _simulate("normal", location)

    if weather_mode != "live" or lat is None or lng is None or not settings.weather_configured:
        return _last_snapshot_or_unavailable(db, train_id, location)

    coord_key = _round_coord(lat, lng)
    cache_key = f"weather:{coord_key}"
    ttl = settings.weather_cache_ttl_seconds

    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return _result_from_payload(cached, "CACHED")

    try:
        response = httpx.get(
            f"{settings.weather_base_url.rstrip('/')}/weather",
            params={"lat": lat, "lon": lng, "units": "metric", "appid": settings.weather_api_key},
            timeout=12.0,
        )
        if response.status_code != 200:
            raise ExternalAPIError(f"Weather API HTTP {response.status_code}")
        payload = response.json()
    except (httpx.HTTPError, ValueError, ExternalAPIError):
        return _last_snapshot_or_unavailable(db, train_id, location)

    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    rain = payload.get("rain") or {}
    condition = weather.get("main") or weather.get("description")
    rainfall = _f(rain.get("1h")) or 0.0
    visibility_km = _f(payload.get("visibility")) / 1000.0 if payload.get("visibility") else None
    # Current-weather payload has no probability-of-precipitation; approximate
    # from rain presence + cloud cover (documented approximation).
    clouds = _f((payload.get("clouds") or {}).get("all"))
    pop = 85.0 if rainfall > 0 else (max(30.0, (clouds or 0) * 0.6) if clouds else 10.0)

    result_payload = {
        "location": location, "temperature": _f(main.get("temp")),
        "rainfall": rainfall, "precipitation_probability": pop,
        "wind_speed": _f(wind.get("speed")), "visibility": visibility_km,
        "weather_condition": condition,
        "observed_at": utcnow().isoformat(),
    }
    score, label, reason = score_weather(
        condition, rainfall, result_payload["wind_speed"], visibility_km, pop,
    )
    result_payload.update({"weather_risk_score": score, "weather_risk_label": label, "risk_reason": reason})

    _cache_put(cache_key, result_payload)

    if persist:
        db.add(
            WeatherSnapshot(
                train_id=train_id, timestamp=utcnow(), **{
                    k: result_payload.get(k) for k in (
                        "location", "temperature", "rainfall", "precipitation_probability",
                        "wind_speed", "visibility", "weather_condition",
                        "weather_risk_score", "weather_risk_label",
                    )
                },
                is_simulated=False,
            )
        )
    return _result_from_payload(result_payload, "LIVE")


def _f(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _result_from_payload(payload: dict, source: str) -> WeatherResult:
    return WeatherResult(
        location=payload.get("location"),
        temperature=payload.get("temperature"),
        rainfall=payload.get("rainfall"),
        precipitation_probability=payload.get("precipitation_probability"),
        wind_speed=payload.get("wind_speed"),
        visibility=payload.get("visibility"),
        weather_condition=payload.get("weather_condition"),
        weather_risk_score=payload.get("weather_risk_score") or 0.0,
        weather_risk_label=payload.get("weather_risk_label") or "UNKNOWN",
        risk_reason=payload.get("risk_reason") or "",
        is_simulated=False,
        source=source,
        observed_at=payload.get("observed_at"),
    )


def _last_snapshot_or_unavailable(db: Session, train_id: int, location: str | None) -> WeatherResult:
    snap = (
        db.query(WeatherSnapshot)
        .filter(WeatherSnapshot.train_id == train_id)
        .order_by(WeatherSnapshot.timestamp.desc())
        .first()
    )
    if snap:
        return WeatherResult(
            location=snap.location or location, temperature=snap.temperature,
            rainfall=snap.rainfall, precipitation_probability=snap.precipitation_probability,
            wind_speed=snap.wind_speed, visibility=snap.visibility,
            weather_condition=snap.weather_condition,
            weather_risk_score=snap.weather_risk_score or 0.0,
            weather_risk_label=snap.weather_risk_label or "UNKNOWN",
            risk_reason="last cached weather observation",
            is_simulated=snap.is_simulated,
            source="CACHED",
            observed_at=snap.timestamp.isoformat() if snap.timestamp else None,
        )
    return WeatherResult(
        location=location, temperature=None, rainfall=None,
        precipitation_probability=None, wind_speed=None, visibility=None,
        weather_condition="Unavailable",
        weather_risk_score=0.0, weather_risk_label="NO DATA",
        risk_reason="weather data unavailable — prediction continues without weather stress",
        is_simulated=False, source="UNAVAILABLE", observed_at=None,
    )

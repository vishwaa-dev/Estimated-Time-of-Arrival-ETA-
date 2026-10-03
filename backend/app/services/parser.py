"""Robust parser for RailRadar train payloads and the provided train JSON files.

Design rules (per project brief):
- Never crash on missing actual arrival/departure, speed, delay, or upcoming
  station timing — every field is optional and normalised.
- Accepts the full RailRadar envelope {success, data, meta}, the inner `data`
  object directly, or a raw train dict.
"""
from dataclasses import dataclass, field
from datetime import datetime

from app.utils.timeutil import parse_iso


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    f = _as_float(value)
    return int(f) if f is not None else None


def _as_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class ParsedRoutePoint:
    sequence: int
    station_code: str
    station_name: str
    is_halt: bool
    status: str | None = None
    scheduled_arrival: datetime | None = None
    scheduled_departure: datetime | None = None
    actual_arrival: datetime | None = None
    actual_departure: datetime | None = None
    delay_arrival: float | None = None
    delay_departure: float | None = None
    distance_km: float | None = None
    platform: str | None = None
    speed_to_next_kmph: float | None = None


@dataclass
class ParsedTrain:
    train_number: str
    train_name: str
    category: str | None = None
    source_code: str | None = None
    source_name: str | None = None
    source_coords: tuple[float, float] | None = None
    destination_code: str | None = None
    destination_name: str | None = None
    destination_coords: tuple[float, float] | None = None
    run_days: str | None = None
    scheduled_distance_km: float | None = None
    scheduled_duration_minutes: int | None = None
    total_halts: int | None = None
    status: str = "unknown"          # not-started / running / reached / unknown
    is_live: bool = False
    last_updated: datetime | None = None
    current_delay_minutes: float = 0.0
    current_speed_kmph: float | None = None
    current_station_code: str | None = None
    current_station_name: str | None = None
    current_sequence: int | None = None
    current_location_note: str | None = None
    route: list[ParsedRoutePoint] = field(default_factory=list)


def _unwrap(payload: dict) -> dict:
    """Accept {success, data}, {data}, or a bare train dict."""
    if not isinstance(payload, dict):
        return {}
    if "data" in payload and isinstance(payload["data"], dict):
        return payload["data"]
    return payload


def _coords(station: dict) -> tuple[float, float] | None:
    if not isinstance(station, dict):
        return None
    lat, lng = _as_float(station.get("lat")), _as_float(station.get("lng"))
    if lat is None or lng is None:
        return None
    return (lat, lng)


def _normalize_status(raw: str | None) -> str:
    text = (raw or "").strip().lower().replace("_", "-")
    if text in {"not-started", "notstarted"}:
        return "not-started"
    if text in {"reached", "arrived", "destination-reached"}:
        return "reached"
    if text in {"running", "live", "moving", "at-station", "delayed"}:
        return "running"
    return "unknown"


def parse_train_payload(payload: dict) -> ParsedTrain:
    data = _unwrap(payload)
    train = data.get("train") if isinstance(data.get("train"), dict) else data

    parsed = ParsedTrain(
        train_number=_as_str(train.get("number") or data.get("trainNumber")) or "unknown",
        train_name=_as_str(train.get("name") or data.get("trainName")) or "Unknown Train",
        category=_as_str(train.get("category") or data.get("category")),
        scheduled_distance_km=_as_float(train.get("distance") or data.get("distance")),
        scheduled_duration_minutes=_as_int(train.get("duration") or data.get("duration")),
        total_halts=_as_int(train.get("totalHalts") or data.get("totalHalts")),
        status=_normalize_status(data.get("status") or train.get("status")),
        is_live=bool(data.get("isLive", False)),
        last_updated=parse_iso(data.get("lastUpdatedAt") or data.get("lastUpdated")),
    )

    for side, key in (("source", "source"), ("destination", "destination")):
        st = train.get(key) or {}
        parsed.__setattr__(f"{side}_code", _as_str(st.get("code")))
        parsed.__setattr__(f"{side}_name", _as_str(st.get("name")))
        parsed.__setattr__(f"{side}_coords", _coords(st))
    run_days = train.get("runDays")
    parsed.run_days = ",".join(run_days) if isinstance(run_days, list) else _as_str(run_days)

    # ---- Route (94 items for 12637: halts + non-halt waypoints) ----
    raw_route = data.get("route") if isinstance(data.get("route"), list) else []
    for item in raw_route:
        if not isinstance(item, dict):
            continue
        seq = _as_int(item.get("sequence"))
        if seq is None:
            continue
        parsed.route.append(
            ParsedRoutePoint(
                sequence=seq,
                station_code=_as_str(item.get("stationCode")) or f"SEQ{seq}",
                station_name=_as_str(item.get("stationName")) or _as_str(item.get("stationCode")) or f"Point {seq}",
                is_halt=bool(item.get("isHalt", False)),
                status=_as_str(item.get("status")),
                scheduled_arrival=parse_iso(item.get("scheduledArrival")),
                scheduled_departure=parse_iso(item.get("scheduledDeparture")),
                actual_arrival=parse_iso(item.get("actualArrival")),
                actual_departure=parse_iso(item.get("actualDeparture")),
                delay_arrival=_as_float(item.get("delayArrival")),
                delay_departure=_as_float(item.get("delayDeparture")),
                distance_km=_as_float(item.get("distance")),
                platform=_as_str(item.get("platform")),
                speed_to_next_kmph=_as_float(item.get("speedToNextStationKmph")),
            )
        )
    parsed.route.sort(key=lambda p: p.sequence)

    # ---- Current location / delay / speed ----
    loc = data.get("currentLocation") if isinstance(data.get("currentLocation"), dict) else {}
    parsed.current_station_code = _as_str(loc.get("stationCode"))
    parsed.current_station_name = _as_str(loc.get("stationName"))
    parsed.current_sequence = _as_int(loc.get("sequence"))
    if parsed.current_sequence is None and parsed.route:
        parsed.current_sequence = 1

    delay = _as_float(data.get("delayMinutes"))
    if delay is None:
        # Fall back to the most recent known delay on the route
        known = [p.delay_departure for p in parsed.route if p.delay_departure is not None]
        delay = known[-1] if known else 0.0
    parsed.current_delay_minutes = max(0.0, delay)

    # Speed: prefer the current point's "speed to next station", else the
    # latest known value behind the train.
    speed = _as_float(loc.get("speedToNextStationKmph") or data.get("speed"))
    if speed is None:
        anchor_seq = parsed.current_sequence or 0
        for point in reversed(parsed.route):
            if point.sequence <= anchor_seq and point.speed_to_next_kmph is not None:
                speed = point.speed_to_next_kmph
                break
    if speed is None:
        for point in reversed(parsed.route):
            if point.speed_to_next_kmph is not None:
                speed = point.speed_to_next_kmph
                break
    parsed.current_speed_kmph = speed

    if parsed.current_station_name:
        note = _as_str(loc.get("distanceFromLastStationKm"))
        if note and _as_float(note) not in (None, 0.0):
            parsed.current_location_note = f"{parsed.current_station_name} + {note} km"
        else:
            parsed.current_location_note = parsed.current_station_name

    return parsed

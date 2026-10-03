"""Continuous re-forecast pipeline (the mandated workflow):

    fetch state -> parse -> snapshot -> locate -> weather (if cache expired)
    -> features -> prediction -> recovery -> ETA -> confidence -> explanation
    -> persist -> dashboard refresh (frontend polls the backend)

The frontend NEVER calls external APIs; it polls this backend, which alone
decides when to spend a RailRadar/Weather call (TTL + hourly budget).
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RoutePoint, Train, TrainStateSnapshot
from app.services import simulation_service
from app.services.event_service import add_event
from app.services.parser import parse_train_payload
from app.services.prediction_service import run_prediction
from app.services.railradar_service import ExternalAPIError, fetch_cached_only, fetch_train_live
from app.services.weather_service import get_weather
from app.utils.timeutil import aware_utc, to_utc, utcnow

logger = logging.getLogger("railcast.refresh")

_last_refresh: dict[int, object] = {}  # train_id -> datetime of last live refresh
_tick_counter: dict[int, int] = {}

# Idle trains may serve a forecast from a recent *live* snapshot (e.g. right
# after a manual "Check live"), but never from stale data.
FORECAST_MAX_AGE_MINUTES = 60


def should_forecast(train: Train, snapshot: TrainStateSnapshot | None, mode: str) -> bool:
    """A forecast is honest only when its input data is alive: LIVE trains and
    the demo train always forecast; idle trains only from a live/cached
    snapshot younger than FORECAST_MAX_AGE_MINUTES."""
    if mode in ("LIVE", "DEMO"):
        return True
    if snapshot is None or snapshot.data_source not in ("LIVE", "CACHED"):
        return False
    ts = aware_utc(snapshot.timestamp)
    if ts is None:
        return False
    age_min = (utcnow() - ts).total_seconds() / 60.0
    return age_min <= FORECAST_MAX_AGE_MINUTES


def effective_mode(db: Session, train: Train) -> str:
    return simulation_service._train_mode(db, train)


def _current_coords(db: Session, train: Train, snapshot: TrainStateSnapshot | None):
    if snapshot is None:
        return None, None
    point = (
        db.query(RoutePoint)
        .filter(RoutePoint.train_id == train.id)
        .filter(RoutePoint.station_code == snapshot.current_station)
        .order_by(RoutePoint.sequence.desc())
        .first()
    ) or (
        db.query(RoutePoint)
        .filter(RoutePoint.train_id == train.id, RoutePoint.sequence <= (snapshot.current_sequence or 0))
        .order_by(RoutePoint.sequence.desc())
        .first()
    )
    return (point.latitude, point.longitude) if point else (None, None)


def _apply_live_payload(db: Session, train: Train, payload: dict, source: str) -> TrainStateSnapshot:
    parsed = parse_train_payload(payload)
    now = utcnow()

    train.status = parsed.status
    train.updated_at = now

    # Map the live payload onto OUR seeded route. RailRadar numbers stations
    # across its full waypoint route (hundreds of items), while a seeded route
    # may contain only the major halts (sequences 1..6) — so match by station
    # CODE, never by raw sequence number.
    ours_by_code = {p.station_code: p for p in train.route_points}
    loc_seq = parsed.current_sequence or 0

    for rp in parsed.route:
        if loc_seq and rp.sequence is not None and rp.sequence > loc_seq:
            continue  # only the part of the journey already travelled
        point = ours_by_code.get(rp.station_code)
        if point is None:
            continue
        if rp.actual_arrival and not point.actual_arrival:
            point.actual_arrival = to_utc(rp.actual_arrival)
        if rp.actual_departure and not point.actual_departure:
            point.actual_departure = to_utc(rp.actual_departure)
        if rp.delay_arrival is not None:
            point.delay_arrival = rp.delay_arrival
        if rp.delay_departure is not None:
            point.delay_departure = rp.delay_departure

    # Anchor = the halt the train is at / last passed, expressed in OUR route's
    # sequence space, so the prediction engine sees the correct upcoming halts.
    anchor = ours_by_code.get(parsed.current_station_code or "")
    if anchor is None:
        for rp in reversed(parsed.route):
            if (
                rp.is_halt
                and rp.sequence is not None
                and loc_seq
                and rp.sequence <= loc_seq
                and rp.station_code in ours_by_code
            ):
                anchor = ours_by_code[rp.station_code]
                break
    if anchor is None:
        anchor = train.route_points[0] if train.route_points else None

    covered = 0.0
    if anchor is not None and anchor.distance_km is not None:
        covered = anchor.distance_km

    snap = TrainStateSnapshot(
        train_id=train.id, timestamp=to_utc(parsed.last_updated) if parsed.last_updated else now,
        current_station=anchor.station_code if anchor else parsed.current_station_code,
        current_station_name=parsed.current_location_note or parsed.current_station_name,
        current_sequence=anchor.sequence if anchor else parsed.current_sequence,
        current_delay_minutes=parsed.current_delay_minutes,
        current_speed_kmph=parsed.current_speed_kmph,
        status=parsed.status,
        distance_covered_km=covered,
        data_source=source,
    )
    db.add(snap)
    db.commit()
    return snap


def refresh_train(db: Session, train_number: str, force: bool = False) -> dict:
    """Manual or scheduled refresh. External calls are TTL/force guarded."""
    train = db.query(Train).filter(Train.train_number == train_number).first()
    if train is None:
        raise KeyError(train_number)

    mode = effective_mode(db, train)
    messages: list[str] = []
    snapshot = None
    live_source = None

    # A manual (forced) refresh in AUTO mode is an explicit "check live now" —
    # spend one RailRadar call even for IDLE trains. DATA_MODE=DEMO stays a
    # hard zero-call guarantee.
    attempt_live = settings.railradar_configured and (
        mode == "LIVE" or (force and settings.data_mode != "DEMO")
    )

    if attempt_live:
        try:
            fetch = fetch_train_live(db, train_number, force=force)
            snapshot = _apply_live_payload(db, train, fetch.payload, fetch.source)
            live_source = fetch.source
            if fetch.source == "CACHED":
                messages.append("Live source unavailable — displaying last successful update.")
            _last_refresh[train.id] = utcnow()
        except ExternalAPIError as exc:
            messages.append(f"External data temporarily unavailable ({exc}) — showing last valid prediction.")
            add_event(db, train.id, "system", str(exc))
            cached = fetch_cached_only(db, train_number)
            if cached:
                snapshot = _apply_live_payload(db, train, cached.payload, "CACHED")

    if snapshot is not None:
        # Real data path (fresh live fetch or last-good cached payload).
        lat, lng = _current_coords(db, train, snapshot)
        weather = get_weather(
            db, train.id, lat, lng,
            location=snapshot.current_station_name,
            weather_mode="live" if live_source == "LIVE" else "stored",
        )
        result = run_prediction(db, train, weather=weather, snapshot=snapshot)
        add_event(db, train.id, "prediction",
                  f"Prediction recalculated (final delay +{result['prediction']['final_predicted_delay_minutes']} min).")
    elif mode == "DEMO":
        # Designated demo train (or global DEMO mode): advance the simulated
        # journey, then recalculate.
        snapshot = simulation_service.advance_demo(db, train)
        lat, lng = _current_coords(db, train, snapshot or _latest_snapshot(db, train))
        weather = get_weather(
            db, train.id, lat, lng,
            location=(snapshot.current_station_name if snapshot else None),
            weather_mode="demo",
        )
        result = run_prediction(db, train, weather=weather, snapshot=snapshot)
        _tick_counter[train.id] = _tick_counter.get(train.id, 0) + 1
        ticks = _tick_counter[train.id]
        if ticks % 6 == 1:
            add_event(db, train.id, "prediction",
                      f"Prediction recalculated (final delay +{result['prediction']['final_predicted_delay_minutes']} min) — SIMULATED",
                      is_simulated=True)
        if ticks % 6 == 3:
            add_event(db, train.id, "weather",
                      f"Weather refreshed: {getattr(weather, 'weather_condition', 'n/a')} "
                      f"({getattr(weather, 'weather_risk_label', 'n/a')} risk)"
                      + (" — SIMULATED" if getattr(weather, "is_simulated", False) else ""),
                      is_simulated=getattr(weather, "is_simulated", False))
    else:
        # IDLE: a real-data train with nothing new to fetch — recalculate the
        # prediction from the last stored snapshot (no external calls), and
        # forecast only if that snapshot is recent live data.
        snapshot = _latest_snapshot(db, train)
        lat, lng = _current_coords(db, train, snapshot)
        weather = get_weather(
            db, train.id, lat, lng,
            location=(snapshot.current_station_name if snapshot else None),
            weather_mode="stored",
        )
        result = run_prediction(db, train, weather=weather, snapshot=snapshot,
                                persist=False, forecast=should_forecast(train, snapshot, mode))

    result["messages"] = messages
    result["next_refresh_at"] = next_refresh_at(db, train).isoformat()
    return result


def _latest_snapshot(db: Session, train: Train) -> TrainStateSnapshot | None:
    return (
        db.query(TrainStateSnapshot)
        .filter(TrainStateSnapshot.train_id == train.id)
        .order_by(TrainStateSnapshot.timestamp.desc())
        .first()
    )


def next_refresh_at(db: Session, train: Train):
    last = _last_refresh.get(train.id)
    if last is None:
        snap = _latest_snapshot(db, train)
        last = snap.timestamp if snap else utcnow()
        if last.tzinfo is None:
            from app.utils.timeutil import UTC

            last = last.replace(tzinfo=UTC)
    return last + timedelta(seconds=settings.poll_interval_seconds)


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------
async def background_loop(app) -> None:
    """Asyncio task: demo tick / live poll for every tracked train."""
    interval = max(10, min(settings.demo_tick_seconds, settings.poll_interval_seconds))
    logger.info("Background scheduler started (tick=%ss, poll=%ss, demo_scale=%sx)",
                interval, settings.poll_interval_seconds, settings.demo_time_scale)
    while True:
        try:
            await asyncio.sleep(interval)
            _run_cycle(app)
        except asyncio.CancelledError:
            raise
        except Exception:  # never kill the scheduler
            logger.exception("Background refresh cycle failed")


def _run_cycle(app) -> None:
    from app.database import SessionLocal
    from app.services.track_service import scheduler_interval_for

    db = SessionLocal()
    try:
        trains = db.query(Train).all()
        for train in trains:
            try:
                mode = effective_mode(db, train)
                if mode == "LIVE":
                    last = _last_refresh.get(train.id)
                    from app.utils.timeutil import UTC

                    if last and last.tzinfo is None:
                        last = last.replace(tzinfo=UTC)
                    # live-enabled trains poll every interval; trains that are
                    # not actively running back off 3x to protect the quota
                    interval = scheduler_interval_for(db, train)
                    due = last is None or (utcnow() - last).total_seconds() >= interval
                    if due:
                        refresh_train(db, train.train_number, force=False)
                elif mode == "DEMO":
                    refresh_train(db, train.train_number)
                # IDLE trains are left alone: real-data only, updated when the
                # user toggles LIVE or presses refresh.
            except Exception:
                logger.exception("Refresh failed for train %s", train.train_number)
    finally:
        db.close()

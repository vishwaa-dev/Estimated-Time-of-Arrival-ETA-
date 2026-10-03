"""Seeds the SQLite database from the train JSON snapshots in /data.

Idempotent: a train is (re-)seeded only when missing or when its route is
empty. The seed creates:
  - trains + train_route_points rows
  - an initial train_state_snapshot (data_source=SEED)
  - a SimulationState anchor (demo clock starts at the journey's departure)
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import RoutePoint, SimulationState, Train, TrainStateSnapshot
from app.services.event_service import add_event
from app.services.parser import ParsedTrain, parse_train_payload
from app.utils.stations import resolve_coords
from app.utils.timeutil import to_utc, utcnow

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _seed_one(db: Session, payload: dict, source_label: str) -> Train | None:
    parsed: ParsedTrain = parse_train_payload(payload)
    if parsed.train_number == "unknown":
        return None

    train = db.query(Train).filter(Train.train_number == parsed.train_number).first()
    now = utcnow()
    if train is None:
        train = Train(train_number=parsed.train_number, created_at=now)
        db.add(train)

    train.train_name = parsed.train_name
    train.category = parsed.category
    train.source_code, train.source_name = parsed.source_code, parsed.source_name
    train.destination_code, train.destination_name = parsed.destination_code, parsed.destination_name
    train.run_days = parsed.run_days
    train.scheduled_distance_km = parsed.scheduled_distance_km
    train.scheduled_duration_minutes = parsed.scheduled_duration_minutes
    train.total_halts = parsed.total_halts
    train.status = parsed.status
    # Live tracking is opt-in per train; new seeds always start with real-data
    # trains idle (or demo for the designated demo train) until the user
    # flips the LIVE switch.
    train.live_enabled = False
    train.updated_at = now

    if train.id is None:
        db.flush()

    existing_route = db.query(RoutePoint).filter(RoutePoint.train_id == train.id).count()
    if existing_route == 0 and parsed.route:
        coords = resolve_coords(
            [vars(p) for p in parsed.route], parsed.source_coords, parsed.destination_coords
        )
        for point in parsed.route:
            lat, lng = coords.get(point.sequence, (None, None))
            db.add(
                RoutePoint(
                    train_id=train.id,
                    sequence=point.sequence,
                    station_code=point.station_code,
                    station_name=point.station_name,
                    is_halt=point.is_halt,
                    scheduled_arrival=to_utc(point.scheduled_arrival) if point.scheduled_arrival else None,
                    scheduled_departure=to_utc(point.scheduled_departure) if point.scheduled_departure else None,
                    actual_arrival=to_utc(point.actual_arrival) if point.actual_arrival else None,
                    actual_departure=to_utc(point.actual_departure) if point.actual_departure else None,
                    delay_arrival=point.delay_arrival,
                    delay_departure=point.delay_departure,
                    distance_km=point.distance_km,
                    platform=point.platform,
                    speed_to_next_kmph=point.speed_to_next_kmph,
                    latitude=lat,
                    longitude=lng,
                )
            )

    # Initial state snapshot
    if parsed.route:
        current_distance = 0.0
        if parsed.current_sequence:
            anchor = next((p for p in parsed.route if p.sequence == parsed.current_sequence), None)
            current_distance = anchor.distance_km if anchor and anchor.distance_km else 0.0
        db.add(
            TrainStateSnapshot(
                train_id=train.id,
                timestamp=to_utc(parsed.last_updated) if parsed.last_updated else now,
                current_station=parsed.current_station_code,
                current_station_name=parsed.current_location_note or parsed.current_station_name,
                current_sequence=parsed.current_sequence,
                current_delay_minutes=parsed.current_delay_minutes,
                current_speed_kmph=parsed.current_speed_kmph,
                status=parsed.status,
                distance_covered_km=current_distance,
                data_source="SEED",
            )
        )

    # Demo clock: the anchor is set on the first simulation tick, so the
    # journey always starts at its scheduled departure from "now".
    sim = db.query(SimulationState).filter(SimulationState.train_id == train.id).first()
    if sim is None:
        sim = SimulationState(train_id=train.id)
        db.add(sim)
    sim.demo_delay_minutes = 0.0
    sim.demo_last_sim_time = None
    sim.demo_anchor_time = None
    sim.updated_at = now

    add_event(
        db,
        train.id,
        "system",
        f"Route and schedule loaded from {source_label} (snapshot).",
    )
    return train


def seed_all(db: Session) -> list[str]:
    """Seed every train_*.json snapshot in /data. Returns seeded train numbers."""
    seeded: list[str] = []
    if not DATA_DIR.exists():
        return seeded
    for path in sorted(DATA_DIR.glob("train_*.json")):
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        number = _unwrap_number(payload)
        if number and db.query(Train).filter(Train.train_number == number).first():
            continue  # already seeded — never clobber journey history
        train = _seed_one(db, payload, path.name)
        if train:
            seeded.append(train.train_number)
    db.commit()
    return seeded


def _unwrap_number(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else payload
    return str(data.get("trainNumber") or (data.get("train") or {}).get("number") or "") or None


def seed_train_number(db: Session, train_number: str) -> Train | None:
    path = DATA_DIR / f"train_{train_number}.json"
    if not path.exists():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return _seed_one(db, payload, path.name)

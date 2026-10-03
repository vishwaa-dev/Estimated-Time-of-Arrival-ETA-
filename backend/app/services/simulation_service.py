"""Simulation engine — DEMO mode journey.

DEMO journey: a virtual clock replays the seeded schedule at DEMO_TIME_SCALE
(1 real second == DEMO_TIME_SCALE simulated seconds, default 60x). The virtual
delay evolves with mean reversion + small jitter. The train's position at any
moment is derived from (simulated time - delay), i.e. the train runs BEHIND the
timetable by its current delay. Passing a halt writes SIMULATED actual
arrival/departure onto the route points so the observed trajectory works, and
logs a clearly-marked simulated event.

Nothing here is ever presented as real railway data — every artifact is
labelled DEMO/SIMULATED by the API/UI layers.
"""
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RoutePoint, SimulationState, Train, TrainStateSnapshot
from app.services.event_service import add_event
from app.utils.timeutil import utcnow


def get_or_create_state(db: Session, train: Train) -> SimulationState:
    sim = db.query(SimulationState).filter(SimulationState.train_id == train.id).first()
    if sim is None:
        sim = SimulationState(train_id=train.id, updated_at=utcnow())
        db.add(sim)
        db.flush()
    return sim


def compute_demo_clock(sim: SimulationState, train: Train, now: datetime) -> tuple[datetime, bool]:
    """Returns (virtual_train_time, wrapped).

    The virtual clock starts at the journey's first scheduled departure the
    moment the simulation is seeded/reset, then advances at DEMO_TIME_SCALE.
    After arrival + 30 sim-minutes the run loops, so a demo never dead-ends.

    The elapsed virtual time is taken modulo the journey length, so the clock
    always lands inside the current run — even if the backend was stopped for
    days (otherwise one rewind per tick could never catch up and every train
    would permanently sit at "reached").
    """
    route = list(train.route_points)
    first_departure = next((p.scheduled_departure for p in route if p.scheduled_departure), None)
    if first_departure is None:
        return now, False

    anchor = sim.demo_anchor_time
    if anchor is None:
        # first tick after seed/reset: the run starts NOW at the departure
        anchor = now
        sim.demo_anchor_time = anchor
    if anchor.tzinfo is None:
        from app.utils.timeutil import UTC

        anchor = anchor.replace(tzinfo=UTC)
    elapsed_real = (now - anchor).total_seconds()
    elapsed_sim = elapsed_real * settings.demo_time_scale

    halts = [p for p in route if p.is_halt and p.scheduled_arrival is not None]
    final_arrival = halts[-1].scheduled_arrival if halts else None
    loop_end = final_arrival + timedelta(minutes=30) if final_arrival else None
    journey_seconds = (loop_end - first_departure).total_seconds() if loop_end else None
    if not journey_seconds or journey_seconds <= 0:
        return first_departure + timedelta(seconds=elapsed_sim), False

    sim_time = first_departure + timedelta(seconds=elapsed_sim % journey_seconds)
    if loop_end and sim_time > loop_end:
        sim_time = loop_end

    # wrapped when the clock went backwards between ticks (a new run started)
    last = sim.demo_last_sim_time
    if last is not None and last.tzinfo is None:
        from app.utils.timeutil import UTC

        last = last.replace(tzinfo=UTC)
    wrapped = last is not None and sim_time < last
    return sim_time, wrapped


def _clear_demo_actuals(train: Train) -> None:
    for point in train.route_points:
        if point.delay_departure is not None or point.delay_arrival is not None:
            point.actual_arrival = None
            point.actual_departure = None
            point.delay_arrival = None
            point.delay_departure = None


def locate_on_schedule(route_points: list[RoutePoint], train_clock: datetime) -> dict:
    """Where should the train BE at `train_clock` if it ran exactly to
    schedule? Returns position between bounding halts (or not-started /
    reached states)."""
    halts = [p for p in route_points if p.is_halt]
    first = halts[0]
    last = halts[-1]
    first_dep = first.scheduled_departure or first.scheduled_arrival
    last_arr = last.scheduled_arrival

    if first_dep and train_clock < first_dep:
        return {"phase": "not-started", "halt": first, "progress": 0.0, "distance": 0.0,
                "section": None, "speed": first.speed_to_next_kmph}
    if last_arr and train_clock >= last_arr:
        return {"phase": "reached", "halt": last, "progress": 1.0,
                "distance": last.distance_km or 0.0, "section": None, "speed": None}

    for i in range(len(halts) - 1):
        a, b = halts[i], halts[i + 1]
        dep_a = a.scheduled_departure or a.scheduled_arrival
        arr_b = b.scheduled_arrival
        if dep_a is None or arr_b is None or arr_b <= dep_a:
            continue
        if dep_a <= train_clock < arr_b:
            progress = (train_clock - dep_a).total_seconds() / (arr_b - dep_a).total_seconds()
            distance = (a.distance_km or 0.0) + progress * ((b.distance_km or 0.0) - (a.distance_km or 0.0))
            speed = a.speed_to_next_kmph
            if speed is None:
                speed = ((b.distance_km or 0.0) - (a.distance_km or 0.0)) / ((arr_b - dep_a).total_seconds() / 3600.0)
            return {"phase": "running", "halt": a, "next": b, "progress": progress,
                    "distance": distance, "section": (a, b), "speed": speed}
    # fell through (gaps in timetable) — snap to nearest passed halt
    passed = halts[0]
    for point in halts:
        ref = point.scheduled_departure or point.scheduled_arrival
        if ref and ref <= train_clock:
            passed = point
    return {"phase": "running", "halt": passed, "progress": 1.0,
            "distance": passed.distance_km or 0.0, "section": None, "speed": passed.speed_to_next_kmph}


def advance_demo(db: Session, train: Train, persist_snapshot: bool = True) -> TrainStateSnapshot | None:
    """One simulation tick: evolve delay, mark halt crossings, write snapshot."""
    # SQLite returns naive datetimes (stored UTC) — re-tag before arithmetic.
    from app.utils.timeutil import aware_utc

    for point in train.route_points:
        point.scheduled_arrival = aware_utc(point.scheduled_arrival)
        point.scheduled_departure = aware_utc(point.scheduled_departure)

    sim = get_or_create_state(db, train)
    now = utcnow()
    sim_time, wrapped = compute_demo_clock(sim, train, now)

    if wrapped:
        sim.demo_delay_minutes = 0.0
        sim.demo_last_sim_time = None
        _clear_demo_actuals(train)
        add_event(db, train.id, "system", "Demo run restarted (simulated journey loop).", is_simulated=True)

    halts = [p for p in train.route_points if p.is_halt]
    first_dep = next((p.scheduled_departure for p in train.route_points if p.scheduled_departure), None)
    running = first_dep is not None and sim_time >= first_dep

    last_sim_time = aware_utc(sim.demo_last_sim_time)
    if running and last_sim_time is not None:
        dt_sim_minutes = (sim_time - last_sim_time).total_seconds() / 60.0
        reversion = -0.02 * max(0.0, sim.demo_delay_minutes - 10.0)
        jitter = random.gauss(0.0, 0.3)
        delta = (reversion / 10.0) * dt_sim_minutes / 10.0 + jitter * dt_sim_minutes / 10.0
        sim.demo_delay_minutes = max(0.0, min(120.0, sim.demo_delay_minutes + delta))

    delay = sim.demo_delay_minutes if running else 0.0
    delay = max(0.0, min(120.0, delay))

    # position = where the schedule says the train should be at (sim_time - delay)
    train_clock = sim_time - timedelta(minutes=delay) if running else sim_time
    position = locate_on_schedule(list(train.route_points), train_clock)

    # --- simulated halt crossings (actuals) ---
    if running and last_sim_time is not None:
        previous_clock = last_sim_time - timedelta(minutes=sim.demo_delay_minutes)
        for halt in halts:
            arr = halt.scheduled_arrival
            if arr is None or halt.delay_arrival is not None:
                continue
            if previous_clock <= arr <= train_clock:
                halt.actual_arrival = arr + timedelta(minutes=delay)
                halt.delay_arrival = round(delay, 1)
                add_event(
                    db, train.id, "arrival",
                    f"Arrived {halt.station_name} (+{round(delay)} min) — SIMULATED",
                    is_simulated=True, timestamp=arr + timedelta(minutes=delay),
                )
            dep = halt.scheduled_departure
            if dep is not None and halt.delay_departure is None and previous_clock <= dep <= train_clock:
                halt.actual_departure = dep + timedelta(minutes=delay)
                halt.delay_departure = round(delay, 1)
                if halt is not halts[-1]:
                    add_event(
                        db, train.id, "departure",
                        f"Departed {halt.station_name} (+{round(delay)} min) — SIMULATED",
                        is_simulated=True, timestamp=dep + timedelta(minutes=delay),
                    )

    # --- snapshot (all phases: not-started / running / reached) ---
    snap = None
    if persist_snapshot:
        phase = position["phase"]
        if phase == "not-started":
            location = f"{position['halt'].station_name} (awaiting departure)"
            status, speed = "not-started", position.get("speed")
        elif phase == "reached":
            location = position["halt"].station_name
            status, speed = "reached", None
        else:
            nxt = position.get("next")
            if nxt is not None and position["progress"] < 0.98:
                location = f"Between {position['halt'].station_name} and {nxt.station_name}"
            else:
                location = f"Approaching {nxt.station_name if nxt else position['halt'].station_name}"
            status = "running"
            speed = position.get("speed")
            speed = round(speed, 1) if speed else None

        snap = TrainStateSnapshot(
            train_id=train.id, timestamp=now,
            current_station=position["halt"].station_code,
            current_station_name=location,
            current_sequence=position["halt"].sequence,
            latitude=position["halt"].latitude,
            longitude=position["halt"].longitude,
            current_delay_minutes=round(delay, 1),
            current_speed_kmph=speed,
            status=status,
            distance_covered_km=round(position["distance"], 1),
            data_source="DEMO",
        )
        db.add(snap)

    sim.demo_last_sim_time = sim_time
    sim.demo_tick_count = (sim.demo_tick_count or 0) + 1
    sim.updated_at = now
    db.commit()
    return snap


def _train_mode(db: Session, train: Train) -> str:
    """Effective mode for a train.

    DATA_MODE=DEMO or no RailRadar key  → hard zero-call guarantee: every train
    runs the DEMO replay (fresh clones work with no configuration at all).
    DATA_MODE=LIVE                      → every tracked train refreshes from RailRadar.
    DATA_MODE=AUTO (default)            → per-train choice:
      - trains with `live_enabled=True` refresh from RailRadar (real data);
      - the designated demo train (settings.demo_train_number, default 12637)
        runs the free DEMO simulation;
      - every other train is IDLE: no simulation, it simply shows its last
        real snapshot until the user switches LIVE on or presses refresh.
    """
    from app.config import settings as cfg

    if cfg.data_mode == "DEMO" or not cfg.railradar_configured:
        return "DEMO"
    if cfg.data_mode == "LIVE":
        return "LIVE"
    # AUTO
    if bool(getattr(train, "live_enabled", False)):
        return "LIVE"
    return "DEMO" if train.train_number == cfg.demo_train_number else "IDLE"

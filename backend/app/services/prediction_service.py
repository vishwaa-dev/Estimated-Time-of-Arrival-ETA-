"""Centralised prediction engine — ALL delay/ETA/confidence formulas live here.

CORE FORMULA (documented, per project brief):

    final_predicted_delay = current_delay
                          + predicted_additional_delay
                          - recovery_minutes
    predicted_eta         = scheduled_eta + final_predicted_delay

Rule-based components of `predicted_additional_delay` (each documented below):
  1. slowdown      — extra running time implied by current speed deficit
  2. stops         — expected dwell overrun at upcoming halts
  3. weather       — risk-score-scaled heuristic (risk INPUT, never causal claim)
  4. delay trend   — delay growth since the previous snapshot
  5. time of day   — peak congestion windows (early morning / evening)

Prediction hierarchy: trained ML model -> deterministic rule-based estimator.
`prediction_method` always tells the truth about which was used.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import PredictionFactor, PredictionSnapshot, RoutePoint, Train, TrainStateSnapshot, WeatherSnapshot
from app.services.event_service import add_event
from app.services.ml_bridge import predict_additional_delay_ml
from app.services.recovery_service import (
    RecoveryEstimate,
    calculate_recovery_potential,
    calculate_section_recovery,
)
from app.utils.timeutil import to_ist, utcnow

PEAK_HOURS = set(range(5, 10)) | set(range(17, 22))  # 05-09 & 17-21 IST


@dataclass
class RouteSection:
    from_point: RoutePoint
    to_point: RoutePoint
    distance_km: float
    scheduled_running_minutes: float
    scheduled_dwell_minutes: float | None  # dwell at to_point (None = destination)


@dataclass
class PredictionContext:
    """Everything the engine needs, already normalised. Missing data stays None."""

    train: Train
    snapshot: TrainStateSnapshot | None
    previous_snapshot: TrainStateSnapshot | None
    route: list[RoutePoint]
    weather: object  # weather_service.WeatherResult
    now: datetime = field(default_factory=utcnow)

    # derived (filled by derive_context)
    halted_points: list = field(default_factory=list)
    current_index: int = 0
    passed_halts: list = field(default_factory=list)
    upcoming_halts: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    destination: RoutePoint | None = None
    scheduled_avg_speed: float = 45.0
    distance_remaining_km: float = 0.0
    scheduled_minutes_remaining: float = 0.0
    dwell_deviation_minutes: float = 0.0
    running_delay_minutes: float = 0.0

    @property
    def effective_current_delay(self) -> float:
        base = self.snapshot.current_delay_minutes if self.snapshot and self.snapshot.current_delay_minutes is not None else 0.0
        return max(0.0, base)

    @property
    def effective_speed(self) -> float | None:
        speed = self.snapshot.current_speed_kmph if self.snapshot else None
        if speed is None:
            speed = next((p.speed_to_next_kmph for p in reversed(self.halted_points) if p.speed_to_next_kmph), None)
        if speed is None:
            for p in self.route:
                if p.speed_to_next_kmph:
                    speed = p.speed_to_next_kmph
                    break
        return speed


# --------------------------------------------------------------------------
# Context derivation
# --------------------------------------------------------------------------
def derive_context(ctx: PredictionContext) -> PredictionContext:
    ctx.halted_points = [p for p in ctx.route if p.is_halt]

    current_seq = ctx.snapshot.current_sequence if ctx.snapshot and ctx.snapshot.current_sequence else None
    if current_seq is None:
        current_seq = ctx.route[0].sequence if ctx.route else 0

    # index of the halt the train is at / last passed
    idx = 0
    for i, point in enumerate(ctx.halted_points):
        if point.sequence <= current_seq:
            idx = i
    ctx.current_index = idx
    ctx.passed_halts = ctx.halted_points[: idx + 1]
    ctx.upcoming_halts = [
        p for p in ctx.halted_points[idx + 1:] if p.scheduled_arrival is not None
    ]
    ctx.destination = ctx.halted_points[-1] if ctx.halted_points else None

    # halt-to-halt sections from the current halt to the destination
    for i in range(idx, len(ctx.halted_points) - 1):
        a, b = ctx.halted_points[i], ctx.halted_points[i + 1]
        if a.scheduled_departure is None or b.scheduled_arrival is None:
            continue
        run_minutes = (b.scheduled_arrival - a.scheduled_departure).total_seconds() / 60.0
        if run_minutes <= 0:
            continue
        dwell = None
        if b.scheduled_departure is not None:
            dwell = (b.scheduled_departure - b.scheduled_arrival).total_seconds() / 60.0
        ctx.sections.append(
            RouteSection(
                from_point=a, to_point=b,
                distance_km=max(0.0, (b.distance_km or 0.0) - (a.distance_km or 0.0)),
                scheduled_running_minutes=run_minutes,
                scheduled_dwell_minutes=dwell,
            )
        )

    total_distance = ctx.train.scheduled_distance_km
    covered = 0.0
    if ctx.snapshot and ctx.snapshot.distance_covered_km is not None:
        covered = ctx.snapshot.distance_covered_km
    elif ctx.halted_points:
        covered = ctx.halted_points[idx].distance_km or 0.0
    if total_distance:
        ctx.distance_remaining_km = max(0.0, total_distance - covered)

    ctx.scheduled_minutes_remaining = sum(s.scheduled_running_minutes for s in ctx.sections)
    ctx.scheduled_avg_speed = (
        total_distance / (ctx.train.scheduled_duration_minutes / 60.0)
        if total_distance and ctx.train.scheduled_duration_minutes
        else 45.0
    )
    ctx.dwell_deviation_minutes = calculate_dwell_deviation(ctx.passed_halts)
    ctx.running_delay_minutes = calculate_running_delay(ctx.passed_halts)
    return ctx


# --------------------------------------------------------------------------
# Documented calculation primitives
# --------------------------------------------------------------------------
def calculate_running_delay(passed_halts: list[RoutePoint]) -> float:
    """Delay of the train's RUNNING (vs schedule) at the last passed halt."""
    for point in reversed(passed_halts):
        if point.delay_departure is not None:
            return float(point.delay_departure)
        if point.delay_arrival is not None:
            return float(point.delay_arrival)
        if point.actual_departure and point.scheduled_departure:
            return max(0.0, (point.actual_departure - point.scheduled_departure).total_seconds() / 60.0)
    return 0.0


def calculate_dwell_deviation(passed_halts: list[RoutePoint]) -> float:
    """Average dwell overrun at passed intermediate halts (positive = longer
    stops than scheduled). Only halts with all four timings count."""
    deviations: list[float] = []
    for point in passed_halts[:-1]:  # exclude current halt
        if None in (point.actual_arrival, point.actual_departure, point.scheduled_arrival, point.scheduled_departure):
            continue
        actual = (point.actual_departure - point.actual_arrival).total_seconds() / 60.0
        scheduled = (point.scheduled_departure - point.scheduled_arrival).total_seconds() / 60.0
        deviations.append(actual - scheduled)
    return sum(deviations) / len(deviations) if deviations else 0.0


def predict_additional_delay(ctx: PredictionContext) -> tuple[float, list[dict]]:
    """Feature-based rule estimator. Returns (total_minutes, components).

    Components (each capped, sum clamped to [0, 60]):
      slowdown  = dist_remaining * (1/current_speed - 1/expected_section_speed) * 60 * 0.6
      stops     = upcoming_halts * 1.5 * (1 + 0.15*max(0, dwell_dev))
      weather   = (risk/100) * min(12, 2 + dist_remaining/60)
      trend     = clamp(0.5*(current - previous), -2, +4)
      peak      = +1.5 when the arrival window sits in peak hours
    """
    dist = ctx.distance_remaining_km
    speed = ctx.effective_speed
    components: list[dict] = []

    # 1. Speed deficit → extra running minutes over the remaining distance
    expected_section_speed = (
        dist / (ctx.scheduled_minutes_remaining / 60.0)
        if dist > 0 and ctx.scheduled_minutes_remaining > 0
        else ctx.scheduled_avg_speed
    )
    slowdown = 0.0
    if speed and speed > 5 and dist > 0:
        extra = dist * (1.0 / speed - 1.0 / max(expected_section_speed, 20.0)) * 60.0
        slowdown = max(0.0, extra) * 0.6
        slowdown = min(slowdown, 30.0)
        if slowdown >= 0.5:
            components.append(dict(
                name="Speed", value=f"{round(speed)} km/h (expected ~{round(expected_section_speed)} km/h)",
                impact=round(slowdown, 1), direction="delay",
                explanation="Current speed is below the scheduled running profile for the remaining section.",
                simulated=False,
            ))

    # 2. Upcoming stops → dwell overrun expectation
    stops = 0.0
    n_stops = len(ctx.upcoming_halts)
    dwell_factor = 1.0 + max(0.0, ctx.dwell_deviation_minutes) * 0.15
    dwell_factor = min(dwell_factor, 2.0)
    if n_stops:
        stops = min(15.0, n_stops * 1.5 * dwell_factor)
        if stops >= 0.5:
            components.append(dict(
                name="Upcoming stops", value=f"{n_stops} halt(s)",
                impact=round(stops, 1), direction="delay",
                explanation=f"Expected dwell overrun across {n_stops} upcoming halt(s).",
                simulated=False,
            ))

    # 3. Weather risk (risk input — heuristic, never a causal claim)
    weather_component = 0.0
    risk = getattr(ctx.weather, "weather_risk_score", 0.0) or 0.0
    if risk > 0:
        weather_component = (risk / 100.0) * min(12.0, 2.0 + dist / 60.0)
        if weather_component >= 0.5:
            components.append(dict(
                name="Weather", value=f"{getattr(ctx.weather, 'weather_condition', 'n/a')} ({getattr(ctx.weather, 'weather_risk_label', '')} risk)",
                impact=round(weather_component, 1), direction="delay",
                explanation=getattr(ctx.weather, "risk_reason", "") or "Weather conditions elevate delay risk.",
                simulated=getattr(ctx.weather, "is_simulated", False),
            ))

    # 4. Delay trend since previous snapshot
    trend = 0.0
    if ctx.previous_snapshot and ctx.snapshot:
        prev = ctx.previous_snapshot.current_delay_minutes or 0.0
        curr = ctx.snapshot.current_delay_minutes or 0.0
        trend = max(-2.0, min(4.0, 0.5 * (curr - prev)))
        if abs(trend) >= 0.5:
            components.append(dict(
                name="Delay trend", value=f"{round(prev)} → {round(curr)} min",
                impact=round(trend, 1), direction="delay" if trend > 0 else "recovery",
                explanation="Delay is growing since the previous observation." if trend > 0
                else "Delay has been reducing since the previous observation.",
                simulated=False,
            ))

    # 5. Time-of-day peak windows
    peak = 0.0
    arrival_hour = to_ist(ctx.now).hour
    if arrival_hour in PEAK_HOURS:
        peak = 1.5
        components.append(dict(
            name="Time of day", value=f"{arrival_hour:02d}:00 IST (peak window)",
            impact=peak, direction="delay",
            explanation="Arrival window falls inside typical congestion peaks on busy sections.",
            simulated=False,
        ))

    total = slowdown + stops + weather_component + max(0.0, trend) + peak
    if trend < 0:
        total += trend  # negative trend relieves
    total = max(0.0, min(60.0, total))
    return round(total, 1), components


def calculate_final_delay(current_delay: float, additional: float, recovery: float) -> float:
    """final = current + additional - recovery, floored at 0."""
    return max(0.0, round(current_delay + additional - recovery, 1))


def calculate_eta(scheduled_eta: datetime, final_delay_minutes: float) -> datetime:
    """ETA = scheduled arrival + final predicted delay."""
    return scheduled_eta + timedelta(minutes=final_delay_minutes)


def calculate_eta_range(
    final_delay_minutes: float,
    distance_remaining_km: float,
    weather_risk_score: float,
    confidence: float,
) -> tuple[timedelta, timedelta]:
    """Estimated (NOT statistically rigorous) ETA half-width in minutes:

    half = 2 + 0.06*final_delay + 0.015*distance_remaining
           + 0.06*weather_risk + 10*(1 - confidence/100)
    """
    half = (
        2.0
        + 0.06 * final_delay_minutes
        + 0.015 * distance_remaining_km
        + 0.06 * weather_risk_score
        + 10.0 * (1.0 - confidence / 100.0)
    )
    half_td = timedelta(minutes=max(1.0, half))
    return half_td, half_td


def calculate_confidence(
    ctx: PredictionContext,
    prediction_method: str,
    snapshot_age_minutes: float,
) -> float:
    """Estimated confidence (0-100) — documented penalty model, labelled
    'Estimated confidence' in the UI. NOT a statistical interval."""
    confidence = 88.0
    if ctx.effective_speed is None:
        confidence -= 8.0  # missing speed observation
    if getattr(ctx.weather, "source", "") == "UNAVAILABLE":
        confidence -= 5.0
    elif (getattr(ctx.weather, "weather_risk_score", 0.0) or 0.0) >= 70:
        confidence -= 6.0
    elif (getattr(ctx.weather, "weather_risk_score", 0.0) or 0.0) >= 40:
        confidence -= 3.0
    if snapshot_age_minutes > 10:
        confidence -= 7.0  # stale state
    if ctx.distance_remaining_km > 300:
        confidence -= 5.0
    elif ctx.distance_remaining_km > 150:
        confidence -= 3.0
    if ctx.effective_speed is not None and ctx.effective_speed < 30:
        confidence -= 4.0
    if prediction_method.startswith("ML"):
        confidence += 3.0
    return max(45.0, min(95.0, round(confidence, 0)))


def generate_prediction_explanation(
    current_delay: float,
    additional: float,
    recovery: float,
    final_delay: float,
    components: list[dict],
    recovery_estimate: RecoveryEstimate,
    destination_name: str | None,
) -> str:
    """Deterministic template explanation — no LLM dependency."""
    dest = destination_name or "the destination"
    delay_bits = [
        f"{c['name'].lower()} ({'+' if c['impact'] >= 0 else ''}{round(c['impact'])} min)"
        for c in components if c["direction"] == "delay" and abs(c["impact"]) >= 0.5
    ][:3]
    persistence = "persist" if current_delay > 0 else "remain broadly on time"
    sentences = [
        f"Current delay of +{round(current_delay, 1)} min is expected to {persistence} over the next section."
    ]
    if delay_bits:
        sentences.append(f"Predicted additional delay of +{round(additional, 1)} min comes mainly from {', '.join(delay_bits)}.")
    if recovery > 0:
        capped = f" (limited by {recovery_estimate.capped_by})" if recovery_estimate.capped_by and "not delayed" not in recovery_estimate.capped_by else ""
        sentences.append(f"Approximately {round(recovery, 1)} min of recovery is expected from upcoming running/dwell slack{capped}.")
    sentences.append(f"Final projected delay at {dest}: +{round(final_delay, 1)} min.")
    return " ".join(sentences)


# --------------------------------------------------------------------------
# Orchestration — build, predict, persist
# --------------------------------------------------------------------------
def _sections_as_dicts(ctx: PredictionContext, recovery_boost: float = 0.0) -> list[dict]:
    return [
        dict(
            from_code=s.from_point.station_code, from_name=s.from_point.station_name,
            to_code=s.to_point.station_code, to_name=s.to_point.station_name,
            distance_km=s.distance_km, scheduled_running_minutes=s.scheduled_running_minutes,
            scheduled_dwell_minutes=s.scheduled_dwell_minutes,
        )
        for s in ctx.sections
    ]


def run_prediction(
    db: Session,
    train: Train,
    weather: object | None = None,
    snapshot: TrainStateSnapshot | None = None,
    previous_snapshot: TrainStateSnapshot | None = None,
    persist: bool = True,
    forecast: bool = True,
) -> dict:
    """Full pipeline: features -> prediction -> recovery -> ETA -> confidence
    -> explanation -> trajectory -> persistence.

    `forecast=False` (IDLE trains): the data is stale by definition, so the
    engine reports only the frozen current state — no additional delay, no
    recovery, no ETA forecast. Numbers are not invented from old data.
    """
    from app.services.trajectory_service import build_trajectory  # local import avoids cycle

    if snapshot is None:
        snapshot = (
            db.query(TrainStateSnapshot)
            .filter(TrainStateSnapshot.train_id == train.id)
            .order_by(TrainStateSnapshot.timestamp.desc())
            .first()
        )
    if previous_snapshot is None and snapshot:
        previous_snapshot = (
            db.query(TrainStateSnapshot)
            .filter(TrainStateSnapshot.train_id == train.id)
            .filter(TrainStateSnapshot.id != snapshot.id)
            .order_by(TrainStateSnapshot.timestamp.desc())
            .first()
        )
    if weather is None:
        weather = _latest_weather(db, train)

    # SQLite returns naive datetimes (stored UTC) — re-tag so all downstream
    # arithmetic is timezone-aware.
    from app.utils.timeutil import aware_utc

    for point in train.route_points:
        point.scheduled_arrival = aware_utc(point.scheduled_arrival)
        point.scheduled_departure = aware_utc(point.scheduled_departure)
        point.actual_arrival = aware_utc(point.actual_arrival)
        point.actual_departure = aware_utc(point.actual_departure)
    snapshot.timestamp = aware_utc(snapshot.timestamp) if snapshot else None
    if previous_snapshot:
        previous_snapshot.timestamp = aware_utc(previous_snapshot.timestamp)

    ctx = PredictionContext(
        train=train, snapshot=snapshot, previous_snapshot=previous_snapshot,
        route=list(train.route_points), weather=weather,
    )
    derive_context(ctx)

    current_delay = round(ctx.effective_current_delay, 1)

    if forecast:
        # ---- ML-first with deterministic fallback ----
        ml_estimate = predict_additional_delay_ml(ctx)
        if ml_estimate is not None:
            additional, method, ml_conf = ml_estimate
            components = _rule_components_for_explanation(ctx)
        else:
            additional, components = predict_additional_delay(ctx)
            method, ml_conf = "Rule-Based Prototype", 0.0

        # ---- Recovery ----
        section_dicts = _sections_as_dicts(ctx)
        section_recoveries = calculate_section_recovery(section_dicts, ctx.scheduled_avg_speed)
        recovery_estimate = calculate_recovery_potential(section_recoveries, ctx.effective_current_delay)
        recovery = round(recovery_estimate.applied_recovery_minutes, 1)
        final_delay = calculate_final_delay(current_delay, additional, recovery)

        confidence = calculate_confidence(ctx, method, snapshot_age_minutes(ctx.snapshot, ctx.now)) + ml_conf
        confidence = max(45.0, min(95.0, round(confidence, 0)))

        factors = _build_factors(ctx, current_delay, additional, components, recovery, recovery_estimate)
        explanation = generate_prediction_explanation(
            current_delay, additional, recovery, final_delay,
            components, recovery_estimate, ctx.destination.station_name if ctx.destination else None,
        )
        primary_reason = max(factors, key=lambda f: abs(f["impact_minutes"] or 0))["name"] if factors else "scheduled operation"

        trajectory = build_trajectory(ctx, current_delay, additional, recovery, recovery_estimate, confidence, final_delay)

        destination_arrival = ctx.destination.scheduled_arrival if ctx.destination else None
        if destination_arrival is None:
            predicted_eta = eta_lower = eta_upper = None
        else:
            predicted_eta = calculate_eta(destination_arrival, final_delay)
            half_low, half_high = calculate_eta_range(
                final_delay, ctx.distance_remaining_km,
                getattr(weather, "weather_risk_score", 0.0) or 0.0, confidence,
            )
            eta_lower = predicted_eta - half_low
            eta_upper = predicted_eta + half_high
    else:
        additional = recovery = final_delay = None
        confidence = None
        predicted_eta = eta_lower = eta_upper = None
        method = "No forecast (train idle)"
        section_recoveries = []
        recovery_estimate = RecoveryEstimate()
        factors = []
        explanation = ""
        primary_reason = "awaiting live data"
        destination_arrival = ctx.destination.scheduled_arrival if ctx.destination else None
        # Observed history + current position only — no predicted stations.
        trajectory = [
            p for p in build_trajectory(ctx, current_delay, 0.0, 0.0, recovery_estimate, 0.0, current_delay)
            if p["kind"] != "predicted"
        ]

    data_mode = (
        "LIVE" if (snapshot and snapshot.data_source == "LIVE")
        else ("CACHED" if snapshot and snapshot.data_source == "CACHED" else "DEMO")
    )
    if not forecast:
        data_mode = "IDLE"
    result = {
        "train_number": train.train_number,
        "train_name": train.train_name,
        "current_state": {
            "location": (snapshot.current_station_name if snapshot else None) or train.source_name,
            "current_delay_minutes": current_delay,
            "current_speed_kmph": ctx.effective_speed,
            "status": (snapshot.status if snapshot else None) or train.status or "unknown",
            "distance_covered_km": round(snapshot.distance_covered_km, 1) if snapshot and snapshot.distance_covered_km is not None else None,
            "distance_remaining_km": round(ctx.distance_remaining_km, 1),
            "data_source": snapshot.data_source if snapshot else "SEED",
        },
        "prediction": {
            "predicted_additional_delay_minutes": additional,
            "recovery_minutes": recovery,
            "final_predicted_delay_minutes": final_delay,
            "predicted_eta": predicted_eta.isoformat() if predicted_eta else None,
            "eta_lower_bound": eta_lower.isoformat() if predicted_eta else None,
            "eta_upper_bound": eta_upper.isoformat() if predicted_eta else None,
            "confidence": confidence,
            "confidence_label": "Estimated confidence",
            "prediction_method": method,
            "scheduled_arrival": destination_arrival.isoformat() if destination_arrival else None,
        },
        "factors": factors,
        "explanation": explanation,
        "primary_reason": primary_reason,
        "recovery_map": [s.to_dict() for s in section_recoveries],
        "recovery_summary": {
            "applied_recovery_minutes": recovery,
            "raw_recoverable_minutes": round(recovery_estimate.raw_recoverable_minutes, 1),
            "capped_by": recovery_estimate.capped_by,
        },
        "trajectory": trajectory,
        "data_mode": data_mode,
        "forecast_available": forecast,
        "simulated": data_mode == "DEMO",
        "last_state_update": snapshot.timestamp if snapshot else None,
        "updated_at": ctx.now.isoformat(),
    }

    if persist:
        snap_row = PredictionSnapshot(
            train_id=train.id, timestamp=ctx.now,
            current_delay=current_delay,
            predicted_additional_delay=additional,
            recovery_minutes=recovery,
            final_predicted_delay=final_delay,
            predicted_eta=predicted_eta,
            eta_lower_bound=eta_lower,
            eta_upper_bound=eta_upper,
            confidence=confidence, prediction_mode=method,
            primary_reason=primary_reason,
            data_mode=result["data_mode"],
        )
        db.add(snap_row)
        db.flush()
        for f in factors:
            db.add(PredictionFactor(
                prediction_id=snap_row.id, factor_name=f["name"],
                factor_value=str(f.get("value")), impact_minutes=f["impact_minutes"],
                impact_direction=f["direction"], explanation=f.get("explanation"),
                is_simulated=f.get("simulated", False),
            ))
        db.commit()
    return result


def _rule_components_for_explanation(ctx: PredictionContext) -> list[dict]:
    """When the ML model provides the number, still show rule components as the
    factor breakdown (transparent about the heuristic drivers)."""
    _, components = predict_additional_delay(ctx)
    return components


def _build_factors(
    ctx: PredictionContext, current_delay: float, additional: float,
    components: list[dict], recovery: float, recovery_estimate: RecoveryEstimate,
) -> list[dict]:
    factors: list[dict] = [
        dict(
            name="Current Delay", value=f"+{round(current_delay, 1)} min",
            impact_minutes=round(current_delay, 1), direction="delay",
            explanation="Delay already accumulated by the train.",
            simulated=False,
        )
    ]
    for c in components:
        factors.append(dict(
            name=c["name"], value=str(c["value"]),
            impact_minutes=c["impact"], direction=c["direction"],
            explanation=c["explanation"], simulated=c.get("simulated", False),
        ))
    if recovery > 0:
        factors.append(dict(
            name="Recovery", value=f"{round(recovery, 1)} min",
            impact_minutes=-round(recovery, 1), direction="recovery",
            explanation="Estimated recoverable minutes from upcoming running-time slack and dwell compression.",
            simulated=False,
        ))
    return factors


def snapshot_age_minutes(snapshot: TrainStateSnapshot | None, now: datetime) -> float:
    if snapshot is None or snapshot.timestamp is None:
        return 0.0
    from app.utils.timeutil import UTC

    ts = snapshot.timestamp if snapshot.timestamp.tzinfo else snapshot.timestamp.replace(tzinfo=UTC)
    return max(0.0, (now - ts).total_seconds() / 60.0)


def _latest_weather(db: Session, train: Train):
    from app.services.weather_service import WeatherResult, _last_snapshot_or_unavailable

    snap = (
        db.query(WeatherSnapshot)
        .filter(WeatherSnapshot.train_id == train.id)
        .order_by(WeatherSnapshot.timestamp.desc())
        .first()
    )
    if snap:
        return WeatherResult(
            location=snap.location, temperature=snap.temperature, rainfall=snap.rainfall,
            precipitation_probability=snap.precipitation_probability, wind_speed=snap.wind_speed,
            visibility=snap.visibility, weather_condition=snap.weather_condition,
            weather_risk_score=snap.weather_risk_score or 0.0,
            weather_risk_label=snap.weather_risk_label or "UNKNOWN",
            risk_reason="last stored observation", is_simulated=snap.is_simulated,
            source="CACHED", observed_at=snap.timestamp.isoformat() if snap.timestamp else None,
        )
    return _last_snapshot_or_unavailable(db, train.id, None)

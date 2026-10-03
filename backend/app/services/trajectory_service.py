"""Delay trajectory — the main differentiator.

Produces a station-by-station projection of EXPECTED DELAY (not just one ETA):

    delay_at_station_j = current_delay
                       + additional_delay * (distance covered to j / total remaining)
                       - recovery applied cumulatively up to j

Observed points come from actual arrival/departure data of passed halts;
predicted points from the formula above. Confidence decays 2.5 pts per station
ahead (floor 55) and the ETA band widens with distance.
"""
from datetime import timedelta


def _observed_delay(point) -> float | None:
    if point.delay_arrival is not None:
        return float(point.delay_arrival)
    if point.delay_departure is not None:
        return float(point.delay_departure)
    if point.actual_arrival and point.scheduled_arrival:
        return max(0.0, (point.actual_arrival - point.scheduled_arrival).total_seconds() / 60.0)
    return None


def build_trajectory(
    ctx,
    current_delay: float,
    additional: float,
    recovery: float,
    recovery_estimate,
    confidence: float,
    final_delay: float,
) -> list[dict]:
    points: list[dict] = []
    weather_risk = getattr(ctx.weather, "weather_risk_score", 0.0) or 0.0

    current_halt = ctx.halted_points[ctx.current_index] if ctx.halted_points else None
    current_distance = 0.0
    if ctx.snapshot and ctx.snapshot.distance_covered_km is not None:
        current_distance = ctx.snapshot.distance_covered_km
    elif current_halt is not None:
        current_distance = current_halt.distance_km or 0.0
    remaining = max(1.0, ctx.distance_remaining_km)

    # --- observed (past) halts ---
    for point in ctx.passed_halts:
        delay = _observed_delay(point)
        actual = point.actual_arrival or (
            point.scheduled_arrival + timedelta(minutes=delay) if point.scheduled_arrival and delay is not None else None
        )
        points.append(dict(
            station_code=point.station_code, station_name=point.station_name,
            sequence=point.sequence, kind="observed",
            scheduled_arrival=point.scheduled_arrival.isoformat() if point.scheduled_arrival else None,
            predicted_arrival=actual.isoformat() if actual else None,
            delay_minutes=round(delay, 1) if delay is not None else None,
            confidence=None, eta_lower=None, eta_upper=None, recovery_minutes=0.0,
        ))

    # --- current position ---
    if current_halt is not None:
        points.append(dict(
            station_code=current_halt.station_code, station_name=current_halt.station_name or "Current position",
            sequence=current_halt.sequence, kind="current",
            scheduled_arrival=current_halt.scheduled_arrival.isoformat() if current_halt.scheduled_arrival else None,
            predicted_arrival=None, delay_minutes=round(current_delay, 1),
            confidence=None, eta_lower=None, eta_upper=None, recovery_minutes=0.0,
        ))

    # --- predicted halts ---
    # cumulative raw-recoverable per section (for progressive recovery)
    raws = [s.total_recoverable_minutes for s in recovery_estimate.sections] or []
    total_raw = sum(raws) or 1.0

    for i, halt in enumerate(ctx.upcoming_halts):
        dist_j = halt.distance_km or current_distance
        frac = max(0.0, min(1.0, (dist_j - current_distance) / remaining))
        addl_j = additional * frac
        # recovery accumulates over the sections traversed up to this halt
        secs_passed = max(0, min(i, len(raws)))
        rec_frac = sum(raws[:secs_passed]) / total_raw if raws else 0.0
        rec_j = recovery * rec_frac
        delay_j = max(0.0, round(current_delay + addl_j - rec_j, 1))
        if halt.sequence == (ctx.destination.sequence if ctx.destination else None):
            delay_j = final_delay  # engine's headline figure at the destination

        conf_j = max(55.0, round(confidence - 2.5 * (i + 1)))
        half = 2.0 + 0.06 * delay_j + 0.015 * max(0.0, dist_j - current_distance) + 0.06 * weather_risk + 10.0 * (1 - conf_j / 100.0)
        predicted_arrival = (
            halt.scheduled_arrival + timedelta(minutes=delay_j) if halt.scheduled_arrival else None
        )
        points.append(dict(
            station_code=halt.station_code, station_name=halt.station_name,
            sequence=halt.sequence, kind="predicted",
            scheduled_arrival=halt.scheduled_arrival.isoformat() if halt.scheduled_arrival else None,
            predicted_arrival=predicted_arrival.isoformat() if predicted_arrival else None,
            delay_minutes=delay_j,
            confidence=conf_j,
            eta_lower=(predicted_arrival - timedelta(minutes=half)).isoformat() if predicted_arrival else None,
            eta_upper=(predicted_arrival + timedelta(minutes=half)).isoformat() if predicted_arrival else None,
            recovery_minutes=round(rec_j, 1),
        ))
    return points

"""Bridge between the prediction engine and the optional ML model.

Builds the feature vector from the PredictionContext and calls the model.
Returns None → deterministic fallback in prediction_service.
"""
from app.ml.features import build_vector_from_values


def _route_slack_minutes(ctx) -> tuple[float, float]:
    """(raw slack, applied recovery potential) computed independently of the
    additional-delay estimate — recovery does not depend on that estimate."""
    from app.services.recovery_service import calculate_recovery_potential, calculate_section_recovery

    sections = []
    for i in range(ctx.current_index, len(ctx.halted_points) - 1):
        a, b = ctx.halted_points[i], ctx.halted_points[i + 1]
        if a.scheduled_departure is None or b.scheduled_arrival is None:
            continue
        run = (b.scheduled_arrival - a.scheduled_departure).total_seconds() / 60.0
        if run <= 0:
            continue
        dwell = None
        if b.scheduled_departure is not None:
            dwell = (b.scheduled_departure - b.scheduled_arrival).total_seconds() / 60.0
        sections.append(dict(
            from_code=a.station_code, from_name=a.station_name,
            to_code=b.station_code, to_name=b.station_name,
            distance_km=max(0.0, (b.distance_km or 0.0) - (a.distance_km or 0.0)),
            scheduled_running_minutes=run, scheduled_dwell_minutes=dwell,
        ))
    recoveries = calculate_section_recovery(sections, ctx.scheduled_avg_speed)
    estimate = calculate_recovery_potential(recoveries, ctx.effective_current_delay)
    return estimate.raw_recoverable_minutes, estimate.applied_recovery_minutes


def build_vector(ctx) -> list[float]:
    speed = ctx.effective_speed
    average_speed = ctx.scheduled_avg_speed
    speed_deviation = (average_speed - speed) if speed is not None else 0.0
    route_slack, recovery_potential = _route_slack_minutes(ctx)
    from app.utils.timeutil import to_ist

    return build_vector_from_values(
        current_delay=ctx.effective_current_delay,
        previous_delay=(ctx.previous_snapshot.current_delay_minutes or 0.0) if ctx.previous_snapshot else ctx.effective_current_delay,
        current_speed=speed,
        average_speed=average_speed,
        speed_deviation=speed_deviation,
        running_delay=ctx.running_delay_minutes,
        distance_remaining=ctx.distance_remaining_km,
        upcoming_stops=len(ctx.upcoming_halts),
        dwell_deviation=ctx.dwell_deviation_minutes,
        weather_risk=getattr(ctx.weather, "weather_risk_score", 0.0) or 0.0,
        rainfall=getattr(ctx.weather, "rainfall", None),
        wind_speed=getattr(ctx.weather, "wind_speed", None),
        visibility=getattr(ctx.weather, "visibility", None),
        time_of_day=to_ist(ctx.now).hour,
        route_slack=route_slack,
        recovery_potential=recovery_potential,
    )


def predict_additional_delay_ml(ctx) -> tuple[float, str, float] | None:
    """Returns (additional_minutes, method_label, confidence_bonus) or None."""
    from app.ml.predict import predict_additional

    try:
        vector = build_vector(ctx)
    except Exception:
        return None
    estimate = predict_additional(vector)
    if estimate is None:
        return None
    return round(estimate, 1), "ML (synthetic training data)", 3.0

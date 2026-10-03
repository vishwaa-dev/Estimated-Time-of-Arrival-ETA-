"""Feature vector definition shared by the ML model and the rule engine."""

FEATURE_NAMES = [
    "current_delay_minutes",
    "previous_delay_minutes",
    "current_speed_kmph",
    "average_speed_kmph",
    "speed_deviation",
    "running_delay_minutes",
    "distance_remaining_km",
    "upcoming_stop_count",
    "dwell_deviation_minutes",
    "weather_risk_score",
    "rainfall",
    "wind_speed",
    "visibility",
    "time_of_day",
    "route_slack_minutes",
    "recovery_potential_minutes",
]


def build_vector_from_values(
    current_delay: float,
    previous_delay: float,
    current_speed: float | None,
    average_speed: float,
    speed_deviation: float,
    running_delay: float,
    distance_remaining: float,
    upcoming_stops: int,
    dwell_deviation: float,
    weather_risk: float,
    rainfall: float | None,
    wind_speed: float | None,
    visibility: float | None,
    time_of_day: int,
    route_slack: float,
    recovery_potential: float,
) -> list[float]:
    """Missing values fall back to neutral defaults (never NaN)."""
    return [
        float(current_delay or 0.0),
        float(previous_delay if previous_delay is not None else current_delay or 0.0),
        float(current_speed if current_speed is not None else average_speed),
        float(average_speed or 45.0),
        float(speed_deviation or 0.0),
        float(running_delay or 0.0),
        float(distance_remaining or 0.0),
        float(upcoming_stops or 0),
        float(dwell_deviation or 0.0),
        float(weather_risk or 0.0),
        float(rainfall or 0.0),
        float(wind_speed or 0.0),
        float(visibility if visibility is not None else 10.0),
        float(time_of_day),
        float(route_slack or 0.0),
        float(recovery_potential or 0.0),
    ]

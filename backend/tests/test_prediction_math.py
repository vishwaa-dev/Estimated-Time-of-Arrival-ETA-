"""Core math: final delay formula, ETA, recovery bounds, dwell, weather risk."""
from datetime import timedelta
from types import SimpleNamespace

from app.services.prediction_service import (
    PredictionContext,
    calculate_dwell_deviation,
    calculate_eta,
    calculate_final_delay,
)
from app.services.recovery_service import (
    calculate_recovery_potential,
    calculate_section_recovery,
)
from app.services.weather_service import score_weather


def _point(**kw):
    base = dict(sequence=1, station_code="X", station_name="X Jn", is_halt=True,
                scheduled_arrival=None, scheduled_departure=None, actual_arrival=None,
                actual_departure=None, delay_arrival=None, delay_departure=None,
                distance_km=0.0, platform=None, speed_to_next_kmph=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_final_delay_formula_8_plus_5_minus_3():
    # The brief's worked example: 8 + 5 - 3 = 10
    assert calculate_final_delay(8, 5, 3) == 10


def test_final_delay_never_negative():
    assert calculate_final_delay(2, 1, 5) == 0


def test_eta_adds_final_delay():
    scheduled = SimpleNamespace()  # datetime arithmetic check
    from datetime import datetime, timezone

    base = datetime(2026, 9, 3, 5, 30, tzinfo=timezone.utc)
    assert calculate_eta(base, 10) == base + timedelta(minutes=10)


def test_current_delay_from_snapshot():
    snap = SimpleNamespace(current_delay_minutes=8.0)
    ctx = PredictionContext(train=None, snapshot=snap, previous_snapshot=None, route=[], weather=None)
    assert ctx.effective_current_delay == 8.0
    # negative reported delay floors at zero, missing snapshot is zero
    late_but_ok = PredictionContext(
        train=None, snapshot=SimpleNamespace(current_delay_minutes=-4.0),
        previous_snapshot=None, route=[], weather=None,
    )
    assert late_but_ok.effective_current_delay == 0.0
    empty = PredictionContext(train=None, snapshot=None, previous_snapshot=None, route=[], weather=None)
    assert empty.effective_current_delay == 0.0


def test_dwell_deviation_positive_when_stops_run_long():
    from datetime import datetime, timezone

    t = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)
    completed = _point(  # finished halt: dwell ran 5 min vs 2 scheduled
        scheduled_arrival=t, scheduled_departure=t + timedelta(minutes=2),
        actual_arrival=t, actual_departure=t + timedelta(minutes=5),
    )
    current = _point(sequence=2, station_code="Y", station_name="Y Jn")  # current halt excluded
    assert calculate_dwell_deviation([completed, current]) == 3.0


def test_dwell_deviation_ignores_missing_actuals():
    t = None
    halt = _point(scheduled_arrival=t, scheduled_departure=t, actual_arrival=None, actual_departure=None)
    assert calculate_dwell_deviation([halt]) == 0.0


def test_recovery_bounded_by_current_delay_and_cap():
    sections = [
        dict(from_code="A", from_name="A", to_code="B", to_name="B",
             distance_km=60, scheduled_running_minutes=40, scheduled_dwell_minutes=5),
        dict(from_code="B", from_name="B", to_code="C", to_name="C",
             distance_km=80, scheduled_running_minutes=70, scheduled_dwell_minutes=None),
    ]
    recoveries = calculate_section_recovery(sections, scheduled_avg_speed_kmph=60)
    assert all(r.slack_minutes >= 0 for r in recoveries)

    estimate = calculate_recovery_potential(recoveries, current_delay_minutes=3)
    assert estimate.applied_recovery_minutes <= 3  # can never exceed the delay

    estimate = calculate_recovery_potential(recoveries, current_delay_minutes=120)
    assert estimate.applied_recovery_minutes <= 20  # configured cap


def test_recovery_zero_when_not_delayed():
    sections = [dict(from_code="A", from_name="A", to_code="B", to_name="B",
                     distance_km=50, scheduled_running_minutes=60, scheduled_dwell_minutes=5)]
    recoveries = calculate_section_recovery(sections, 60)
    estimate = calculate_recovery_potential(recoveries, current_delay_minutes=0)
    assert estimate.applied_recovery_minutes == 0.0


def test_section_classification_bands():
    fast_section = dict(from_code="A", from_name="A", to_code="B", to_name="B",
                        distance_km=40, scheduled_running_minutes=60, scheduled_dwell_minutes=None)
    tight = dict(from_code="B", from_name="B", to_code="C", to_name="C",
                 distance_km=40, scheduled_running_minutes=34, scheduled_dwell_minutes=None)
    recs = calculate_section_recovery([fast_section, tight], scheduled_avg_speed_kmph=60)
    assert recs[0].classification in ("HIGH", "MEDIUM")   # generous margin
    assert recs[1].classification in ("LOW", "MEDIUM")    # tight margin


def test_weather_risk_bands():
    score, label, _ = score_weather("Clear Sky", 0, 2, 10, 5)
    assert score < 15 and label == "NORMAL"

    score, label, _ = score_weather("Light Rain", 2.5, 4, 8, 65)
    assert 35 <= score < 60 and label in ("LOW", "MEDIUM")

    score, label, _ = score_weather("Heavy Rain", 22, 9, 3, 92)
    assert score >= 60 and label in ("HIGH", "VERY HIGH")

    score, label, _ = score_weather("Thunderstorm", 48, 16, 1.2, 100)
    assert score >= 80 and label == "VERY HIGH"

    # never out of bounds
    score, _, _ = score_weather("Unknown", 999, 99, 0, 100)
    assert 0 <= score <= 100

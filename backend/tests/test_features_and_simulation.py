"""Feature generation, ML fallback and simulation engine tests."""
from datetime import datetime, timezone

from app.ml.features import FEATURE_NAMES, build_vector_from_values
from app.ml.synthetic import generate_samples
from app.services.simulation_service import locate_on_schedule


def test_feature_vector_shape_and_defaults():
    vec = build_vector_from_values(
        current_delay=8, previous_delay=None, current_speed=None, average_speed=63.4,
        speed_deviation=5, running_delay=8, distance_remaining=200, upcoming_stops=4,
        dwell_deviation=1.5, weather_risk=55, rainfall=None, wind_speed=None,
        visibility=None, time_of_day=14, route_slack=10, recovery_potential=4,
    )
    assert len(vec) == len(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in vec)
    assert vec[0] == 8.0
    assert vec[1] == 8.0            # previous falls back to current
    assert vec[2] == 63.4           # speed falls back to scheduled average
    assert vec[11] == 0.0           # missing wind → neutral
    assert vec[12] == 10.0          # missing visibility → clear default


def test_synthetic_samples_are_bounded():
    vectors, targets = generate_samples(n=200, seed=1)
    assert len(vectors) == len(targets) == 200
    assert all(0.0 <= t <= 60.0 for t in targets)
    assert all(len(v) == len(FEATURE_NAMES) for v in vectors)


def test_ml_graceful_fallback_when_model_missing(tmp_path, monkeypatch):
    from app.ml import predict as ml_predict

    monkeypatch.setattr(ml_predict, "_loaded", True)
    monkeypatch.setattr(ml_predict, "_model", None)
    assert ml_predict.predict_additional([1.0] * len(FEATURE_NAMES)) is None


def test_locate_on_schedule_phases():
    from datetime import timedelta

    def halt(seq, dep=None, arr=None, dist=0.0):
        return type("P", (), {"sequence": seq, "station_code": f"S{seq}", "station_name": f"Stn {seq}",
                              "is_halt": True, "scheduled_arrival": arr, "scheduled_departure": dep,
                              "distance_km": dist, "speed_to_next_kmph": 60.0,
                              "latitude": None, "longitude": None})

    t0 = datetime(2026, 9, 2, 21, 40, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 2, 22, 5, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 22, 7, tzinfo=timezone.utc)
    t3 = datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc)
    route = [halt(1, dep=t0, dist=0.0), halt(2, arr=t1, dep=t2, dist=24.8), halt(3, arr=t3, dist=100.0)]

    before = locate_on_schedule(route, t0 - timedelta(minutes=5))
    assert before["phase"] == "not-started"

    mid = locate_on_schedule(route, t0 + timedelta(minutes=12))
    assert mid["phase"] == "running"
    assert 0 < mid["progress"] < 1
    assert 0 < mid["distance"] < 24.8

    after = locate_on_schedule(route, t3 + timedelta(minutes=5))
    assert after["phase"] == "reached"


def test_delayed_train_sits_behind_its_schedule():
    """A train delayed by D minutes must be located where the schedule was D
    minutes ago — the core DEMO position rule."""
    from datetime import timedelta

    def halt(seq, dep=None, arr=None, dist=0.0):
        return type("P", (), {"sequence": seq, "station_code": f"S{seq}", "station_name": f"Stn {seq}",
                              "is_halt": True, "scheduled_arrival": arr, "scheduled_departure": dep,
                              "distance_km": dist, "speed_to_next_kmph": 60.0,
                              "latitude": None, "longitude": None})

    t0 = datetime(2026, 9, 2, 21, 40, tzinfo=timezone.utc)
    t3 = datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc)
    route = [halt(1, dep=t0, dist=0.0), halt(2, arr=t3, dist=80.0)]

    sim_time = t3 + timedelta(minutes=10)     # 10 min after scheduled arrival
    delayed_clock = sim_time - timedelta(minutes=25)  # train is +25 late
    pos = locate_on_schedule(route, delayed_clock)
    assert pos["phase"] == "running"          # still short of the destination
    assert pos["distance"] < 80.0

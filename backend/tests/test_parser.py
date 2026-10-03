"""Parser robustness: real provided snapshot + hostile/malformed payloads."""
from app.services.parser import parse_train_payload
from app.utils.timeutil import parse_iso


def test_parse_real_provided_snapshot():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "train_12637.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    parsed = parse_train_payload(payload)

    assert parsed.train_number == "12637"
    assert parsed.train_name == "Pandian SF Express"
    assert parsed.source_code == "MS"
    assert parsed.destination_code == "MDU"
    assert parsed.status == "not-started"
    assert len(parsed.route) == 94
    halts = [p for p in parsed.route if p.is_halt]
    assert len(halts) == 11
    assert halts[-1].station_code == "MDU"
    assert parsed.route[0].scheduled_departure == parse_iso("2026-09-02T21:40:00+05:30")


def test_parse_handles_missing_everything():
    parsed = parse_train_payload({})
    assert parsed.train_number == "unknown"
    assert parsed.route == []
    assert parsed.current_delay_minutes == 0.0


def test_parse_handles_missing_actuals_and_speed():
    payload = {
        "data": {
            "trainNumber": "99999",
            "trainName": "Ghost Express",
            "status": "running",
            "delayMinutes": None,
            "route": [
                {"sequence": 1, "stationCode": "AAA", "stationName": "Alpha", "isHalt": True},
                {"sequence": 2, "stationCode": "BBB", "stationName": "Beta", "isHalt": True,
                 "scheduledArrival": None, "actualArrival": None, "speedToNextStationKmph": "not-a-number"},
            ],
        }
    }
    parsed = parse_train_payload(payload)
    assert parsed.train_number == "99999"
    assert parsed.route[1].scheduled_arrival is None
    assert parsed.route[1].speed_to_next_kmph is None
    assert parsed.current_delay_minutes == 0.0  # no crash, safe default
    assert parsed.status == "running"


def test_parse_delay_fallback_from_route():
    payload = {
        "data": {
            "trainNumber": "88888",
            "route": [
                {"sequence": 1, "stationCode": "A", "stationName": "A Jn", "isHalt": True, "delayDeparture": 12},
            ],
        }
    }
    parsed = parse_train_payload(payload)
    assert parsed.current_delay_minutes == 12.0


def test_parse_unwraps_envelope():
    parsed = parse_train_payload({"success": True, "data": {"trainNumber": "1", "trainName": "X"}})
    assert parsed.train_number == "1"

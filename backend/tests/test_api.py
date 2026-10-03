"""End-to-end API tests over a seeded DEMO-mode database (no external calls)."""
from fastapi.testclient import TestClient  # noqa: F401 (ensures app import order)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["api_keys_exposed"] is False
    assert "RAILRADAR_API_KEY" not in r.text


def test_train_12637_is_seeded(client):
    r = client.get("/api/trains")
    assert r.status_code == 200
    numbers = [t["train_number"] for t in r.json()["trains"]]
    assert "12637" in numbers
    assert "12168" in numbers


def test_search_by_number_and_name(client):
    r = client.get("/api/trains/search", params={"q": "12637"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    assert any(t["train_name"] == "Pandian SF Express" for t in r.json()["trains"])

    r = client.get("/api/trains/search", params={"q": "pandian"})
    assert r.json()["count"] >= 1


def test_prediction_pipeline_contract(client):
    r = client.get("/api/trains/12637/prediction")
    assert r.status_code == 200
    body = r.json()
    assert body["train_number"] == "12637"
    pred = body["prediction"]
    # core formula: final = current + additional - recovery (floored at 0)
    expected = max(0.0, body["current_state"]["current_delay_minutes"]
                   + pred["predicted_additional_delay_minutes"] - pred["recovery_minutes"])
    assert abs(pred["final_predicted_delay_minutes"] - expected) < 0.01
    assert 45 <= pred["confidence"] <= 95
    assert pred["prediction_method"] in ("Rule-Based Prototype", "ML (synthetic training data)")
    assert pred["confidence_label"] == "Estimated confidence"
    assert isinstance(body["factors"], list) and len(body["factors"]) >= 1
    assert body["explanation"]
    assert body["data_mode"] == "DEMO"


def test_trajectory_shape(client):
    # the trajectory lives inside the /prediction response (its only source)
    r = client.get("/api/trains/12637/prediction")
    assert r.status_code == 200
    traj = r.json()["trajectory"]
    assert len(traj) >= 2
    kinds = {p["kind"] for p in traj}
    assert "predicted" in kinds
    assert all("delay_minutes" in p for p in traj)


def test_recovery_map_present(client):
    r = client.get("/api/trains/12637/prediction")
    body = r.json()
    assert isinstance(body["recovery_map"], list)
    for section in body["recovery_map"]:
        assert section["classification"] in ("HIGH", "MEDIUM", "LOW")
        assert section["recovery_potential_minutes"] >= 0


def test_weather_endpoint_never_crashes(client):
    r = client.get("/api/trains/12637/weather")
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["weather_risk_score"] <= 100


def test_unknown_train_404(client):
    assert client.get("/api/trains/00000/prediction").status_code == 404


def test_idle_train_serves_no_forecast(client, monkeypatch):
    # AUTO mode with a configured key: non-demo trains are IDLE -> the API
    # reports the frozen state but must NOT invent a forecast from stale data.
    from app.config import settings

    monkeypatch.setattr(settings, "data_mode", "AUTO")
    monkeypatch.setattr(settings, "railradar_api_key", "test-key", raising=False)

    r = client.get("/api/trains/12903/prediction")
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_available"] is False
    assert body["data_mode"] == "IDLE"
    assert body["prediction"]["final_predicted_delay_minutes"] is None
    assert body["prediction"]["confidence"] is None
    assert all(p["kind"] != "predicted" for p in body["trajectory"])


def test_events_retained(client):
    client.post("/api/trains/12637/refresh")

    r = client.get("/api/trains/12637/events")
    assert r.status_code == 200
    assert len(r.json()["events"]) >= 1


def test_refresh_endpoint_works_in_demo(client):
    r = client.post("/api/trains/12637/refresh")
    assert r.status_code == 200
    body = r.json()
    assert "prediction" in body
    assert "messages" in body

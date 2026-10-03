"""Per-train live-tracking switch + adding trains by number (no external calls)."""


def test_train_cards_expose_live_switch_state(client):
    r = client.get("/api/trains")
    assert r.status_code == 200
    for t in r.json()["trains"]:
        assert "live_enabled" in t
        assert isinstance(t["live_enabled"], bool)


def test_toggle_live_off_pauses_tracking(client):
    r = client.post("/api/trains/12637/live", json={"enabled": False})
    assert r.status_code == 200
    body = r.json()
    assert body["live_enabled"] is False
    assert "PAUSED" in body["message"]
    # prediction still served (demo replay)
    r = client.get("/api/trains/12637/prediction")
    assert r.status_code == 200


def test_toggle_live_on_switches_mode(client):
    r = client.post("/api/trains/12637/live", json={"enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["live_enabled"] is True
    assert "ENABLED" in body["message"]
    client.post("/api/trains/12637/live", json={"enabled": False})  # restore


def test_toggle_rejects_unknown_train(client):
    assert client.post("/api/trains/00000/live", json={"enabled": True}).status_code == 404


def test_effective_mode_follows_live_flag(monkeypatch):
    from app.config import settings
    from app.services.refresh_service import effective_mode

    monkeypatch.setattr(settings, "data_mode", "AUTO")
    monkeypatch.setattr(settings, "railradar_api_key", "test-key", raising=False)

    class FakeTrain:
        train_number = "12903"   # a normal (non-demo) train
        live_enabled = False

    # normal train, LIVE off → IDLE (real-data only, no simulation)
    assert effective_mode(None, FakeTrain()) == "IDLE"
    FakeTrain.live_enabled = True
    assert effective_mode(None, FakeTrain()) == "LIVE"

    # no API key → hard zero-call fallback: everything simulated
    monkeypatch.setattr(settings, "railradar_api_key", "", raising=False)
    assert effective_mode(None, FakeTrain()) == "DEMO"

    # DATA_MODE=DEMO stays a hard zero-call guarantee even with a key
    monkeypatch.setattr(settings, "railradar_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "data_mode", "DEMO")
    FakeTrain.live_enabled = True
    assert effective_mode(None, FakeTrain()) == "DEMO"

    # the designated demo train always has the demo option in AUTO mode
    monkeypatch.setattr(settings, "data_mode", "AUTO")
    FakeTrain.train_number = "12637"
    FakeTrain.live_enabled = False
    assert effective_mode(None, FakeTrain()) == "DEMO"


def test_scheduler_interval_backs_off_when_not_running(client):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Train
    from app.services.track_service import scheduler_interval_for

    db = SessionLocal()
    try:
        train = db.query(Train).filter(Train.train_number == "12168").first()
        interval = scheduler_interval_for(db, train)
        # 12168 is running → standard cadence
        assert interval == settings.poll_interval_seconds
        # simulate an idle (reached) train via its latest snapshot
        from app.models import TrainStateSnapshot

        snap = (
            db.query(TrainStateSnapshot)
            .filter(TrainStateSnapshot.train_id == train.id)
            .order_by(TrainStateSnapshot.timestamp.desc())
            .first()
        )
        snap.status = "reached"
        db.commit()
        assert scheduler_interval_for(db, train) == settings.poll_interval_seconds * 3
    finally:
        db.close()

"""All FastAPI routes. The frontend talks ONLY to these endpoints — external
APIs (RailRadar/OpenWeather) are reached exclusively by the backend."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Train, TrainStateSnapshot, WeatherSnapshot
from app.services import refresh_service, track_service
from app.services.event_service import recent_events
from app.services.prediction_service import run_prediction
from app.services.railradar_service import ExternalAPIError
from app.services.weather_service import _simulate, get_weather
from app.utils.serialize import to_jsonable
from app.utils.timeutil import aware_utc

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------
# Schemas (request bodies)
# --------------------------------------------------------------------------
class LiveToggleBody(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _train_or_404(db: Session, train_number: str) -> Train:
    train = db.query(Train).filter(Train.train_number == train_number).first()
    if train is None:
        raise HTTPException(status_code=404, detail=f"Train {train_number} not found.")
    return train


def _latest_snapshot(db: Session, train: Train) -> TrainStateSnapshot | None:
    snap = (
        db.query(TrainStateSnapshot)
        .filter(TrainStateSnapshot.train_id == train.id)
        .order_by(TrainStateSnapshot.timestamp.desc())
        .first()
    )
    if snap:
        snap.timestamp = aware_utc(snap.timestamp)
    return snap


def _latest_weather_snapshot(db: Session, train: Train) -> WeatherSnapshot | None:
    return (
        db.query(WeatherSnapshot)
        .filter(WeatherSnapshot.train_id == train.id)
        .order_by(WeatherSnapshot.timestamp.desc())
        .first()
    )


def _weather_mode(db: Session, train: Train) -> str:
    """Which weather source a train may use: live fetch (LIVE trains),
    simulated baseline (DEMO train / no key), or stored snapshot (IDLE)."""
    mode = refresh_service.effective_mode(db, train)
    if mode == "LIVE":
        return "live"
    return "demo" if mode == "DEMO" else "stored"


def _forecast_mode(db: Session, train: Train, snap: TrainStateSnapshot | None) -> bool:
    """IDLE trains get no forecast from stale data — but a recent live snapshot
    (e.g. right after 'Check live') is fresh enough to forecast from."""
    return refresh_service.should_forecast(
        train, snap, refresh_service.effective_mode(db, train)
    )


def _weather_payload(db: Session, train: Train) -> dict:
    """Serves cached/simulated weather WITHOUT spending an external call from
    a GET; only the refresh pipeline fetches live weather (TTL-guarded)."""
    stored = _latest_weather_snapshot(db, train)
    if stored is None:
        if refresh_service.effective_mode(db, train) == "DEMO":
            snap = _latest_snapshot(db, train)
            return _simulate("normal", snap.current_station_name if snap else None).to_dict()
        return {
            "location": None, "weather_condition": "Unavailable",
            "weather_risk_score": 0.0, "weather_risk_label": "NO DATA",
            "risk_reason": "no weather observation yet — trigger a refresh",
            "is_simulated": False, "source": "UNAVAILABLE",
        }
    return {
        "location": stored.location, "temperature": stored.temperature,
        "rainfall": stored.rainfall, "precipitation_probability": stored.precipitation_probability,
        "wind_speed": stored.wind_speed, "visibility": stored.visibility,
        "weather_condition": stored.weather_condition,
        "weather_risk_score": stored.weather_risk_score,
        "weather_risk_label": stored.weather_risk_label,
        "risk_reason": "last stored observation",
        "is_simulated": stored.is_simulated,
        "source": "CACHED" if not stored.is_simulated else "SIMULATED",
        "observed_at": stored.timestamp,
    }


# --------------------------------------------------------------------------
# System
# --------------------------------------------------------------------------
@router.get("/health")
def health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.query(Train).first()
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
        "data_mode_setting": settings.data_mode,
        "railradar_configured": settings.railradar_configured,
        "weather_configured": settings.weather_configured,
        "poll_interval_seconds": settings.poll_interval_seconds,
        "demo_time_scale": settings.demo_time_scale,
        "api_keys_exposed": False,
    }


# --------------------------------------------------------------------------
# Train listing / search
# --------------------------------------------------------------------------
def _train_card(db: Session, train: Train) -> dict:
    snap = _latest_snapshot(db, train)
    mode = refresh_service.effective_mode(db, train)
    return {
        "train_number": train.train_number,
        "train_name": train.train_name,
        "source_code": train.source_code, "source_name": train.source_name,
        "destination_code": train.destination_code, "destination_name": train.destination_name,
        "status": (snap.status if snap else train.status) or "unknown",
        "current_delay_minutes": (snap.current_delay_minutes or 0) if snap else 0,
        "location": snap.current_station_name if snap else None,
        "distance_km": train.scheduled_distance_km,
        "duration_minutes": train.scheduled_duration_minutes,
        "data_mode": mode,
        "live_enabled": bool(getattr(train, "live_enabled", False)),
        "simulated": mode == "DEMO",
        "last_updated": snap.timestamp if snap else train.updated_at,
    }


@router.get("/trains")
def list_trains(db: Session = Depends(get_db)):
    trains = db.query(Train).order_by(Train.train_number).all()
    return to_jsonable({"trains": [_train_card(db, t) for t in trains]})


@router.get("/trains/search")
def search_trains(
    q: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
):
    query = db.query(Train)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Train.train_number.ilike(like))
            | (Train.train_name.ilike(like))
            | (Train.source_name.ilike(like))
            | (Train.source_code.ilike(like))
            | (Train.destination_name.ilike(like))
            | (Train.destination_code.ilike(like))
        )
    trains = query.order_by(Train.train_number).all()
    cards = [_train_card(db, t) for t in trains]
    return to_jsonable({"trains": cards, "count": len(cards)})


@router.get("/trains/{train_number}")
def train_detail(train_number: str, db: Session = Depends(get_db)):
    train = _train_or_404(db, train_number)
    card = _train_card(db, train)
    card["total_halts"] = train.total_halts
    card["run_days"] = train.run_days
    card["category"] = train.category
    card["next_refresh_at"] = refresh_service.next_refresh_at(db, train)
    return to_jsonable(card)


@router.post("/trains/{train_number}/live")
def toggle_live_tracking(train_number: str, body: LiveToggleBody, db: Session = Depends(get_db)):
    """Per-train live switch: ON → scheduler refreshes this train from RailRadar
    every poll interval; OFF → train runs the free DEMO simulation."""
    train = _train_or_404(db, train_number)
    message = track_service.set_live_tracking(db, train, body.enabled)
    if body.enabled:
        try:
            result = refresh_service.refresh_train(db, train_number, force=True)
        except ExternalAPIError as exc:
            result = _recalc_current(db, train)
            result["messages"] = [f"Live tracking is ON but the first fetch failed: {exc}"]
    else:
        result = _recalc_current(db, train)
    result["message"] = message
    result["live_enabled"] = bool(train.live_enabled)
    return to_jsonable(result)


@router.get("/trains/{train_number}/state")
def train_state(train_number: str, db: Session = Depends(get_db)):
    train = _train_or_404(db, train_number)
    snap = _latest_snapshot(db, train)
    return to_jsonable({
        "train_number": train.train_number,
        "snapshot": {
            "timestamp": snap.timestamp if snap else None,
            "location": snap.current_station_name if snap else None,
            "current_sequence": snap.current_sequence if snap else None,
            "latitude": snap.latitude if snap else None,
            "longitude": snap.longitude if snap else None,
            "current_delay_minutes": snap.current_delay_minutes if snap else None,
            "current_speed_kmph": snap.current_speed_kmph if snap else None,
            "status": snap.status if snap else None,
            "distance_covered_km": snap.distance_covered_km if snap else None,
            "data_source": snap.data_source if snap else None,
        } if snap else None,
        "next_refresh_at": refresh_service.next_refresh_at(db, train),
        "poll_interval_seconds": settings.poll_interval_seconds,
        "effective_mode": refresh_service.effective_mode(db, train),
    })


@router.get("/trains/{train_number}/weather")
def train_weather(train_number: str, db: Session = Depends(get_db)):
    train = _train_or_404(db, train_number)
    return to_jsonable(_weather_payload(db, train))


@router.get("/trains/{train_number}/prediction")
def train_prediction(train_number: str, db: Session = Depends(get_db)):
    """Serves the latest prediction. GETs NEVER trigger external API calls —
    the backend refresh service alone spends quota."""
    train = _train_or_404(db, train_number)
    snap = _latest_snapshot(db, train)
    weather = get_weather(
        db, train.id,
        *_coords_for(db, train, snap),
        location=snap.current_station_name if snap else None,
        weather_mode=_weather_mode(db, train),
    )
    result = run_prediction(
        db, train, weather=weather, snapshot=snap, persist=False,
        forecast=_forecast_mode(db, train, snap),
    )
    result["live_enabled"] = bool(getattr(train, "live_enabled", False))
    result["next_refresh_at"] = refresh_service.next_refresh_at(db, train)
    return to_jsonable(result)


def _coords_for(db: Session, train: Train, snap):
    return refresh_service._current_coords(db, train, snap)


@router.get("/trains/{train_number}/events")
def train_events(train_number: str, limit: int = Query(default=25, ge=1, le=100), db: Session = Depends(get_db)):
    train = _train_or_404(db, train_number)
    events = recent_events(db, train.id, limit)
    return to_jsonable({
        "train_number": train.train_number,
        "events": [{"timestamp": e.timestamp, "type": e.event_type, "message": e.message,
                    "simulated": e.is_simulated} for e in events],
    })


# --------------------------------------------------------------------------
# Refresh
# --------------------------------------------------------------------------
@router.post("/trains/{train_number}/refresh")
def refresh(train_number: str, db: Session = Depends(get_db)):
    _train_or_404(db, train_number)
    try:
        result = refresh_service.refresh_train(db, train_number, force=True)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Train {train_number} not found.")
    return to_jsonable(result)


def _recalc_current(db: Session, train: Train) -> dict:
    """Recalculate the prediction from the latest snapshot (no external calls)."""
    snap = _latest_snapshot(db, train)
    weather = get_weather(
        db, train.id, *_coords_for(db, train, snap),
        location=snap.current_station_name if snap else None,
        weather_mode=_weather_mode(db, train),
    )
    return run_prediction(
        db, train, weather=weather, snapshot=snap, persist=True,
        forecast=_forecast_mode(db, train, snap),
    )

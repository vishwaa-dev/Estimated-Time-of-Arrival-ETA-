"""Per-train live-tracking control.

The user explicitly selects WHICH trains consume RailRadar quota:
  - POST /api/trains/{n}/live {enabled}   → switch live tracking on/off per train

Trains with live_enabled=True are refreshed by the background scheduler;
everything else shows its last real snapshot (or runs the DEMO replay for the
designated demo train).
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Train, TrainStateSnapshot
from app.services.event_service import add_event


def set_live_tracking(db: Session, train: Train, enabled: bool) -> str:
    """Flip the per-train live switch. The caller handles immediate recalculation."""
    train.live_enabled = enabled
    if enabled:
        message = (
            f"Live tracking ENABLED for {train.train_number} — refreshing from RailRadar "
            f"every {settings.poll_interval_seconds}s."
        )
    else:
        message = (
            f"Live tracking PAUSED for {train.train_number} — the train keeps showing "
            f"its last real snapshot until re-enabled."
        )
    add_event(db, train.id, "system", message)
    db.commit()
    return message


def scheduler_interval_for(db: Session, train: Train) -> int:
    """Polling cadence for a live-enabled train. Trains that are not actively
    running (not-started / reached) are checked 3x slower to protect quota."""
    interval = settings.poll_interval_seconds
    latest = (
        db.query(TrainStateSnapshot)
        .filter(TrainStateSnapshot.train_id == train.id)
        .order_by(TrainStateSnapshot.timestamp.desc())
        .first()
    )
    if latest is not None and latest.status in ("not-started", "reached", "unknown"):
        interval *= 3
    return interval

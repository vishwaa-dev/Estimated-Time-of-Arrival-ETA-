"""Event timeline — demonstrates continuous intelligence on the dashboard."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import EventLog
from app.utils.timeutil import utcnow


def add_event(
    db: Session,
    train_id: int,
    event_type: str,
    message: str,
    is_simulated: bool = False,
    timestamp: datetime | None = None,
) -> EventLog:
    event = EventLog(
        train_id=train_id,
        timestamp=timestamp or utcnow(),
        event_type=event_type,
        message=message,
        is_simulated=is_simulated,
    )
    db.add(event)
    return event


def recent_events(db: Session, train_id: int, limit: int = 25) -> list[EventLog]:
    return (
        db.query(EventLog)
        .filter(EventLog.train_id == train_id)
        .order_by(EventLog.timestamp.desc())
        .limit(limit)
        .all()
    )

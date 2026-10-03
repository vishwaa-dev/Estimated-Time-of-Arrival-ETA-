"""Time helpers. Railway times are IST (+05:30); snapshots are stored aware."""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

IST = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


def aware_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes that were stored as UTC — re-tag them."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_iso(value) -> datetime | None:
    """Robust ISO-8601 parser. Returns an aware datetime or None.

    Handles: '2026-09-02T21:40:00+05:30', naive strings, trailing 'Z',
    and junk/missing values without raising.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=IST)
    except ValueError:
        return None

"""Response serialisation: datetimes → IST ISO strings (+05:30), everything
JSON-safe. Guarantees no secret material ever enters a response."""
from datetime import datetime, timezone


def to_jsonable(obj):
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            from app.utils.timeutil import UTC

            obj = obj.replace(tzinfo=UTC)
        from app.utils.timeutil import to_ist

        return to_ist(obj).isoformat()
    if isinstance(obj, dict):
        return {key: to_jsonable(value) for key, value in obj.items()
                if not str(key).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)

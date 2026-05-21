from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc_now() -> str:
    return serialize_datetime_utc(utc_now())


def serialize_datetime_utc(value: Any) -> str:
    """
    Serialize a datetime for API/JSON as UTC ISO-8601 with Z suffix.
    Naive datetimes are assumed to be UTC (legacy webhook rows).
    """
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        if s.endswith("Z") or "+" in s[-6:] or (len(s) >= 5 and s[-5] in "+-"):
            return s
        return f"{s}Z" if "T" in s else s
    if not isinstance(value, datetime):
        return str(value)
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

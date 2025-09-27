import datetime as dt
from typing import Optional

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # fallback in case zoneinfo not available
    MOSCOW_TZ = dt.timezone(dt.timedelta(hours=3))


def to_moscow(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(MOSCOW_TZ)


def format_moscow(value: Optional[dt.datetime], fmt: str) -> str:
    local = to_moscow(value)
    return local.strftime(fmt) if local else ""

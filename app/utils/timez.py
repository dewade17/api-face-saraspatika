from datetime import datetime, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import current_app


def now_local() -> datetime:
    """Return the current time in the configured local timezone.

    The application defines a TIMEZONE string in its configuration (by
    default ``Asia/Makassar``).  This function attempts to construct a
    ``ZoneInfo`` with that key; if the key is not available (for
    example when the underlying system or tzdata package does not
    include that zone), it falls back to a naive ``datetime.now()``
    without any timezone information.  Downstream code typically
    strips the timezone with ``replace(tzinfo=None)`` anyway, so
    returning a naive datetime preserves existing behaviour when
    time zone data is missing.
    """
    tz_name = current_app.config.get("TIMEZONE", "Asia/Makassar")
    try:
        tz = ZoneInfo(tz_name)
        return datetime.now(tz)
    except ZoneInfoNotFoundError:
        # If the specified timezone is not available, fall back to a naive
        # datetime (system local time).  This avoids raising an error
        # during request processing.
        return datetime.now()

def today_local_date() -> date:
    """Return the current local date using ``now_local()``."""
    return now_local().date()

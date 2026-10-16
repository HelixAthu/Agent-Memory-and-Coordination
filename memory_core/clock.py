"""Injectable system clock supporting frozen test time via CLOCK_NOW env var."""

from __future__ import annotations

import datetime
import os


def now() -> int:
    """Return the current epoch timestamp in integer seconds.

    If CLOCK_NOW is set (as an ISO-8601 string or numeric timestamp), that frozen time is returned.
    """
    env_clock = os.getenv("CLOCK_NOW", "").strip()
    if env_clock:
        try:
            # Try float/int timestamp first
            return int(float(env_clock))
        except ValueError:
            # Parse ISO string
            dt = datetime.datetime.fromisoformat(env_clock.replace("Z", "+00:00"))
            return int(dt.timestamp())
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def now_ms() -> int:
    """Return the current epoch timestamp in integer milliseconds."""
    env_clock = os.getenv("CLOCK_NOW", "").strip()
    if env_clock:
        try:
            return int(float(env_clock) * 1000)
        except ValueError:
            dt = datetime.datetime.fromisoformat(env_clock.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


def to_iso(ts_seconds: int) -> str:
    """Convert an epoch second integer to standard ISO-8601 UTC string."""
    dt = datetime.datetime.fromtimestamp(ts_seconds, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

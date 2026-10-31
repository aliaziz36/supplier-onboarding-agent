"""The only source of 'today'. FAKE_NOW (env) or set_now() override real time.

Eval runs pin the clock to each case's as_of date so results do not drift
with the calendar; the dashboard's fast-forward button calls set_now().
"""
import os
import threading
import time
from datetime import date, datetime, timedelta

_override: date | None = None       # process-wide (dashboard fast-forward)
_local = threading.local()          # per-thread (parallel eval cases)
_display: tuple[datetime, float] | None = None   # dashboard demo clock: (start time, monotonic origin)


def _parse(value: str) -> date:
    return datetime.fromisoformat(value.strip()).date()


def today() -> date:
    if getattr(_local, "override", None) is not None:
        return _local.override
    if _override is not None:
        return _override
    fake = os.getenv("FAKE_NOW", "").strip()
    return _parse(fake) if fake else date.today()


def now_iso() -> str:
    """Timestamp for event rows: the demo clock when set, else the (possibly fake) date plus real wall time."""
    if _display is not None:
        return display_now().isoformat(timespec="seconds")
    return f"{today().isoformat()}T{datetime.now().strftime('%H:%M:%S.%f')}"


def set_display(value: datetime | str | None) -> None:
    """Start the dashboard's demo clock at `value`; it then runs forward in real seconds.

    Only timestamps use it. The agent's 'today' stays the case's as_of date, so replayed
    model calls see exactly the input they were recorded with."""
    global _display
    if value is None:
        _display = None
    else:
        _display = (datetime.fromisoformat(value) if isinstance(value, str) else value, time.monotonic())


def display_now() -> datetime | None:
    if _display is None:
        return None
    start, origin = _display
    return start + timedelta(seconds=time.monotonic() - origin)


def set_now(value: date | str | None) -> None:
    global _override
    _override = _parse(value) if isinstance(value, str) else value


def set_thread_now(value: date | str | None) -> None:
    _local.override = _parse(value) if isinstance(value, str) else value

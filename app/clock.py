"""The only source of 'today'. FAKE_NOW (env) or set_now() override real time.

Eval runs pin the clock to each case's as_of date so results do not drift
with the calendar; the dashboard's fast-forward button calls set_now().
"""
import os
from datetime import date, datetime

_override: date | None = None


def _parse(value: str) -> date:
    return datetime.fromisoformat(value.strip()).date()


def today() -> date:
    if _override is not None:
        return _override
    fake = os.getenv("FAKE_NOW", "").strip()
    return _parse(fake) if fake else date.today()


def now_iso() -> str:
    """Timestamp for event rows: the (possibly fake) date plus real wall time."""
    return f"{today().isoformat()}T{datetime.now().strftime('%H:%M:%S.%f')}"


def set_now(value: date | str | None) -> None:
    global _override
    _override = _parse(value) if isinstance(value, str) else value

"""Regression suite: replays cases from the committed model cache (REPLAY=1, no API key).

Holds the 5 demo cases plus every dev case that ever failed. A case is never
removed; it is fixed or listed in KNOWN_LIMITATIONS with a reason.
"""
import os

import pytest

os.environ["REPLAY"] = "1"

from app.config import CASES_DIR, load_policy  # noqa: E402
from eval import metrics  # noqa: E402
from eval.run import eval_case  # noqa: E402

POLICY = load_policy()
DEMO = sorted(p.parent.name for p in (CASES_DIR / "demo").glob("*/label.json"))
FAILED_ONCE: list[str] = [          # dev case ids, appended by each fix round
    "dev_006_clean",                 # ambiguous DD/MM date -> low confidence -> escalated
    "dev_025_missing",               # Gregorian date labelled Hijri -> unknown expiry -> escalated
    "dev_010_clean",                 # one-digit CR misread on Arabic scan -> registry miss -> escalated
    "dev_026_missing",               # IBAN misread on scanned bank letter (decision right, field wrong)
]
KNOWN_LIMITATIONS: dict[str, str] = {}

CASES = [("demo", c) for c in DEMO] + [("dev", c) for c in FAILED_ONCE]


@pytest.mark.parametrize("split,case_id", CASES, ids=[c for _, c in CASES])
def test_case_replays_correctly(split, case_id):
    if case_id in KNOWN_LIMITATIONS:
        pytest.xfail(KNOWN_LIMITATIONS[case_id])
    row = eval_case(CASES_DIR / split / case_id, POLICY, "hybrid", [])
    assert row["error"] is None, row["error"]
    assert metrics.case_correct(row), (row["expected"], row["got_first"], row["docs_got"], row["flags_got"])

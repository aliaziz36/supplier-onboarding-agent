"""Expiry watch is deterministic: every expiring case must end in a renewal request for the right document."""
import json

import pytest

from app import db
from app.agent import run_case
from app.config import CASES_DIR, load_policy

POLICY = load_policy()
CASE_DIRS = sorted(p.parent for split in ("dev", "demo") for p in (CASES_DIR / split).glob("*expir*/label.json")
                   if json.loads(p.read_text())["kind"] == "expiry")


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_expiry_scan(case_dir):
    r = run_case(db.connect(":memory:"), case_dir, POLICY)
    assert r["final"]["decision"] == "renewal_request"
    assert r["final"]["documents_requested"] == r["label"]["expected_documents_requested"]
    assert r["final"]["vendor_status"] == "at_risk"

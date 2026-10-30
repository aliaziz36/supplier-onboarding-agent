"""Key-free test of the deterministic layer.

Feeds each case's ground-truth extractions (from label.json) into checks.py and
bank_guard.py. If these fail, the rules are wrong, not the model.
Runs on dev and demo only; never on held-out.
"""
import json
from datetime import date
from email.utils import parseaddr
from pathlib import Path

import pytest

from app import cases
from app.bank_guard import check_bank_change
from app.checks import run_checks
from app.config import CASES_DIR, load_policy
from app.registry import Registry, load_world

POLICY = load_policy()
CASE_DIRS = sorted(p.parent for split in ("dev", "demo") for p in (CASES_DIR / split).glob("*/label.json"))


def oracle_docs(label: dict) -> list[dict]:
    docs = []
    for i, (fname, t) in enumerate(label["attachments"].items()):
        ex = {"doc_type": t["doc_type"], "legible": t.get("legible", True),
              "company_name": t.get("company_name"), "company_name_ar": t.get("company_name_ar"),
              "cr_number": t.get("cr_number"), "vat_number": t.get("vat_number"), "iban": t.get("iban"),
              "account_name": t.get("account_name"), "expiry_date_iso": t.get("expiry_date"),
              "contains_instructions": t.get("contains_instructions", False),
              "instructions_text": "embedded instruction" if t.get("contains_instructions") else None,
              "confidence": {}}
        docs.append({"id": f"d{i}", "filename": fname, "received_at": str(i), "extraction": ex})
    return docs


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_rules_on_perfect_extraction(case_dir: Path):
    label = json.loads((case_dir / "label.json").read_text())
    world = load_world(case_dir)
    reg = Registry()
    reg.add_world(world)
    if label["kind"] == "onboarding":
        s = run_checks(oracle_docs(label), reg, POLICY, date.fromisoformat(label["as_of"]))
        assert s["recommended"] == label["expected_decision"], s["risk"] + s["fixable"]
        if label["expected_decision"] == "request_fix":
            assert s["documents_to_request"] == sorted(label["expected_documents_requested"])
    elif label["kind"] == "bank_change":
        sender = cases.parse_eml(case_dir / "email.eml")["sender"]
        f = label["expected_fields"]
        g = check_bank_change(world["vendor_on_file"], f["new_iban"], f["account_name"], sender, POLICY)
        assert sorted(g["flags"]) == sorted(label["expected_flags"])
    else:
        pytest.skip("expiry cases are covered by test_watcher")

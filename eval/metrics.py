"""Metrics over per-case rows produced by eval/run.py. Definitions match docs/PLAN.md section 7b.

A row: {case_id, scenario, kind, perturbations, fraud, expected, got_first, got_final, expected_final,
        docs_expected, docs_got, flags_expected, flags_got, fields: [{field, ok}], tokens_in, tokens_out,
        seconds, error}
"""
from collections import defaultdict

PRICE_IN, PRICE_OUT = 2.00 / 1e6, 10.00 / 1e6   # claude-sonnet-5-5, $ per token


def case_correct(r: dict) -> bool:
    if r.get("error"):
        return False
    ok = r["got_first"] == r["expected"]
    if r.get("expected_final"):
        ok = ok and r["got_final"] == r["expected_final"]
    if r["expected"] == "request_fix":
        ok = ok and r["docs_got"] == r["docs_expected"]
    if r["kind"] == "bank_change":
        ok = ok and sorted(r["flags_got"]) == sorted(r["flags_expected"])
    return ok


def fraud_caught(r: dict) -> bool:
    """A fraud case counts as caught if it was not onboarded / not applied, and (for spoofed bank
    changes) it was frozen with at least one red flag shown to the human."""
    if r.get("error"):
        return False
    if r["kind"] == "bank_change":
        return r["got_first"] == "freeze" and len(r["flags_got"]) > 0
    return r["got_first"] in ("escalate", "request_fix") and r["got_final"] != "onboard"


def _rate(num, den):
    return round(num / den, 4) if den else None


def compute(rows: list[dict]) -> dict:
    n = len(rows)
    correct = [case_correct(r) for r in rows]
    fraud = [r for r in rows if r["fraud"]]
    benign_onb = [r for r in rows if r["kind"] == "onboarding" and r["expected"] in ("onboard", "request_fix")]
    fix_cases = [r for r in rows if r["expected"] == "request_fix" and r["got_first"] == "request_fix"]
    genuine = [r for r in rows if r["kind"] == "bank_change" and not r["fraud"]]
    fields = [f for r in rows for f in r.get("fields", [])]
    human = [r for r in rows if r["got_first"] in ("escalate", "freeze")]
    tin = sum(r.get("tokens_in", 0) for r in rows)
    tout = sum(r.get("tokens_out", 0) for r in rows)
    m = {
        "cases": n,
        "decision_accuracy": _rate(sum(correct), n),
        "fraud_recall": _rate(sum(fraud_caught(r) for r in fraud), len(fraud)),
        "fraud_missed": [r["case_id"] for r in fraud if not fraud_caught(r)],
        "false_escalation_rate": _rate(sum(r["got_first"] == "escalate" for r in benign_onb), len(benign_onb)),
        "genuine_bank_change_false_flag_rate": _rate(sum(bool(r["flags_got"]) for r in genuine), len(genuine)),
        "field_accuracy": _rate(sum(f["ok"] for f in fields), len(fields)),
        "field_accuracy_by_field": {},
        "follow_up_precision": _rate(sum(r["docs_got"] == r["docs_expected"] for r in fix_cases), len(fix_cases)),
        "human_touches_per_case": _rate(len(human), n),
        "errors": [r["case_id"] for r in rows if r.get("error")],
        "tokens_in": tin, "tokens_out": tout,
        "cost_usd_per_case": round((tin * PRICE_IN + tout * PRICE_OUT) / n, 4) if n else None,
        "seconds_per_case": round(sum(r.get("seconds", 0) for r in rows) / n, 2) if n else None,
    }
    by_field = defaultdict(list)
    for f in fields:
        by_field[f["field"]].append(f["ok"])
    m["field_accuracy_by_field"] = {k: _rate(sum(v), len(v)) for k, v in sorted(by_field.items())}
    m["by_scenario"] = breakdown(rows, lambda r: [r["scenario"]])
    m["by_perturbation"] = breakdown(rows, lambda r: r["perturbations"] or ["none"])
    m["by_input"] = breakdown(rows, input_bucket)
    return m


def input_bucket(r: dict) -> list[str]:
    """clean digital vs scanned vs Arabic (a case can be both scanned and Arabic)."""
    p = set(r["perturbations"])
    out = [b for b in ("scanned", "arabic") if b in p]
    return out or ["digital"]


def breakdown(rows, keys_fn) -> dict:
    groups = defaultdict(list)
    for r in rows:
        for k in keys_fn(r):
            groups[k].append(r)
    return {k: {"n": len(v), "accuracy": _rate(sum(case_correct(r) for r in v), len(v))}
            for k, v in sorted(groups.items())}

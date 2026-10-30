"""Run the agent over a split and score it.

    python -m eval.run --split dev --mode hybrid --note "first run"
    python -m eval.run --split dev --ablate crossdoc
    REPLAY=1 python -m eval.run --split dev        # from cache, no API key

Writes results/<run-id>.json and appends a row to results/LOG.md.
"""
import argparse
import json
import os
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app import cases, checks, db
from app.agent import run_case
from app.config import CASES_DIR, MODEL, RESULTS_DIR, load_policy
from app.saudi import normalize_iban
from eval import metrics

FIELDS_BY_TYPE = {
    "commercial_registration": ["company_name", "cr_number", "expiry_date"],
    "vat_certificate": ["vat_number", "expiry_date"],
    "bank_letter": ["iban", "account_name"],
    "gosi_certificate": ["expiry_date"],
    "zakat_certificate": ["expiry_date"],
}


def _same(field, got, want, policy) -> bool:
    if want is None:
        return True
    if got is None:
        return False
    if field in ("company_name", "account_name"):
        return checks.normalize_name(got, policy) == checks.normalize_name(want, policy)
    if field == "iban":
        return normalize_iban(got) == normalize_iban(want)
    return str(got).strip() == str(want).strip()


def field_rows(conn, case_dir: Path, label: dict, policy) -> list[dict]:
    truth = dict(label.get("attachments", {}))
    for rd in sorted((case_dir / "replies").glob("*")) if (case_dir / "replies").exists() else []:
        truth.update(json.loads((rd / "truth.json").read_text()))
    out = []
    for d in cases.case_documents(conn, label["case_id"]):
        t, ex = truth.get(d["filename"]), d["extraction"]
        if not t or not ex or t.get("doc_type") == "other":
            if t and ex and t.get("doc_type") == "other":
                out.append({"field": "doc_type", "ok": ex.get("doc_type") == "other"})
            continue
        out.append({"field": "doc_type", "ok": ex.get("doc_type") == t["doc_type"]})
        if not t.get("legible", True):
            out.append({"field": "legible_flag", "ok": ex.get("legible") is False})
            continue
        for f in FIELDS_BY_TYPE.get(t["doc_type"], []):
            if f == "company_name":
                want = t.get("company_name") or t.get("company_name_ar")
                got = ex.get("company_name") if t.get("company_name") else ex.get("company_name_ar")
            elif f == "expiry_date":
                want, got = t.get("expiry_date"), ex.get("expiry_date_iso")
            else:
                want, got = t.get(f), ex.get(f)
            out.append({"field": f, "ok": _same(f, got, want, policy)})
    if label["kind"] == "bank_change":
        bc = db.row(conn, "SELECT new_iban FROM bank_changes WHERE case_id=?", label["case_id"])
        out.append({"field": "new_iban", "ok": bool(bc) and _same("iban", bc["new_iban"], label["expected_fields"]["new_iban"], policy)})
    return out


def eval_case(case_dir: Path, policy: dict, mode: str, ablate: list) -> dict:
    label = json.loads((case_dir / "label.json").read_text())
    conn = db.connect(":memory:")
    started = time.time()
    row = {"case_id": label["case_id"], "scenario": label["scenario"], "kind": label["kind"],
           "perturbations": label["perturbations"], "fraud": label["fraud"],
           "expected": label["expected_decision"], "expected_final": label.get("expected_final_decision"),
           "docs_expected": sorted(label["expected_documents_requested"]),
           "flags_expected": sorted(label["expected_flags"]), "error": None}
    try:
        r = run_case(conn, case_dir, policy, mode=mode, ablate=ablate)
        first, final = r["first"], r["final"]
        row.update(got_first=first["decision"], got_final=final["decision"],
                   docs_got=first["documents_requested"], flags_got=sorted(first["flags"]),
                   escalation_reason=first.get("escalation_reason"),
                   fields=field_rows(conn, case_dir, label, policy))
    except Exception as e:
        row.update(got_first="error", got_final="error", docs_got=[], flags_got=[], fields=[],
                   error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-1500:])
    ev = db.rows(conn, "SELECT kind, name, summary, tokens_in, tokens_out, cached FROM events ORDER BY id")
    row["tokens_in"] = sum(e["tokens_in"] for e in ev)
    row["tokens_out"] = sum(e["tokens_out"] for e in ev)
    row["llm_calls"] = sum(e["kind"] == "llm" for e in ev)
    row["cache_hits"] = sum(e["kind"] == "llm" and e["cached"] for e in ev)
    row["tool_trace"] = [f"{e['name']}{' REFUSED' if (e['summary'] or '').startswith('REFUSED') else ''}"
                         for e in ev if e["kind"] == "tool"]
    row["seconds"] = round(time.time() - started, 2)
    row["correct"] = metrics.case_correct(row)
    return row


def append_log(run_id: str, args, m: dict):
    log = RESULTS_DIR / "LOG.md"
    if not log.exists():
        log.write_text("# Iteration log\n\nOne row per change. Dev set unless noted. Numbers come from "
                       "`results/<run-id>.json`.\n\n"
                       "| Date | Run id | Change | Split | Mode | Ablate | Decision acc | Fraud recall | "
                       "False escalation | Field acc | Follow-up precision | Human touches/case | $/case |\n"
                       "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"
    with log.open("a") as f:
        f.write(f"| {datetime.now():%Y-%m-%d %H:%M} | {run_id} | {args.note or ''} | {args.split} | {args.mode} | "
                f"{args.ablate or '-'} | {pct(m['decision_accuracy'])} | {pct(m['fraud_recall'])} | "
                f"{pct(m['false_escalation_rate'])} | {pct(m['field_accuracy'])} | {pct(m['follow_up_precision'])} | "
                f"{m['human_touches_per_case']} | {m['cost_usd_per_case']} |\n")


def print_report(m: dict, rows: list[dict]):
    pct = lambda v: "  n/a" if v is None else f"{v * 100:5.1f}%"
    print(f"\nDecision accuracy  {pct(m['decision_accuracy'])}   ({m['cases']} cases)")
    print(f"Fraud recall       {pct(m['fraud_recall'])}   missed: {m['fraud_missed'] or 'none'}")
    print(f"False escalation   {pct(m['false_escalation_rate'])}")
    print(f"Field accuracy     {pct(m['field_accuracy'])}   {m['field_accuracy_by_field']}")
    print(f"Follow-up prec.    {pct(m['follow_up_precision'])}")
    print(f"Human touches/case {m['human_touches_per_case']}   cost/case ${m['cost_usd_per_case']}   "
          f"time/case {m['seconds_per_case']}s   errors: {m['errors'] or 'none'}")
    for title, key in (("scenario", "by_scenario"), ("perturbation", "by_perturbation"), ("input", "by_input")):
        print(f"\nBy {title}:")
        for k, v in m[key].items():
            print(f"  {k:22s} n={v['n']:3d}  acc {pct(v['accuracy'])}")
    wrong = [r for r in rows if not r["correct"]]
    if wrong:
        print("\nFailures:")
        for r in wrong:
            extra = r["error"] or f"docs {r['docs_got']} vs {r['docs_expected']}; flags {r['flags_got']} vs {r['flags_expected']}"
            print(f"  {r['case_id']:40s} expected {r['expected']:12s} got {r['got_first']:12s} {extra}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "dev_zakat", "demo", "heldout"])
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "rules", "model"])
    ap.add_argument("--ablate", default="", help="comma list: crossdoc,registry")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", default="", help="substring filter on case id")
    ap.add_argument("--note", default="", help="what changed, for LOG.md")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--frozen", action="store_true", help="required for --split heldout")
    args = ap.parse_args()
    if args.split == "heldout" and not args.frozen:
        raise SystemExit("Held-out runs only after freeze. Pass --frozen once the system is frozen.")

    os.environ.setdefault("STORE_DIR", tempfile.mkdtemp(prefix="store_"))
    cases.STORE_DIR = Path(os.environ["STORE_DIR"])
    policy = load_policy()
    ablate = [a for a in args.ablate.split(",") if a]
    dirs = sorted(p.parent for p in (CASES_DIR / args.split).glob("*/label.json") if args.only in p.parent.name)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda d: eval_case(d, policy, args.mode, ablate), dirs))
    m = metrics.compute(rows)
    run_id = f"{args.split}-{args.mode}{'-no-' + '-no-'.join(ablate) if ablate else ''}-{datetime.now():%m%d-%H%M%S}"
    out = {"run_id": run_id, "split": args.split, "mode": args.mode, "ablate": ablate, "model": MODEL,
           "replay": os.getenv("REPLAY", "0"), "policy_version": policy.get("version"),
           "policy_path": os.getenv("POLICY_PATH", "policy.yaml"), "note": args.note,
           "wall_seconds": round(time.time() - started, 1), "metrics": m, "cases": rows}
    RESULTS_DIR.mkdir(exist_ok=True)
    if not args.only:
        (RESULTS_DIR / f"{run_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        if not args.no_log:
            append_log(run_id, args, m)
    print_report(m, rows)
    print(f"\nrun {run_id}  ({out['wall_seconds']}s)")


if __name__ == "__main__":
    main()

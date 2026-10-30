"""Expiry watch: scan every vendor's documents against clock.today().

Deterministic by design: dates and thresholds must be exact, and the renewal
email is a template. Expiring within the window -> renewal email + at_risk.
Already expired -> payment hold + notice to the manager.
"""
from datetime import date

from app import clock, db

DOC_LABELS = {
    "commercial_registration": "Commercial Registration (CR)",
    "vat_certificate": "VAT registration certificate",
    "gosi_certificate": "GOSI / Nitaqat certificate",
    "zakat_certificate": "Zakat certificate",
    "bank_letter": "bank account confirmation letter",
}


def scan_expiries(conn, policy: dict, today: date | None = None) -> list[dict]:
    today = today or clock.today()
    window = policy["expiry_watch"]["renewal_notice_days"]
    found = []
    for r in db.rows(conn, "SELECT vd.vendor_id, vd.doc_type, vd.expiry_date, v.name, v.email, v.status"
                           " FROM vendor_documents vd JOIN vendors v ON v.id = vd.vendor_id"
                           " WHERE vd.expiry_date IS NOT NULL ORDER BY vd.vendor_id, vd.doc_type"):
        days = (date.fromisoformat(r["expiry_date"]) - today).days
        if days < 0:
            found.append({**r, "days_left": days, "state": "expired"})
        elif days <= window:
            found.append({**r, "days_left": days, "state": "expiring"})
    return found


def run_scan(conn, policy: dict, today: date | None = None) -> list[dict]:
    today = today or clock.today()
    findings = scan_expiries(conn, policy, today)
    db.log_event(conn, kind="tool", name="scan_expiries", input={"date": str(today)},
                 output=[{k: f[k] for k in ("vendor_id", "doc_type", "expiry_date", "days_left", "state")} for f in findings],
                 summary=f"Expiry scan for {today}: {len(findings)} document(s) need attention")
    for vendor_id in sorted({f["vendor_id"] for f in findings}):
        mine = [f for f in findings if f["vendor_id"] == vendor_id]
        expired = [f for f in mine if f["state"] == "expired"]
        expiring = [f for f in mine if f["state"] == "expiring"]
        v = mine[0]
        if expiring:
            docs = [f["doc_type"] for f in expiring]
            lines = "\n".join(f"- {DOC_LABELS.get(f['doc_type'], f['doc_type'])}: expires {f['expiry_date']}"
                              f" ({f['days_left']} days)" for f in expiring)
            body = (f"Dear {v['name']} team,\n\nOur records show the following document(s) expire soon:\n{lines}\n\n"
                    "Please reply to this email with the renewed copy before the expiry date so that payments"
                    " continue without interruption.\n\nThank you,\nSupplier Onboarding")
            conn.execute("INSERT INTO emails (vendor_id, direction, sender, to_addr, subject, body, kind,"
                         " documents_requested, ts) VALUES (?,?,?,?,?,?,?,?,?)",
                         (vendor_id, "out", "onboarding@buyer-company.sa", v["email"],
                          "Renewal needed: document expiring soon", body, "renewal", db.dumps(docs), clock.now_iso()))
            if not expired:
                conn.execute("UPDATE vendors SET status='at_risk' WHERE id=? AND status='active'", (vendor_id,))
            conn.commit()
            db.log_event(conn, kind="tool", name="send_email", vendor_id=vendor_id,
                         input={"to": v["email"], "kind": "renewal", "documents_requested": docs},
                         summary=f"Renewal request sent to {v['name']} for {', '.join(docs)}; vendor marked at risk")
        if expired and policy["expiry_watch"].get("hold_payments_on_expiry", True):
            docs = [f["doc_type"] for f in expired]
            set_vendor_hold(conn, vendor_id, True, f"expired: {', '.join(docs)}")
    return findings


def set_vendor_hold(conn, vendor_id: str, on: bool, reason: str) -> dict:
    conn.execute("UPDATE vendors SET status=?, hold_reason=? WHERE id=?",
                 ("on_hold" if on else "active", reason if on else None, vendor_id))
    conn.commit()
    db.log_event(conn, kind="tool", name="set_vendor_hold", vendor_id=vendor_id,
                 input={"on": on, "reason": reason},
                 summary=f"Payment hold {'ON' if on else 'OFF'} for {vendor_id}: {reason}")
    return {"vendor_id": vendor_id, "status": "on_hold" if on else "active"}

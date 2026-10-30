"""Case store helpers: ingest an .eml, seed vendors on file, read a case's outcome."""
import email
import hashlib
import json
import os
from email import policy as email_policy
from email.utils import parseaddr
from pathlib import Path

from app import clock, db
from app.config import ROOT

STORE_DIR = Path(os.getenv("STORE_DIR", ROOT / "data" / "store"))


def parse_eml(path: Path) -> dict:
    msg = email.message_from_bytes(Path(path).read_bytes(), policy=email_policy.default)
    name, addr = parseaddr(msg["From"])
    body = msg.get_body(preferencelist=("plain",))
    attachments = []
    for part in msg.iter_attachments():
        attachments.append((part.get_filename(), part.get_payload(decode=True)))
    return {"sender_name": name, "sender": addr.lower(), "subject": str(msg["Subject"] or ""),
            "body": body.get_content() if body else "", "attachments": attachments}


def ingest_email(conn, eml_path: Path, case_id: str, store_dir: Path | None = None) -> int:
    """Store an inbound email and its PDF attachments. Creates the case if new."""
    e = parse_eml(eml_path)
    if not db.row(conn, "SELECT id FROM cases WHERE id=?", case_id):
        conn.execute("INSERT INTO cases (id, kind, supplier_name, sender_email, status, case_dir, created_at, updated_at)"
                     " VALUES (?,?,?,?,?,?,?,?)",
                     (case_id, "email", e["sender_name"], e["sender"], "received", str(Path(eml_path).parent),
                      clock.now_iso(), clock.now_iso()))
    else:
        db.set_case_status(conn, case_id, "received")
    cur = conn.execute("INSERT INTO emails (case_id, direction, sender, to_addr, subject, body, kind, ts)"
                       " VALUES (?,?,?,?,?,?,?,?)",
                       (case_id, "in", e["sender"], "onboarding@buyer-company.sa", e["subject"], e["body"],
                        "inbound", clock.now_iso()))
    email_id = cur.lastrowid
    folder = Path(store_dir or STORE_DIR) / case_id
    folder.mkdir(parents=True, exist_ok=True)
    n = db.row(conn, "SELECT COUNT(*) AS n FROM documents WHERE case_id=?", case_id)["n"]
    for fname, data in e["attachments"]:
        if not fname or not fname.lower().endswith(".pdf"):
            continue
        n += 1
        doc_id = f"{case_id}#d{n}"
        path = folder / f"{email_id}_{fname}"
        path.write_bytes(data)
        conn.execute("INSERT INTO documents (id, case_id, email_id, filename, path, sha256, received_at)"
                     " VALUES (?,?,?,?,?,?,?)",
                     (doc_id, case_id, email_id, fname, str(path), hashlib.sha256(data).hexdigest(), clock.now_iso()))
    conn.commit()
    db.log_event(conn, kind="system", name="email_received", case_id=case_id,
                 summary=f"Email from {e['sender']}: {e['subject']} ({len(e['attachments'])} attachments)")
    return email_id


def seed_vendor(conn, vendor: dict | None) -> None:
    """Load a vendor that already exists in the buyer's system (guard scenarios)."""
    if not vendor:
        return
    conn.execute("INSERT OR REPLACE INTO vendors (id, name, name_ar, cr_number, vat_number, iban, bank_code,"
                 " account_name, email, email_domain, phone, status, created_at)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (vendor["vendor_id"], vendor["name"], vendor.get("name_ar"), vendor["cr_number"],
                  vendor.get("vat_number"), vendor["iban"], vendor["bank_code"], vendor["account_name"],
                  vendor["email"], vendor["email_domain"], vendor["phone"], "active", clock.now_iso()))
    for t, exp in (vendor.get("documents") or {}).items():
        conn.execute("INSERT OR REPLACE INTO vendor_documents (vendor_id, doc_type, expiry_date) VALUES (?,?,?)",
                     (vendor["vendor_id"], t, exp))
    conn.commit()


def case_documents(conn, case_id: str) -> list[dict]:
    docs = db.rows(conn, "SELECT * FROM documents WHERE case_id=? ORDER BY received_at, id", case_id)
    for d in docs:
        d["extraction"] = json.loads(d["extraction"]) if d["extraction"] else None
    return docs


def outcome(conn, case_id: str | None = None, vendor_id: str | None = None) -> dict:
    """What the system actually did, read back from the store (used by eval and dashboard)."""
    out = {"decision": "none", "documents_requested": [], "flags": [], "vendor_status": None}
    if case_id:
        case = db.row(conn, "SELECT * FROM cases WHERE id=?", case_id) or {}
        out["status"] = case.get("status")
        bc = db.row(conn, "SELECT * FROM bank_changes WHERE case_id=? ORDER BY id DESC", case_id)
        applied = db.row(conn, "SELECT * FROM bank_changes WHERE case_id=? AND status='applied'", case_id)
        emails = db.rows(conn, "SELECT * FROM emails WHERE case_id=? AND direction='out' ORDER BY id", case_id)
        cards = db.rows(conn, "SELECT * FROM decision_cards WHERE case_id=? ORDER BY id", case_id)
        vendor = db.row(conn, "SELECT * FROM vendors WHERE case_id=?", case_id)
        if applied:
            out["decision"] = "bank_change_applied"
        elif vendor:
            out["decision"] = "onboard"
            out["vendor_id"] = vendor["id"]
        elif bc:
            out["decision"] = "freeze"
            out["flags"] = json.loads(bc["flags"] or "[]")
        elif cards or case.get("status") == "escalated":
            out["decision"] = "escalate"
            out["escalation_reason"] = cards[-1]["reason"] if cards else None
        elif any(e["kind"] == "request_fix" for e in emails):
            out["decision"] = "request_fix"
        last_req = [e for e in emails if e["kind"] == "request_fix"]
        if last_req:
            out["documents_requested"] = sorted(json.loads(last_req[-1]["documents_requested"] or "[]"))
    if vendor_id:
        v = db.row(conn, "SELECT * FROM vendors WHERE id=?", vendor_id) or {}
        out["vendor_status"] = v.get("status")
        renewals = db.rows(conn, "SELECT * FROM emails WHERE vendor_id=? AND kind='renewal' ORDER BY id", vendor_id)
        if renewals and out["decision"] == "none":
            out["decision"] = "renewal_request"
            out["documents_requested"] = sorted({t for e in renewals for t in json.loads(e["documents_requested"] or "[]")})
        elif v.get("status") == "on_hold" and out["decision"] == "none":
            out["decision"] = "hold"
    return out

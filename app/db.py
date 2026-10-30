"""SQLite store: cases, documents, emails, events, vendors, bank changes, decision cards.

The events table is the audit log; the dashboard and the metrics read only it
(plus the final state tables for convenience).
"""
import json
import sqlite3
from pathlib import Path

from app import clock
from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                 -- onboarding | bank_change | expiry
    supplier_name TEXT,
    sender_email TEXT,
    status TEXT NOT NULL,               -- received | reading | checking | waiting_on_supplier
                                        -- | onboarded | escalated | approved | rejected | frozen | closed
    follow_ups INTEGER NOT NULL DEFAULT 0,
    vendor_id TEXT,
    case_dir TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    email_id INTEGER,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    extraction TEXT,                    -- JSON from extract.py
    received_at TEXT
);
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT,
    vendor_id TEXT,
    direction TEXT NOT NULL,            -- in | out
    sender TEXT, to_addr TEXT, subject TEXT, body TEXT,
    kind TEXT,                          -- inbound | request_fix | welcome | renewal | notice
    documents_requested TEXT,           -- JSON list, structured for follow-up precision
    ts TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT, vendor_id TEXT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- tool | reasoning | llm | system
    name TEXT,
    input TEXT, output TEXT, summary TEXT,
    tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
    cached INTEGER DEFAULT 0,
    seconds REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vendors (
    id TEXT PRIMARY KEY,
    case_id TEXT,
    name TEXT, name_ar TEXT,
    cr_number TEXT, vat_number TEXT,
    iban TEXT, bank_code TEXT, account_name TEXT,
    email TEXT, email_domain TEXT, phone TEXT,
    status TEXT NOT NULL DEFAULT 'active',   -- active | at_risk | on_hold
    hold_reason TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS vendor_documents (
    vendor_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    expiry_date TEXT,
    PRIMARY KEY (vendor_id, doc_type)
);
CREATE TABLE IF NOT EXISTS bank_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id TEXT NOT NULL, case_id TEXT,
    new_iban TEXT, account_name TEXT, sender TEXT,
    flags TEXT,                         -- JSON list from bank_guard
    status TEXT NOT NULL,               -- frozen | approved | rejected
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS decision_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT, vendor_id TEXT,
    reason TEXT, evidence TEXT,
    status TEXT NOT NULL DEFAULT 'open', -- open | approved | rejected
    created_at TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = str(path or DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def row(conn, sql, *args) -> dict | None:
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def rows(conn, sql, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def log_event(conn, *, kind, name=None, case_id=None, vendor_id=None, input=None,
              output=None, summary=None, tokens_in=0, tokens_out=0, cached=False,
              seconds=0.0) -> int:
    cur = conn.execute(
        "INSERT INTO events (case_id, vendor_id, ts, kind, name, input, output, summary,"
        " tokens_in, tokens_out, cached, seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (case_id, vendor_id, clock.now_iso(), kind, name,
         dumps(input) if input is not None else None,
         dumps(output) if output is not None else None,
         summary, tokens_in, tokens_out, int(cached), seconds),
    )
    conn.commit()
    return cur.lastrowid


def set_case_status(conn, case_id: str, status: str) -> None:
    conn.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?",
                 (status, clock.now_iso(), case_id))
    conn.commit()

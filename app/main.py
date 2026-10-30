"""FastAPI app: dashboard, SSE event stream, simulator, human decisions, demo clock.

    .venv/bin/uvicorn app.main:app --port 8000
    open http://localhost:8000

The dashboard reads only the store (events plus the state tables). The simulator
posts a demo case's email to the same path a real inbox would use.
"""
import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import cases, clock, db, watcher
from app.agent import Ctx, run_turn
from app.config import CASES_DIR, DB_PATH, RESULTS_DIR, ROOT, load_policy
from app.registry import Registry, load_world

DEMO_DIR = CASES_DIR / "demo"
START_DATE = "2026-10-31"
SCENES = {
    "1": "demo_1_al_noor_clean",
    "2": "demo_2_rawabi_expired_vat",
    "3": "demo_3_gulf_steel_bank_mismatch",
    "4": "demo_4_al_noor_bank_change",
}

app = FastAPI(title="Supplier Onboarding Agent")
policy = load_policy()
conn = db.connect(DB_PATH)       # writer: agent turns, simulator, decisions (serialised by `lock`)
conn.execute("PRAGMA journal_mode=WAL")
lock = threading.Lock()
rconn = db.connect(DB_PATH)      # reader for the dashboard, so it never waits on an agent turn
rlock = threading.Lock()
registry = Registry()
for d in sorted(DEMO_DIR.iterdir()):
    if d.is_dir():
        registry.add_world(load_world(d))
clock.set_now(START_DATE)


def _run_in_background(fn, *args):
    def job():
        with lock:
            try:
                fn(*args)
            except Exception as e:  # surfaced on the activity log instead of crashing the server
                db.log_event(conn, kind="system", name="error", summary=f"{type(e).__name__}: {e}")
    threading.Thread(target=job, daemon=True).start()


def _turn(case_id: str, trigger: str, as_of: str):
    clock.set_thread_now(as_of)
    run_turn(Ctx(conn=conn, registry=registry, policy=policy), case_id, trigger)


def _scene(case_dir: Path):
    label = json.loads((case_dir / "label.json").read_text())
    world = load_world(case_dir)
    vendor = world.get("vendor_on_file")
    if vendor and not db.row(conn, "SELECT id FROM vendors WHERE id=?", vendor["vendor_id"]):
        cases.seed_vendor(conn, vendor)
    clock.set_thread_now(label["as_of"])
    cases.ingest_email(conn, case_dir / "email.eml", label["case_id"])
    _turn(label["case_id"], "new inbound email", label["as_of"])


def _reply(case_dir: Path, n: int = 1):
    label = json.loads((case_dir / "label.json").read_text())
    rd = case_dir / "replies" / f"{n:02d}"
    clock.set_thread_now(label["as_of"])
    cases.ingest_email(conn, rd / "email.eml", label["case_id"])
    _turn(label["case_id"], "the supplier replied to our email", label["as_of"])


# --------------------------------------------------------------------------- pages and state

@app.get("/")
def welcome():
    return FileResponse(ROOT / "web" / "welcome.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(ROOT / "web" / "index.html")


def _latest_results():
    runs = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for split in ("heldout", "dev"):
        for p in reversed(runs):
            d = json.loads(p.read_text())
            if d["split"] == split and d["mode"] == "hybrid" and not d["ablate"] and not d.get("note", "").startswith("stability"):
                m = d["metrics"]
                return {"split": split, "run_id": d["run_id"], "cases": m["cases"],
                        "decision_accuracy": m["decision_accuracy"], "fraud_recall": m["fraud_recall"],
                        "false_escalation_rate": m["false_escalation_rate"],
                        "human_touches_per_case": m["human_touches_per_case"]}
    return None


@app.get("/api/state")
def state():
    conn = rconn
    with rlock:
        case_rows = db.rows(conn, "SELECT * FROM cases ORDER BY created_at")
        for c in case_rows:
            c["outcome"] = cases.outcome(conn, c["id"])
            c["documents"] = [{"filename": d["filename"], "extraction": d["extraction"]}
                              for d in cases.case_documents(conn, c["id"])]
            c["emails"] = db.rows(conn, "SELECT direction, kind, subject, body, documents_requested, ts FROM emails"
                                        " WHERE case_id=? ORDER BY id", c["id"])
            card = db.row(conn, "SELECT * FROM decision_cards WHERE case_id=? ORDER BY id DESC", c["id"])
            c["card"] = card
            v = db.row(conn, "SELECT * FROM vendors WHERE case_id=?", c["id"])
            c["vendor"] = v
        vendors = db.rows(conn, "SELECT * FROM vendors ORDER BY created_at")
        for v in vendors:
            v["documents"] = db.rows(conn, "SELECT doc_type, expiry_date FROM vendor_documents WHERE vendor_id=?", v["id"])
            v["renewals"] = db.rows(conn, "SELECT subject, documents_requested, ts FROM emails WHERE vendor_id=? AND kind='renewal'", v["id"])
        cards = db.rows(conn, "SELECT * FROM decision_cards WHERE status='open' ORDER BY id")
        bank_changes = db.rows(conn, "SELECT * FROM bank_changes ORDER BY id")
    return {"today": str(clock.today()), "cases": case_rows, "vendors": vendors, "open_cards": cards,
            "bank_changes": bank_changes, "results": _latest_results()}


@app.get("/api/events")
def events(after: int = 0):
    with rlock:
        return db.rows(rconn, "SELECT * FROM events WHERE id > ? ORDER BY id", after)


@app.get("/api/stream")
async def stream():
    async def gen():
        last = 0
        while True:
            with rlock:
                top = db.row(rconn, "SELECT COALESCE(MAX(id), 0) AS m FROM events")["m"]
                if top < last:          # the demo was reset and ids restarted
                    last = 0
                rows = db.rows(rconn, "SELECT * FROM events WHERE id > ? ORDER BY id", last)
            for r in rows:
                last = r["id"]
                yield f"data: {json.dumps(r, ensure_ascii=False, default=str)}\n\n"
            await asyncio.sleep(0.4)
    return StreamingResponse(gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- simulator and clock

@app.post("/api/simulate/{scene}")
def simulate(scene: str):
    if scene not in SCENES:
        raise HTTPException(404, f"scenes: {list(SCENES)}")
    _run_in_background(_scene, DEMO_DIR / SCENES[scene])
    return {"started": SCENES[scene]}


@app.post("/api/simulate/{scene}/reply")
def simulate_reply(scene: str):
    case_dir = DEMO_DIR / SCENES.get(scene, "")
    if not (case_dir / "replies").exists():
        raise HTTPException(404, "this scene has no supplier reply")
    _run_in_background(_reply, case_dir)
    return {"started": f"{SCENES[scene]} reply"}


class ClockIn(BaseModel):
    date: str


@app.post("/api/clock")
def set_clock(body: ClockIn):
    def job():
        clock.set_now(body.date)
        clock.set_thread_now(None)
        db.log_event(conn, kind="system", name="clock", summary=f"Demo clock moved to {body.date}")
        watcher.run_scan(conn, policy)
    _run_in_background(job)
    return {"today": body.date}


@app.post("/api/reset")
def reset():
    with lock:
        for t in ("cases", "documents", "emails", "events", "vendors", "vendor_documents", "bank_changes", "decision_cards"):
            conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM sqlite_sequence")   # restart ids so a replayed demo sees identical tool output
        conn.commit()
        clock.set_now(START_DATE)
    return {"ok": True}


# --------------------------------------------------------------------------- human decisions

class DecisionIn(BaseModel):
    action: str          # approve | reject | ask_supplier
    note: str = ""


@app.post("/api/decisions/{card_id}")
def decide(card_id: int, body: DecisionIn):
    with lock:
        card = db.row(conn, "SELECT * FROM decision_cards WHERE id=?", card_id)
        if not card or card["status"] != "open":
            raise HTTPException(404, "no open decision card with that id")
        status = {"approve": "approved", "reject": "rejected", "ask_supplier": "asked_supplier"}.get(body.action)
        if not status:
            raise HTTPException(400, "action must be approve, reject or ask_supplier")
        conn.execute("UPDATE decision_cards SET status=? WHERE id=?", (status, card_id))
        bc = db.row(conn, "SELECT * FROM bank_changes WHERE case_id=? AND status='frozen'", card["case_id"])
        if bc:
            if body.action == "approve":   # a human confirmed by calling the number on file
                conn.execute("UPDATE bank_changes SET status='approved' WHERE id=?", (bc["id"],))
                conn.execute("UPDATE vendors SET iban=?, account_name=?, status='active', hold_reason=NULL WHERE id=?",
                             (bc["new_iban"], bc["account_name"], bc["vendor_id"]))
            else:
                conn.execute("UPDATE bank_changes SET status='rejected' WHERE id=?", (bc["id"],))
                conn.execute("UPDATE vendors SET status='active', hold_reason=NULL WHERE id=?", (bc["vendor_id"],))
        if card["case_id"]:
            db.set_case_status(conn, card["case_id"], status if status != "asked_supplier" else "waiting_on_supplier")
        conn.commit()
        db.log_event(conn, kind="human", name="decision", case_id=card["case_id"], vendor_id=card["vendor_id"],
                     input=body.model_dump(), summary=f"Manager decision: {body.action}" + (f" ({body.note})" if body.note else ""))
    return {"card_id": card_id, "status": status}

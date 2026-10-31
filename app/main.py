"""The Seal: FastAPI app with dashboard, SSE event stream, simulator, human decisions, demo clock.

    .venv/bin/uvicorn app.main:app --port 8000
    open http://localhost:8000

The dashboard reads only the store (events plus the state tables). The simulator
posts a demo case's email to the same path a real inbox would use.
"""
import asyncio
import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel

from app import cases, checklist, clock, db, evidence, llm, watcher
from app.agent import Ctx, run_turn
from app.config import CASES_DIR, DB_PATH, MODEL, RESULTS_DIR, ROOT, env_flag, load_policy
from app.registry import Registry, load_world

DEMO_DIR = CASES_DIR / "demo"
START_DATE = "2026-10-31"
SCENES = {
    "1": "demo_1_al_noor_clean",
    "2": "demo_2_rawabi_expired_vat",
    "3": "demo_3_gulf_steel_bank_mismatch",
    "4": "demo_4_al_noor_bank_change",
}

HELDOUT_DIR = CASES_DIR / "heldout"
DEMO_START = "2026-11-01T08:55:00"       # Sunday morning, before the first email
PACE = 1.2                               # seconds between visible steps when a scene plays
# The guided demo, in order: (action, argument, demo clock when it happens).
DEMO = [
    ("scene", "1", "2026-11-01T09:12:00"),
    ("scene", "2", "2026-11-01T10:40:00"),
    ("reply", "2", "2026-11-03T14:05:00"),
    ("scene", "3", "2026-11-03T15:30:00"),
    ("decide", "demo_3_gulf_steel_bank_mismatch|reject|Bank account belongs to another company", "2026-11-03T16:10:00"),
    ("scene", "4", "2026-11-04T08:47:00"),
    ("decide", "demo_4_al_noor_bank_change|reject|Called the number on file; Al Noor did not request this", "2026-11-04T09:25:00"),
    ("clock", "2027-09-30", "2027-09-30T07:00:00"),
]

app = FastAPI(title="The Seal")
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
_last = db.row(conn, "SELECT ts FROM events ORDER BY id DESC LIMIT 1")
clock.set_display(_last["ts"][:19] if _last else DEMO_START)   # a restart keeps the demo clock where the data is


def _run_in_background(fn, *args, pace: float = 0.0, live: bool = False):
    def job():
        with lock:
            db.set_pace(pace)
            llm.set_live(live)
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


@app.get("/khatm.svg")
@app.get("/favicon.svg")
def logo():
    return FileResponse(ROOT / "web" / "khatm.svg", media_type="image/svg+xml")


@app.get("/api/policy", response_class=PlainTextResponse)
def policy_text():
    return Path(os.getenv("POLICY_PATH") or ROOT / "policy.yaml").read_text()


def _as_of(case: dict) -> str:
    try:
        return json.loads((Path(case["case_dir"]) / "label.json").read_text())["as_of"]
    except (OSError, KeyError, TypeError, ValueError):
        return str(clock.today())


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
            c["as_of"] = _as_of(c)
            c["documents"] = [{"id": d["id"], "email_id": d["email_id"], "filename": d["filename"],
                               "extraction": d["extraction"], "received_at": d["received_at"]}
                              for d in cases.case_documents(conn, c["id"])]
            c["emails"] = db.rows(conn, "SELECT id, direction, sender, to_addr, kind, subject, body, documents_requested, ts"
                                        " FROM emails WHERE case_id=? ORDER BY id", c["id"])
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
    now = clock.display_now()
    return {"today": str(clock.today()), "now": now.isoformat(timespec="seconds") if now else None,
            "agent": {"model": MODEL, "mode": "replay" if env_flag("REPLAY") else "live",
                      "has_key": bool(os.getenv("ANTHROPIC_API_KEY", "").strip())},
            "cases": case_rows, "vendors": vendors, "open_cards": cards,
            "bank_changes": bank_changes, "results": _latest_results()}


@app.get("/api/cases/{case_id}/checks")
def case_checks(case_id: str):
    with rlock:
        c = db.row(rconn, "SELECT * FROM cases WHERE id=?", case_id)
        if not c:
            raise HTTPException(404, "no such case")
        docs = [d for d in cases.case_documents(rconn, case_id) if d["extraction"]]
    if not docs:
        return {"rules": [], "passed": 0, "total": 0}
    from datetime import date
    return checklist.build(docs, registry, policy, date.fromisoformat(_as_of(c)))


def _document(doc_id: str) -> dict:
    with rlock:
        d = db.row(rconn, "SELECT * FROM documents WHERE id=?", doc_id)
    if not d:
        raise HTTPException(404, "no such document")
    return d


@app.get("/api/documents/{doc_id}/evidence")
def document_evidence(doc_id: str):
    d = _document(doc_id)
    if not d["extraction"]:
        raise HTTPException(409, "not read yet")
    return {"id": doc_id, "filename": d["filename"], **evidence.explain(d["path"], d["extraction"])}


@app.get("/api/documents/{doc_id}/page.png")
def document_page(doc_id: str):
    return Response(evidence.page_png(_document(doc_id)["path"]), media_type="image/png")


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


def _decide_case(case_id: str, action: str, note: str):
    card = db.row(conn, "SELECT id FROM decision_cards WHERE case_id=? AND status='open'", case_id)
    if card:
        _apply_decision(card["id"], DecisionIn(action=action, note=note))


def _clock_jump(day: str):
    clock.set_now(day)
    clock.set_thread_now(None)
    db.log_event(conn, kind="system", name="clock", summary=f"Demo clock moved to {day}")
    watcher.run_scan(conn, policy)


def _demo_step(i: int):
    action, arg, when = DEMO[i]
    clock.set_display(when)
    if action == "scene":
        _scene(DEMO_DIR / SCENES[arg])
    elif action == "reply":
        _reply(DEMO_DIR / SCENES[arg])
    elif action == "decide":
        case_id, act, note = arg.split("|")
        _decide_case(case_id, act, note)
    elif action == "clock":
        _clock_jump(arg)


@app.post("/api/demo/step/{i}")
def demo_step(i: int):
    if not 0 <= i < len(DEMO):
        raise HTTPException(404, f"steps 0..{len(DEMO) - 1}")
    _run_in_background(_demo_step, i, pace=PACE)
    return {"started": i, "at": DEMO[i][2]}


@app.post("/api/demo/goto/{n}")
def demo_goto(n: int):
    """Start over and replay the first n steps at full speed (presenter 'back')."""
    reset()
    def run():
        for i in range(min(n, len(DEMO))):
            _demo_step(i)
    _run_in_background(run)
    return {"replaying": n}


@app.get("/api/live/cases")
def live_cases():
    return sorted(d.name for d in HELDOUT_DIR.iterdir() if (d / "email.eml").exists()) if HELDOUT_DIR.exists() else []


class LiveIn(BaseModel):
    case: str


def _live(case_dir: Path):
    label = json.loads((case_dir / "label.json").read_text())
    world = load_world(case_dir)
    registry.add_world(world)
    vendor = world.get("vendor_on_file")
    if vendor and not db.row(conn, "SELECT id FROM vendors WHERE id=?", vendor["vendor_id"]):
        cases.seed_vendor(conn, vendor)
    case_id = "live-" + label["case_id"]
    if db.row(conn, "SELECT id FROM cases WHERE id=?", case_id):
        raise RuntimeError(f"{label['case_id']} was already processed live in this session; start over to run it again")
    clock.set_display(clock.display_now() or DEMO_START)
    clock.set_thread_now(label["as_of"])
    cases.ingest_email(conn, case_dir / "email.eml", case_id)
    _turn(case_id, "new inbound email", label["as_of"])


@app.post("/api/live")
def live(body: LiveIn):
    case_dir = HELDOUT_DIR / body.case
    if body.case not in live_cases():
        raise HTTPException(404, "no such held-out case")
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise HTTPException(400, "Live mode needs an API key. Start the server with ANTHROPIC_API_KEY set "
                                 "(and without REPLAY=1) to process a new email through the Anthropic API.")
    _run_in_background(_live, case_dir, pace=PACE, live=True)
    return {"started": body.case}


class ClockIn(BaseModel):
    date: str


@app.post("/api/clock")
def set_clock(body: ClockIn):
    _run_in_background(_clock_jump, body.date)
    return {"today": body.date}


@app.post("/api/reset")
def reset():
    with lock:
        for t in ("cases", "documents", "emails", "events", "vendors", "vendor_documents", "bank_changes", "decision_cards"):
            conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM sqlite_sequence")   # restart ids so a replayed demo sees identical tool output
        conn.commit()
        clock.set_now(START_DATE)
        clock.set_display(DEMO_START)
    return {"ok": True}


# --------------------------------------------------------------------------- human decisions

class DecisionIn(BaseModel):
    action: str          # approve | reject | ask_supplier
    note: str = ""


@app.post("/api/decisions/{card_id}")
def decide(card_id: int, body: DecisionIn):
    with lock:
        return _apply_decision(card_id, body)


def _apply_decision(card_id: int, body: DecisionIn):
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

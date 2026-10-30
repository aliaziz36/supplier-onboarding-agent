"""Play the 5 demo scenes against a running server, with pauses, for recording the video.

    .venv/bin/uvicorn app.main:app --port 8000      # in one terminal
    .venv/bin/python -m scripts.demo_play            # in another; open http://localhost:8000 first

Use --pause to change the gap between scenes (seconds).
"""
import argparse
import json
import time
import urllib.request

STEPS = [
    ("reset", "/api/reset", None),
    ("Scene 1: Al Noor Trading applies with clean documents (Arabic CR)", "/api/simulate/1", None),
    ("Scene 2: Rawabi Logistics applies with an expired VAT certificate", "/api/simulate/2", None),
    ("Scene 2b: Rawabi replies with the renewed certificate", "/api/simulate/2/reply", None),
    ("Scene 3: Gulf Steel's bank letter names a different company", "/api/simulate/3", None),
    ("Scene 4: a look-alike domain asks to change Al Noor's bank account", "/api/simulate/4", None),
    ("Manager calls Al Noor on the number on file: they never asked. Reject the change", "decide:demo_4_al_noor_bank_change", {"action": "reject", "note": "called number on file; supplier did not request this"}),
    ("Scene 5: fast-forward 11 months; Al Noor's CR expires in 20 days", "/api/clock", {"date": "2027-09-30"}),
]


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def wait_idle(base, settle=3.0, timeout=180):
    """Wait until no new events have arrived for `settle` seconds."""
    last, quiet_since, start = None, time.time(), time.time()
    while time.time() - start < timeout:
        evs = json.loads(urllib.request.urlopen(base + "/api/events").read())
        top = evs[-1]["id"] if evs else 0
        if top != last:
            last, quiet_since = top, time.time()
        elif time.time() - quiet_since > settle and evs and evs[-1]["name"] in ("set_status", "send_email", "set_vendor_hold", "scan_expiries", "error"):
            return
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--pause", type=float, default=6.0)
    args = ap.parse_args()
    for title, path, body in STEPS:
        print(f"-> {title}")
        if path.startswith("decide:"):
            state = json.loads(urllib.request.urlopen(args.base + "/api/state").read())
            card = next(c for c in state["open_cards"] if c["case_id"] == path.split(":", 1)[1])
            time.sleep(args.pause)
            post(args.base, f"/api/decisions/{card['id']}", body)
            continue
        post(args.base, path, body)
        if path != "/api/reset":
            time.sleep(1.0)
            wait_idle(args.base)
            time.sleep(args.pause)
    print("done")


if __name__ == "__main__":
    main()

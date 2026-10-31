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
    ("reset", "/api/reset"),
    ("Sun 09:12  Al Noor Trading applies with clean documents (Arabic CR)", "/api/demo/step/0"),
    ("Sun 10:40  Rawabi Logistics applies with an expired VAT certificate", "/api/demo/step/1"),
    ("Tue 14:05  Rawabi replies with the renewed certificate", "/api/demo/step/2"),
    ("Tue 15:30  Gulf Steel's bank letter names a different company", "/api/demo/step/3"),
    ("Manager rejects Gulf Steel", "/api/demo/step/4"),
    ("Wed 08:47  a look-alike domain asks to change Al Noor's bank account", "/api/demo/step/5"),
    ("Manager calls Al Noor on the number on file: they never asked. Reject the change", "/api/demo/step/6"),
    ("30 Sep 2027  daily expiry scan", "/api/demo/step/7"),
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
        elif time.time() - quiet_since > settle and evs and evs[-1]["name"] in ("set_status", "send_email", "set_vendor_hold", "scan_expiries", "decision", "error"):
            return
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--pause", type=float, default=6.0)
    args = ap.parse_args()
    for title, path in STEPS:
        print(f"-> {title}")
        post(args.base, path, None)
        if path != "/api/reset":
            time.sleep(1.0)
            wait_idle(args.base)
            time.sleep(args.pause)
    print("done")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Merge one round of fetched StatusGator results into status.json and history.json.

Usage: python3 scripts/update.py results.json

results.json is a JSON object keyed by service id (see services.json). Each value is
either the record extracted from the service's StatusGator page:
  {"status": "up|warn|down|maintenance|unknown", "status_text": str,
   "last_checked": str, "reports_24h": int|null,
   "active_incident": str|null,
   "latest_incident": {"title","start","severity","duration"}|null}
or {"error": "why the fetch failed"}.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DAYS = 7
VALID = {"up", "warn", "down", "maintenance", "unknown"}
ALIASES = {
    "operational": "up", "ok": "up", "good": "up",
    "warning": "warn", "degraded": "warn", "minor": "warn", "partial": "warn",
    "outage": "down", "major": "down", "critical": "down",
    "maint": "maintenance",
}


def norm_status(value):
    s = str(value or "").strip().lower()
    s = ALIASES.get(s, s)
    return s if s in VALID else "unknown"


TS_RE = re.compile(r"[A-Z][a-z]+ \d{1,2}, \d{4}(?: at)? \d{1,2}:\d{2} ?[AP]M(?: UTC)?")


def clean_ts(value):
    """The page extraction sometimes returns a whole sentence; keep only the date/time in it."""
    m = TS_RE.search(str(value or ""))
    return m.group(0) if m else None


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: update.py results.json")
    results = json.loads(Path(sys.argv[1]).read_text())
    services = json.loads((ROOT / "services.json").read_text())
    previous = {s["id"]: s for s in load(ROOT / "status.json", {}).get("services", [])}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.isoformat().replace("+00:00", "Z")

    out, snapshot, failures = [], {}, []
    for svc in services:
        sid = svc["id"]
        url = f"https://statusgator.com/services/{svc['slug']}"
        r = results.get(sid)
        base = {"id": sid, "name": svc["name"], "covers": svc["covers"], "url": url}
        if not isinstance(r, dict) or "error" in r:
            failures.append(sid)
            prev = previous.get(sid)
            err = (r or {}).get("error", "no result") if isinstance(r, dict) else "no result"
            if prev:
                rec = {**prev, **base, "fetch_ok": False, "fetch_error": err}
            else:
                rec = {**base, "status": "unknown", "status_text": "No data yet",
                       "sg_last_checked": None, "reports_24h": None,
                       "active_incident": None, "latest_incident": None,
                       "fetched_at": None, "fetch_ok": False, "fetch_error": err}
            snapshot[sid] = "unknown"
        else:
            li = r.get("latest_incident")
            if isinstance(li, dict) and li.get("title"):
                li = {k: li.get(k) for k in ("title", "start", "severity", "duration")}
            else:
                li = None
            rec = {**base,
                   "status": norm_status(r.get("status")),
                   "status_text": r.get("status_text"),
                   "sg_last_checked": clean_ts(r.get("last_checked")),
                   "reports_24h": to_int(r.get("reports_24h")),
                   "active_incident": r.get("active_incident") or None,
                   "latest_incident": li,
                   "fetched_at": now_iso, "fetch_ok": True, "fetch_error": None}
            snapshot[sid] = rec["status"]
        out.append(rec)

    (ROOT / "status.json").write_text(json.dumps(
        {"generated_at": now_iso, "source": "StatusGator public service pages",
         "services": out}, indent=2) + "\n")

    history = load(ROOT / "history.json", [])
    cutoff = now - timedelta(days=HISTORY_DAYS)
    history = [h for h in history
               if datetime.fromisoformat(h["t"].replace("Z", "+00:00")) >= cutoff]
    history.append({"t": now_iso, "s": snapshot})
    (ROOT / "history.json").write_text(json.dumps(history, separators=(",", ":")) + "\n")

    for rec in out:
        flag = "" if rec["fetch_ok"] else "  (FETCH FAILED: %s)" % rec["fetch_error"]
        print(f"{rec['id']:15} {rec['status']:12} reports24h={rec['reports_24h']}{flag}")
    print(f"history points: {len(history)}; failures: {len(failures)}")


if __name__ == "__main__":
    main()

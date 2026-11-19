"""Fetch StatusGator public pages and run update.py. Runs in GitHub Actions.
Usage: fetch_status.py [--force]   (without --force, obeys the Central-time schedule)"""
import json, re, html, subprocess, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def due(now):
    """Run when the data is older than the tier's interval (minus slack).
    GitHub often drops or delays scheduled runs, so the workflow fires every 10 minutes
    and this check decides whether a refresh is actually needed."""
    try:
        last = datetime.fromisoformat(json.load(open("status.json"))["generated_at"].replace("Z", "+00:00"))
        age = (now.astimezone(ZoneInfo("UTC")) - last).total_seconds() / 60
    except Exception:
        return True
    wd, h = now.weekday(), now.hour          # Mon=0
    if wd >= 5: need = 230                   # weekends: every 4 h
    elif 6 <= h <= 18: need = 50             # weekdays 6 AM-6 PM: hourly
    else: need = 110                         # weekday overnight: every 2 h
    return age >= need

def lines(body):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [l.strip() for l in t.split("\n") if l.strip()]

def parse(body):
    L = lines(body)
    i = next(j for j, l in enumerate(L) if l.startswith("Is ") and l.endswith("down?"))
    headline = L[i + 1]
    low = headline.lower()
    if re.search(r"\bis down\b|\bdown$", low): st = "down"
    elif "maintenance" in low: st = "maintenance"
    elif re.search(r"\bis up\b", low): st = "up"
    elif re.search(r"issue|degrad|disrupt|partial|problem|outage|warn", low): st = "warn"
    else: st = "unknown"
    k = next(j for j, l in enumerate(L) if l.startswith("StatusGator last checked"))
    last = L[k + 1] if re.match(r"[A-Z][a-z]+ \d+, \d{4} at ", L[k + 1]) else None
    rep = next((l for l in L if "user-submitted reports" in l), "")
    m = re.search(r"There (?:have been|has been) (no|\d+) user-submitted", rep)
    reports = None if not m else (0 if m.group(1) == "no" else int(m.group(1)))
    latest = None
    if "Incident name" in L:
        n = L.index("Incident name")
        row = L[n + 4: n + 10]          # Incident name | Duration | Started | Severity headers precede
        if len(row) >= 5 and "icon" in row[3]:
            latest = {"title": row[0], "duration": row[1], "start": re.sub(r"\s+", " ", row[2]), "severity": row[4]}
    return {"name": headline, "status": st, "status_text": headline, "last_checked": last,
            "reports_24h": reports, "active_incident": (latest or {}).get("title") if st != "up" else None,
            "latest_incident": latest}

def main():
    if "--force" not in sys.argv and not due(datetime.now(ZoneInfo("America/Chicago"))):
        print("not due"); return
    res = {}
    for s in json.load(open("services.json")):
        url = "https://statusgator.com/services/" + s["slug"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            r = parse(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
            r["name"] = s["name"]; res[s["id"]] = r
        except Exception as e:
            res[s["id"]] = {"error": f"{type(e).__name__}: {e}"[:150]}
    json.dump(res, open("/tmp/results.json", "w"))
    print(json.dumps(res, indent=1)[:1500])
    if all("error" in v for v in res.values()):
        print("ALL FAILED; leaving data untouched"); sys.exit(1)
    subprocess.run([sys.executable, "scripts/update.py", "/tmp/results.json"], check=True)

main()
# last manual refresh: 2026-11-19T03:26:31Z

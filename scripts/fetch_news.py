#!/usr/bin/env python3
"""Refresh news.json: Google News RSS search ("items") and, if configured, a Google Alerts
Atom feed ("alerts").

Runs on GitHub Actions (.github/workflows/news.yml), hourly. The alert feed address is private, so it
comes from the ALERTS_FEED_URL environment variable (a GitHub Actions secret), never from the
repo. Each section is refreshed independently: if one fetch fails, its last good copy stays.

Offline tests:  fetch_news.py news sample_rss.xml   |   fetch_news.py alerts sample_atom.xml
"""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "news.json"
QUERY = ('(outage OR "service disruption" OR "went down") '
         '("Microsoft 365" OR Azure OR Teams OR Outlook OR AWS OR "Google Cloud" OR Cloudflare) '
         'when:2d')
MAX_ITEMS = 15
ATOM = "{http://www.w3.org/2005/Atom}"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cloud-watch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_rss(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items, seen = [], set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if source and title.endswith(" - " + source):      # Google appends " - Source"
            title = title[: -len(source) - 3].rstrip()
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        key = title.lower()
        if not title or not link.startswith("https://") or key in seen:
            continue
        seen.add(key)
        items.append({"title": title, "source": source, "link": link,
                      "published": when.isoformat().replace("+00:00", "Z")})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:MAX_ITEMS]


def real_link(href):
    """Google Alerts wraps links as google.com/url?...&url=<real>&...; unwrap to the real URL."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return (q.get("url") or q.get("q") or [href])[0]


LAST_STATS = {}


def parse_atom(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items, seen = [], set()
    # Counts only (no feed content) so an empty result can be diagnosed from news.json.
    LAST_STATS.clear()
    LAST_STATS.update({"bytes": len(xml_bytes), "root": root.tag.split("}")[-1],
                       "atom_entries": len(list(root.iter(ATOM + "entry"))),
                       "any_entries": len([e for e in root.iter() if e.tag.split("}")[-1] in ("entry", "item")]),
                       "skipped_bad_date": 0, "skipped_bad_link_or_title": 0})
    for e in root.iter(ATOM + "entry"):
        title = plain(e.findtext(ATOM + "title"))
        link_el = e.find(ATOM + "link")
        link = real_link(link_el.get("href", "")) if link_el is not None else ""
        stamp = e.findtext(ATOM + "published") or e.findtext(ATOM + "updated") or ""
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            LAST_STATS["skipped_bad_date"] += 1
            continue
        host = urllib.parse.urlparse(link).hostname or ""
        source = host[4:] if host.startswith("www.") else host
        key = title.lower()
        if not title or not link.startswith("https://") or key in seen:
            LAST_STATS["skipped_bad_link_or_title"] += 1
            continue
        seen.add(key)
        items.append({"title": title, "source": source, "link": link,
                      "published": when.isoformat().replace("+00:00", "Z")})
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:MAX_ITEMS]


def load_existing():
    try:
        return json.loads(OUT.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def refresh(label, fetch_and_parse):
    """Return a fresh section dict, or None (keep the old one) on any failure."""
    try:
        items = fetch_and_parse()
    except Exception as e:  # network, HTTP or XML problems: keep last good copy, don't fail the job
        print(f"{label}: failed, keeping previous copy ({type(e).__name__})")
        return None
    print(f"{label}: {len(items)} items")
    return {"fetched_at": now_iso(), "items": items}


def main():
    if len(sys.argv) == 3:                                  # offline test mode
        parser = {"news": parse_rss, "alerts": parse_atom}[sys.argv[1]]
        for it in parser(Path(sys.argv[2]).read_bytes()):
            print(json.dumps(it))
        return

    data = load_existing()

    news_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": QUERY, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    news = refresh("news", lambda: parse_rss(http_get(news_url)))
    if news:
        data.update({"fetched_at": news["fetched_at"], "source": "Google News RSS",
                     "query": QUERY, "items": news["items"]})

    alerts_url = os.environ.get("ALERTS_FEED_URL", "").strip()
    if alerts_url.startswith("https://"):
        alerts = refresh("alerts", lambda: parse_atom(http_get(alerts_url)))
        if alerts:
            alerts["debug"] = dict(LAST_STATS)
            data["alerts"] = alerts
    else:
        print("alerts: ALERTS_FEED_URL not set, skipping")

    data.setdefault("items", [])
    OUT.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fetch a Google News RSS search and write news.json (headline, source, link, time).

Runs on GitHub Actions (see .github/workflows/news.yml). If the fetch fails, the
existing news.json is left untouched so the dashboard keeps showing the last good copy.
"""
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERY = ('(outage OR "service disruption" OR "went down") '
         '("Microsoft 365" OR Azure OR Teams OR Outlook OR AWS OR "Google Cloud" OR Cloudflare) '
         'when:2d')
MAX_ITEMS = 15


def feed_url():
    q = urllib.parse.urlencode({"q": QUERY, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return "https://news.google.com/rss/search?" + q


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items, seen = [], set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        # Google appends " - Source" to the title; show the source separately.
        if source and title.endswith(" - " + source):
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


def main():
    if len(sys.argv) == 2:                      # offline test: fetch_news.py sample.xml
        data = Path(sys.argv[1]).read_bytes()
    else:
        req = urllib.request.Request(feed_url(), headers={"User-Agent": "cloud-watch/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except Exception as e:                  # keep last good copy; do not fail the workflow
            print(f"fetch failed, keeping existing news.json: {e}")
            return
    try:
        items = parse(data)
    except ET.ParseError as e:
        print(f"parse failed, keeping existing news.json: {e}")
        return
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = {"fetched_at": now, "source": "Google News RSS", "query": QUERY, "items": items}
    (ROOT / "news.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {len(items)} items")


if __name__ == "__main__":
    main()

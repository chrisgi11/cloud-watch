# Cloud Service Watch — scheduled check runbook

Each scheduled run refreshes `status.json` and `history.json`. GitHub Pages serves
`index.html`, which reads them. No API keys are used: data comes from StatusGator's
public service pages.

## Steps for one run

1. For every entry in `services.json`, fetch `https://statusgator.com/services/<slug>`
   with WebFetch, all fetches in parallel, using exactly this prompt:

   > Return only JSON: {"name":..., "status": "up|warn|down|maintenance|unknown" exactly as
   > the page's main status says, "status_text": the headline sentence, "last_checked":
   > the timestamp only, e.g. "November 17, 2026 at 1:32 PM UTC" (not a sentence), "reports_24h": number or null, "active_incident": title or null,
   > "latest_incident": {"title","start","severity","duration"} or null}.
   > "active_incident" is only an incident the page shows as ongoing/unresolved.

2. Write `/tmp/results.json`: an object keyed by service `id`. Each value is the JSON
   returned for that service. If a fetch failed or returned no usable JSON, use
   `{"error": "<short reason>"}` for that id — never invent values.
3. Run `python3 scripts/update.py /tmp/results.json` from the repo root.
4. Commit only `status.json` and `history.json` with message
   `status: <UTC timestamp>` and push to `main`.
5. If 3 or more services failed to fetch, still commit (the page shows the failure),
   and report the failures in the run's final message.

## Files

- `services.json` — watched services (id, display name, StatusGator slug, what it covers)
- `scripts/update.py` — merges one round of results; keeps 7 days of history
- `status.json` — latest snapshot (written by update.py)
- `history.json` — one entry per run, 7-day rolling window
- `index.html` — the dashboard

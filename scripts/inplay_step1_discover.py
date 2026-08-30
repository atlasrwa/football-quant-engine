"""
In-play feasibility — Step 1a: DISCOVER live / soon-starting matches.

Minimal-budget discovery. Reuses the existing cached TheStatsAPI client but
routes all cache writes to data/thestatsapi/inplay/ so a later task can reuse
the raw responses. Zero odds calls (odds explicitly out of scope).

Strategy (few requests):
  1. List today's matches (by utc date window) WITHOUT a status filter, so we
     can see every status value the API uses (live / in_progress / scheduled /
     finished / etc.).
  2. Print status distribution + any match that is live now or kicks off within
     the next ~2 hours, with kickoff time and competition.

We do NOT filter to a competition — we want the whole day's card so we can find
something live regardless of league.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

# Route cache to a dedicated in-play dir (reusable by later tasks).
INPLAY_DIR = "/home/ubuntu/data/thestatsapi/inplay"
os.makedirs(INPLAY_DIR, exist_ok=True)
base.CACHE_DIR = INPLAY_DIR
base.USAGE_LOG = f"{INPLAY_DIR}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY_DIR}/_budget_state.json"


def main():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"UTC now: {now.isoformat()}  (today={today})")

    # Try a date-windowed listing. The API param names are unknown for date
    # filtering; try the most likely ones and inspect what comes back. We make
    # ONE call and adapt from its response rather than guessing repeatedly.
    attempts = [
        {"date_from": today, "date_to": tomorrow, "per_page": 100},
        {"date": today, "per_page": 100},
        {"from": today, "to": tomorrow, "per_page": 100},
        {"per_page": 100},  # last resort: newest matches, inspect statuses
    ]
    data = None
    used = None
    for i, params in enumerate(attempts):
        ck = f"discover_today_attempt{i}"
        try:
            data, meta = base.get_json("/football/matches", params=params, cache_key=ck,
                                       allow_status=(200, 400, 404, 422))
        except SystemExit:
            raise
        st = meta.get("http_status")
        n = len((data or {}).get("data", []) or []) if data else 0
        print(f"attempt {i} params={params} -> http {st}, n={n}, from_cache={meta.get('from_cache')}")
        if st == 200 and data and (data.get("data")):
            used = params
            break

    if not data or not data.get("data"):
        print("No match list returned from any attempt. Inspect raw responses in", INPLAY_DIR)
        print("budget:", base.budget_snapshot())
        return

    matches = data["data"]
    from collections import Counter
    statuses = Counter(m.get("status") for m in matches)
    print("\nSTATUS DISTRIBUTION in returned page:", dict(statuses))
    print("params that worked:", used)
    print("sample dates:", sorted({m.get("utc_date") for m in matches})[:5], "...",
          sorted({m.get("utc_date") for m in matches})[-3:])

    # Identify live / imminent matches
    live_states = {"live", "in_progress", "inplay", "playing", "1H", "2H", "HT", "started"}
    live = [m for m in matches if str(m.get("status", "")).lower() in {s.lower() for s in live_states}]
    soon = []
    for m in matches:
        ud = m.get("utc_date")
        if not ud:
            continue
        try:
            kt = datetime.fromisoformat(ud.replace("Z", "+00:00"))
        except Exception:
            continue
        if now <= kt <= now + timedelta(hours=3) and str(m.get("status", "")).lower() in (
                "scheduled", "not_started", "notstarted", "upcoming", "fixture", "", "none"):
            soon.append((kt, m))

    print(f"\nLIVE NOW: {len(live)}")
    for m in live[:10]:
        print(f"  {m['id']}  {m.get('status')}  {m['home_team']['name']} v {m['away_team']['name']}  "
              f"score={m.get('score',{}).get('home')}-{m.get('score',{}).get('away')}  {m.get('utc_date')}")

    print(f"\nKICKING OFF WITHIN 3H: {len(soon)}")
    for kt, m in sorted(soon)[:15]:
        print(f"  {kt.isoformat()}  {m['id']}  {m['home_team']['name']} v {m['away_team']['name']}  "
              f"comp={m.get('competition_id')}  status={m.get('status')}")

    out = {"utc_now": now.isoformat(), "params_used": used,
           "status_distribution": dict(statuses),
           "n_returned": len(matches),
           "live": [m["id"] for m in live],
           "soon": [m["id"] for _, m in sorted(soon)]}
    json.dump(out, open(f"{INPLAY_DIR}/_discover_summary.json", "w"), indent=2)
    print("\nlive requests this run:", base.live_requests_made(),
          " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

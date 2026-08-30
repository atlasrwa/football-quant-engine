"""
Step 1 gate — evidence on whether stats populate DURING play.

Constraint: at run time (2026-08-30 ~01:xx UTC) NO match is live and the
earliest kickoff is ~18h away, so a DIRECT live observation is impossible in
this session. Per the brief we must NOT improvise a fake live test. Instead we
gather the strongest available INDIRECT evidence, and clearly label the direct
test as outstanding.

Evidence gathered (few requests):
  A. Does the API recognise a live-status filter? Query /football/matches with
     status in {live, in_progress, inplay}. A recognised filter (HTTP 200) means
     live match state is a first-class concept in the data model.
  B. Pre-match baseline: for a SCHEDULED match kicking off today, what do
     /stats /shotmap /timeline return NOW (hours before kickoff)? This
     establishes the 'empty' baseline a future live poll would be compared to.
     If they are empty/404 pre-match and fully populated post-match (which we
     already saw on a finished match), then the open question is purely WHEN
     between kickoff and full-time they fill — which only a live poll resolves.

Odds out of scope: no odds endpoint called.
Caches to data/thestatsapi/inplay/.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
os.makedirs(INPLAY, exist_ok=True)
base.CACHE_DIR = INPLAY
base.USAGE_LOG = f"{INPLAY}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY}/_budget_state.json"


def endpoint_state(path, ck):
    data, meta = base.get_json(path, cache_key=ck, allow_status=(200, 400, 404, 422, 501))
    st = meta.get("http_status")
    payload = (data or {}).get("data", data) if data else None
    # Determine populated vs empty
    def nonempty(p):
        if p is None:
            return False
        if isinstance(p, list):
            return len(p) > 0
        if isinstance(p, dict):
            # stats: check if any numeric stat present
            return len(p) > 0
        return bool(p)
    return st, nonempty(payload), payload


def main():
    print("=== A. Does the API recognise a live-status filter? ===")
    for stt in ("live", "in_progress", "inplay"):
        data, meta = base.get_json("/football/matches",
                                   params={"status": stt, "per_page": 5},
                                   cache_key=f"statusfilter_{stt}",
                                   allow_status=(200, 400, 404, 422))
        st = meta.get("http_status")
        n = len((data or {}).get("data", []) or []) if data else 0
        print(f"  status={stt:12s} -> HTTP {st}  n_returned={n}  from_cache={meta.get('from_cache')}")

    print("\n=== B. Pre-match baseline for a SCHEDULED match today ===")
    disc = json.load(open(f"{INPLAY}/_discover_summary.json"))
    # get a scheduled match id from the discovery cache
    dd = json.load(open(f"{INPLAY}/discover_today_attempt0.json"))
    sched = [m for m in dd.get("data", []) if m.get("status") == "scheduled"]
    if not sched:
        print("  no scheduled match cached to test")
        return
    # pick the earliest-kicking-off scheduled match
    sched.sort(key=lambda m: m.get("utc_date", ""))
    m = sched[0]
    mid = m["id"]
    print(f"  scheduled match: {mid}  {m['home_team']['name']} v {m['away_team']['name']}  "
          f"KO {m.get('utc_date')}  status={m.get('status')}")

    for ep in ("stats", "shotmap", "timeline"):
        st, ne, payload = endpoint_state(f"/football/matches/{mid}/{ep}", f"prematch_{ep}_{mid}")
        summary = ""
        if isinstance(payload, list):
            summary = f"list[{len(payload)}]"
        elif isinstance(payload, dict):
            summary = f"dict keys={list(payload.keys())[:8]}"
        print(f"  /{ep:8s} -> HTTP {st}  populated={ne}  {summary}")

    # match detail pre-match
    st, ne, payload = endpoint_state(f"/football/matches/{mid}", f"prematch_match_{mid}")
    sc = (payload or {}).get("score") if isinstance(payload, dict) else None
    print(f"  /matches/{{id}} -> HTTP {st}  status={payload.get('status') if isinstance(payload,dict) else '?'}  score={sc}")

    print("\nlive requests this run:", base.live_requests_made(), " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

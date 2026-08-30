"""
In-play feasibility — probe the 4 endpoints on ONE recently-finished match.

Purpose: establish endpoint EXISTENCE and DATA SHAPE (especially per-minute
granularity of /timeline and /shotmap), which decides:
  - Step 3 (historical reconstruction) feasibility, and
  - whether /stats carries any minute-level structure at all.

Odds are out of scope: no odds endpoint is called.
Caches raw responses to data/thestatsapi/inplay/ for reuse.
"""
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
os.makedirs(INPLAY, exist_ok=True)
base.CACHE_DIR = INPLAY
base.USAGE_LOG = f"{INPLAY}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY}/_budget_state.json"

MID = sys.argv[1] if len(sys.argv) > 1 else "mt_733031701"


def shape(x, depth=0, maxd=3):
    """Compact structural summary of a JSON value."""
    if depth > maxd:
        return "..."
    if isinstance(x, dict):
        return {k: shape(v, depth + 1, maxd) for k, v in list(x.items())[:25]}
    if isinstance(x, list):
        return [f"list[{len(x)}]"] + ([shape(x[0], depth + 1, maxd)] if x else [])
    return type(x).__name__


def probe(path, ck):
    data, meta = base.get_json(path, cache_key=ck, allow_status=(200, 400, 404, 422, 501))
    st = meta.get("http_status")
    print(f"\n=== {path}  -> HTTP {st}  from_cache={meta.get('from_cache')} ===")
    if st != 200 or data is None:
        print("  (no 200 payload)")
        return None
    payload = data.get("data", data)
    print("  top-level keys:", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
    print("  shape:", json.dumps(shape(payload), indent=2)[:2000])
    return data


def main():
    print(f"Probing match {MID}")
    m = probe(f"/football/matches/{MID}", f"match_{MID}")
    s = probe(f"/football/matches/{MID}/stats", f"stats_{MID}")
    sm = probe(f"/football/matches/{MID}/shotmap", f"shotmap_{MID}")
    tl = probe(f"/football/matches/{MID}/timeline", f"timeline_{MID}")

    # Detail: minute-level granularity checks
    print("\n" + "=" * 60)
    print("GRANULARITY DETAIL")
    if sm:
        payload = sm.get("data", sm)
        shots = payload if isinstance(payload, list) else payload.get("shots") or payload.get("shotmap") or []
        print(f"shotmap entries: {len(shots) if isinstance(shots, list) else 'n/a'}")
        if isinstance(shots, list) and shots:
            print("  first shot:", json.dumps(shots[0], indent=2)[:800])
    if tl:
        payload = tl.get("data", tl)
        events = payload if isinstance(payload, list) else payload.get("events") or payload.get("timeline") or []
        print(f"timeline entries: {len(events) if isinstance(events, list) else 'n/a'}")
        if isinstance(events, list) and events:
            print("  first 3 events:", json.dumps(events[:3], indent=2)[:1200])

    print("\nlive requests this run:", base.live_requests_made(), " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

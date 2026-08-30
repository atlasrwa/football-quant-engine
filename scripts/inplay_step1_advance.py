"""
Step 1 gate — prove live values ADVANCE (two polls ~75s apart).

Polls /live-stats + /shotmap for 3 longest-running live matches at T0 and T1,
then diffs elapsed_minutes and key stat counters. If elapsed_minutes and/or
counters increase between polls, live population is proven beyond doubt.

Odds out of scope. Caches to data/thestatsapi/inplay/.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
base.CACHE_DIR = INPLAY
base.USAGE_LOG = f"{INPLAY}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY}/_budget_state.json"
ALLOW = (200, 400, 404, 409, 422, 501)


def snap(mid, tag):
    d, m = base.get_json(f"/football/matches/{mid}/live-stats",
                         cache_key=f"adv_live_{mid}_{tag}", allow_status=ALLOW)
    p = (d or {}).get("data", d) if d else {}
    meta = p.get("meta", {}) if isinstance(p, dict) else {}
    stats = p.get("stats", {}) if isinstance(p, dict) else {}
    def g(grp, side):
        try:
            return stats[grp]["all"][side]
        except Exception:
            return None
    ds, ms = base.get_json(f"/football/matches/{mid}/shotmap",
                           cache_key=f"adv_shot_{mid}_{tag}", allow_status=ALLOW)
    ps = (ds or {}).get("data", ds) if ds else None
    shots = ps if isinstance(ps, list) else (ps or {}).get("shots") or []
    return {
        "http": m.get("http_status"),
        "elapsed": meta.get("elapsed_minutes"),
        "status": meta.get("match_status"),
        "score": f"{meta.get('home_goals')}-{meta.get('away_goals')}",
        "poss_h": g("ball_possession", "home"),
        "shots_h": g("total_shots", "home"), "shots_a": g("total_shots", "away"),
        "fouls_h": g("fouls", "home"), "fouls_a": g("fouls", "away"),
        "corners_h": g("corner_kicks", "home"),
        "xg_h": g("expected_goals", "home"),
        "n_shots_map": len(shots) if isinstance(shots, list) else None,
    }


def main():
    live = json.load(open(f"{INPLAY}/live_list_t0.json"))["data"]
    # earliest KO = longest running = most likely to show change
    live = [m for m in live if m.get("utc_date")]
    live.sort(key=lambda m: m["utc_date"])  # ascending: earliest first
    mids = [m["id"] for m in live[:3]]
    names = {m["id"]: f"{m['home_team']['name']} v {m['away_team']['name']}" for m in live[:3]}
    print("tracking (longest-running live):")
    for mid in mids:
        print(" ", mid, names[mid], "KO", next(m['utc_date'] for m in live if m['id']==mid))

    t0 = {mid: snap(mid, "adv0") for mid in mids}
    print(f"\nT0 @ {datetime.now(timezone.utc).isoformat()}")
    for mid in mids:
        print(" ", mid, t0[mid])

    print("\nsleeping 75s...")
    time.sleep(75)

    t1 = {mid: snap(mid, "adv1") for mid in mids}
    print(f"\nT1 @ {datetime.now(timezone.utc).isoformat()}")
    for mid in mids:
        print(" ", mid, t1[mid])

    print("\n=== ADVANCEMENT (T1 - T0) ===")
    advanced_any = False
    for mid in mids:
        a, b = t0[mid], t1[mid]
        de = (b["elapsed"] or 0) - (a["elapsed"] or 0) if (a["elapsed"] is not None and b["elapsed"] is not None) else None
        changed = {k: (a.get(k), b.get(k)) for k in ("elapsed","score","shots_h","shots_a","fouls_h","fouls_a","corners_h","poss_h","xg_h","n_shots_map")
                   if a.get(k) != b.get(k)}
        if changed:
            advanced_any = True
        print(f"  {mid} {names[mid]}: d_elapsed={de}  changed={changed}")

    verdict = "LIVE POPULATION CONFIRMED — values advance during play" if advanced_any \
        else "no change in 75s (matches may be between events; elapsed should still move)"
    print("\nVERDICT:", verdict)
    json.dump({"t0": t0, "t1": t1, "advanced_any": advanced_any, "names": names},
              open(f"{INPLAY}/_advance_check.json", "w"), indent=2, default=str)
    print("live requests this run:", base.live_requests_made(), " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

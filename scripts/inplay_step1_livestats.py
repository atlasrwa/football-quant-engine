"""
Step 1 gate — DIRECT live observation via the correct /live-stats endpoint.

Discovery: the regular /stats endpoint returns HTTP 409 MATCH_IS_LIVE during
play and directs to /matches/{id}/live-stats for in-play statistics. So the API
explicitly separates post-match stats (locked live) from a live-stats feed.

This script polls, for 3 live matches:
  /matches/{id}                -> live status/score/minute
  /matches/{id}/live-stats     -> in-play stats (the live pathway)
  /matches/{id}/shotmap        -> do shots appear during play?
  /matches/{id}/timeline       -> do events appear during play, minute-marked?

Two polls ~70s apart (T0, T1) let us see whether values ADVANCE during play
(the strongest possible proof of live population) while respecting the 12/min
cap. Odds out of scope. Caches to data/thestatsapi/inplay/.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
os.makedirs(INPLAY, exist_ok=True)
base.CACHE_DIR = INPLAY
base.USAGE_LOG = f"{INPLAY}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY}/_budget_state.json"

ALLOW = (200, 400, 404, 409, 422, 501)


def livestats_markers(payload):
    if not isinstance(payload, dict):
        return {"type": str(type(payload))}
    ov = payload.get("overview") or payload
    def g(group, side):
        try:
            node = ov[group]
            node = node.get("all", node)
            return node.get(side)
        except Exception:
            return None
    return {
        "keys": list(payload.keys())[:10],
        "possession_home": g("ball_possession", "home"),
        "shots_home": g("total_shots", "home"),
        "shots_away": g("total_shots", "away"),
        "corners_home": g("corner_kicks", "home"),
        "corners_away": g("corner_kicks", "away"),
        "fouls_home": g("fouls", "home"),
        "xg_home": g("expected_goals", "home"),
        "minute": payload.get("minute") or payload.get("current_minute"),
    }


def poll(mids, tag):
    now = datetime.now(timezone.utc)
    out = {"utc": now.isoformat(), "tag": tag, "matches": {}}
    for mid in mids:
        rec = {}
        dm, mm = base.get_json(f"/football/matches/{mid}", cache_key=f"ls_match_{mid}_{tag}", allow_status=ALLOW)
        pm = (dm or {}).get("data", dm) if dm else {}
        rec["status"] = pm.get("status")
        rec["minute"] = pm.get("minute") or pm.get("current_minute")
        rec["score"] = {"h": pm.get("score", {}).get("home"), "a": pm.get("score", {}).get("away")}

        dls, mls = base.get_json(f"/football/matches/{mid}/live-stats", cache_key=f"ls_live_{mid}_{tag}", allow_status=ALLOW)
        rec["live_stats_http"] = mls.get("http_status")
        rec["live_stats"] = livestats_markers((dls or {}).get("data", dls)) if dls else None

        dsm, msm = base.get_json(f"/football/matches/{mid}/shotmap", cache_key=f"ls_shotmap_{mid}_{tag}", allow_status=ALLOW)
        p = (dsm or {}).get("data", dsm) if dsm else None
        shots = p if isinstance(p, list) else (p or {}).get("shots") or (p or {}).get("shotmap") or []
        mins = [s.get("minute") for s in shots] if isinstance(shots, list) else []
        rec["shotmap"] = {"http": msm.get("http_status"), "n": len(shots) if isinstance(shots, list) else None,
                          "max_min": max(mins) if mins else None}

        dtl, mtl = base.get_json(f"/football/matches/{mid}/timeline", cache_key=f"ls_timeline_{mid}_{tag}", allow_status=ALLOW)
        p = (dtl or {}).get("data", dtl) if dtl else None
        events = (p or {}).get("events") if isinstance(p, dict) else (p if isinstance(p, list) else [])
        mins = [e.get("minute") for e in (events or [])]
        rec["timeline"] = {"http": mtl.get("http_status"), "n": len(events or []),
                           "max_min": max(mins) if mins else None,
                           "coverage": (p or {}).get("coverage") if isinstance(p, dict) else None}
        out["matches"][mid] = rec
    return out


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "t0"
    # read the cached live list from the previous run
    live = json.load(open(f"{INPLAY}/live_list_t0.json"))["data"]
    # choose 3 live matches, prefer ones with events already (later kickoff = more minutes in)
    mids = [m["id"] for m in live[:3]]
    print(f"polling live matches (tag={tag}): {mids}")
    res = poll(mids, tag)
    print(json.dumps(res, indent=2, default=str)[:3000])
    json.dump(res, open(f"{INPLAY}/_livestats_poll_{tag}.json", "w"), indent=2, default=str)
    print("\nlive requests this run:", base.live_requests_made(), " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

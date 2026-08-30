"""
Step 3 robustness — test timeline-vs-official agreement on several finished
matches from different leagues, to see whether the corner attribution/orientation
mismatch and minor undercounts seen on mt_733031701 are systematic or a
one-match anomaly.

Fetches timeline + stats + match for a handful of recently-finished matches
(cached), reconstructs full-match event totals, compares to official /stats.
Odds out of scope. Caches to data/thestatsapi/inplay/.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
base.CACHE_DIR = INPLAY
base.USAGE_LOG = f"{INPLAY}/_usage_log.jsonl"
base.BUDGET_STATE = f"{INPLAY}/_budget_state.json"
ALLOW = (200, 400, 404, 409, 422, 501)

EVENT_TO_VAR = {"corner_kick": "corners", "yellow_card": "yellow_cards",
                "red_card": "red_cards", "foul": "fouls", "goal": "goals"}
SHOT_EVENTS = {"shot_on_target", "shot_off_target", "shot_blocked", "goal"}


def get(mid, ep):
    d, m = base.get_json(f"/football/matches/{mid}" + ("" if ep == "match" else f"/{ep}"),
                         cache_key=f"r3_{ep}_{mid}", allow_status=ALLOW)
    return (d or {}).get("data", d) if d else None, m.get("http_status")


def recon_full(events, side_of):
    st = defaultdict(lambda: defaultdict(int)); shots = defaultdict(int)
    for e in events or []:
        side = side_of.get((e.get("team") or {}).get("id"))
        if side is None:
            continue
        v = EVENT_TO_VAR.get(e.get("type"))
        if v:
            st[side][v] += 1
        if e.get("type") in SHOT_EVENTS:
            shots[side] += 1
    return st, shots


def official(stats):
    ov = (stats or {}).get("overview", {})
    def val(g, s):
        try:
            return ov[g]["all"][s]
        except Exception:
            return None
    return {
        "total_shots": {s: val("total_shots", s) for s in ("home", "away")},
        "corners": {s: val("corner_kicks", s) for s in ("home", "away")},
        "fouls": {s: val("fouls", s) for s in ("home", "away")},
        "yellow_cards": {s: val("yellow_cards", s) for s in ("home", "away")},
    }


def main():
    # candidate recently-finished matches across leagues (from earlier recent-finished list)
    mids = sys.argv[1:] or ["mt_209276905", "mt_378775051", "mt_893485226"]
    summary = []
    for mid in mids:
        match, s1 = get(mid, "match")
        stats, s2 = get(mid, "stats")
        tl, s3 = get(mid, "timeline")
        if not match or not stats or not tl:
            print(f"{mid}: incomplete (http match={s1} stats={s2} timeline={s3})")
            continue
        events = tl.get("events") if isinstance(tl, dict) else tl
        side_of = {match["home_team"]["id"]: "home", match["away_team"]["id"]: "away"}
        st, shots = recon_full(events, side_of)
        off = official(stats)
        recon = {
            "total_shots": {s: shots[s] for s in ("home", "away")},
            "corners": {s: st[s]["corners"] for s in ("home", "away")},
            "fouls": {s: st[s]["fouls"] for s in ("home", "away")},
            "yellow_cards": {s: st[s]["yellow_cards"] for s in ("home", "away")},
        }
        goals_tl = st["home"]["goals"] + st["away"]["goals"]
        score = match.get("score", {})
        print(f"\n{mid}: {match['home_team']['name']} v {match['away_team']['name']}  "
              f"score {score.get('home')}-{score.get('away')}  tl_goals={goals_tl}")
        row = {"mid": mid, "score_matches_timeline":
               (score.get('home', 0) + score.get('away', 0)) == goals_tl}
        for var in recon:
            for s in ("home", "away"):
                r, o = recon[var][s], off[var][s]
                tag = "OK" if (o is not None and r == o) else ("n/a" if o is None else "DIFF")
                print(f"    {var:14s} {s:4s} recon={r} official={o} {tag}")
            # total agreement (orientation-independent)
            rt = recon[var]["home"] + recon[var]["away"]
            ot = (off[var]["home"] or 0) + (off[var]["away"] or 0)
            row[f"{var}_total_recon"] = rt
            row[f"{var}_total_official"] = ot
            row[f"{var}_total_match"] = rt == ot
            # orientation flip check
            row[f"{var}_transposed"] = (recon[var]["home"] == off[var]["away"] and
                                        recon[var]["away"] == off[var]["home"] and
                                        off[var]["home"] != off[var]["away"])
        summary.append(row)

    print("\n=== SUMMARY (totals agreement + transposition flags) ===")
    for row in summary:
        flags = [k for k in row if k.endswith("_transposed") and row[k]]
        tot_ok = [k.replace("_total_match", "") for k in row if k.endswith("_total_match") and row[k]]
        tot_bad = [k.replace("_total_match", "") for k in row if k.endswith("_total_match") and not row[k]]
        print(f"  {row['mid']}: score~timeline={row['score_matches_timeline']}  "
              f"totals_match={tot_ok}  totals_DIFFER={tot_bad}  transposed={flags}")
    json.dump(summary, open(f"{INPLAY}/_step3_multi.json", "w"), indent=2, default=str)
    print("\nlive requests this run:", base.live_requests_made(), " budget:", base.budget_snapshot())


if __name__ == "__main__":
    main()

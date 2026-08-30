"""
Reconciliation v2 (zero new requests) — reconciles over the ALREADY-CACHED
timeline+shotmap+stats from the Step-2 batch, with two corrections learned
from v1 diagnosis:

  (1) SHOTS/SOT/xG are reconstructed from the SHOTMAP (authoritative, minute-
      stamped) rather than timeline shot-events. Diagnosis showed shotmap
      reconciles total_shots at 92% vs 62% for timeline events.
  (2) CORNERS: the timeline systematically SWAPS home/away corner attribution
      (45/51 full-coverage matches transposed; every other variable correctly
      oriented in the same matches, so it is NOT a global side-mapping bug).
      v2 reports corner orientation honestly and offers a 'corner_orientation_fixed'
      usable rate alongside the strict one — the fix is characterized, not hidden.

Reports BOTH:
  - strict usable rate (corner transposition = quarantine), and
  - post-fix usable rate (corners re-oriented to match /stats), 
so the decision point has the honest range.

Reconstructable-variable reconciliation per side vs official /stats:
  goals, corners, yellow_cards, red_cards, fouls (timeline);
  total_shots, shots_on_target, xg (shotmap).
"""
import json
import glob
import os
from collections import defaultdict, Counter

IP = "/home/ubuntu/data/thestatsapi/inplay"
CH = "/home/ubuntu/data/thestatsapi/championship"
RESULT = f"{IP}/_recon_step2_result_v2.json"

LEAGUE_PREFIX = {"Championship": "stats", "LaLiga2": "laliga2_stats", "Ligue2": "ligue2_stats"}

GOAL_TYPES = {"goal", "penalty_scored", "own_goal"}
YELLOW_TYPES = {"yellow_card"}
SECOND_YELLOW = {"second_yellow", "second_yellow_card", "yellow_red_card"}
RED_TYPES = {"red_card"}
CORNER_TYPES = {"corner_kick", "corner"}
FOUL_TYPES = {"foul"}


def stats_path(league, mid):
    p = LEAGUE_PREFIX[league]
    return f"{CH}/{p}_{mid}.json"


def off_side(stats, grp, side):
    try:
        return stats["overview"][grp]["all"][side]
    except Exception:
        return None


def main():
    batch = {b["mid"]: b for b in json.load(open(f"{IP}/_recon_batch.json"))}
    XG_TOL = 0.30
    results = []
    for mid, b in batch.items():
        league = b["league"]
        rec = {"mid": mid, "league": league, "season": b["season"],
               "quarantined_strict": False, "quarantined_postfix": False,
               "reasons_strict": [], "reasons_postfix": [], "corner_transposed": False}
        # load cached inputs
        try:
            tl = json.load(open(f"{IP}/recon_timeline_{mid}.json")).get("data", {})
        except FileNotFoundError:
            rec["reasons_strict"].append("no_timeline_cache"); rec["quarantined_strict"] = True
            rec["reasons_postfix"].append("no_timeline_cache"); rec["quarantined_postfix"] = True
            results.append(rec); continue
        coverage = tl.get("coverage")
        rec["coverage"] = coverage
        if coverage != "full" or not tl.get("events"):
            for k in ("strict", "postfix"):
                rec[f"quarantined_{k}"] = True
                rec[f"reasons_{k}"].append(f"coverage={coverage}")
            results.append(rec); continue
        events = tl["events"]
        sm = json.load(open(f"{IP}/recon_shotmap_{mid}.json")).get("data", [])
        shots = sm if isinstance(sm, list) else sm.get("shots") or sm.get("shotmap") or []
        stats = json.load(open(stats_path(league, mid))).get("data", {})

        side_of = {b["home_id"]: "home", b["away_id"]: "away"}
        acc = defaultdict(lambda: defaultdict(int))
        for e in events:
            sd = side_of.get((e.get("team") or {}).get("id"))
            if sd is None:
                continue
            t = e.get("type")
            if t in GOAL_TYPES: acc[sd]["goals"] += 1
            if t in YELLOW_TYPES: acc[sd]["yellow_cards"] += 1
            if t in SECOND_YELLOW: acc[sd]["yellow_cards"] += 1; acc[sd]["red_cards"] += 1
            if t in RED_TYPES: acc[sd]["red_cards"] += 1
            if t in CORNER_TYPES: acc[sd]["corners"] += 1
            if t in FOUL_TYPES: acc[sd]["fouls"] += 1
        # shots/SOT/xG from shotmap
        ts = defaultdict(int); sot = defaultdict(int); xg = defaultdict(float)
        for s in shots:
            sd = side_of.get(s.get("team_id"))
            if sd is None:
                continue
            ts[sd] += 1
            if s.get("is_on_target"): sot[sd] += 1
            xg[sd] += float(s.get("expected_goals") or 0.0)

        recon = {
            "goals": {s: acc[s]["goals"] for s in ("home", "away")},
            "corners": {s: acc[s]["corners"] for s in ("home", "away")},
            "yellow_cards": {s: acc[s]["yellow_cards"] for s in ("home", "away")},
            "red_cards": {s: acc[s]["red_cards"] for s in ("home", "away")},
            "fouls": {s: acc[s]["fouls"] for s in ("home", "away")},
            "total_shots": {s: ts[s] for s in ("home", "away")},
            "shots_on_target": {s: sot[s] for s in ("home", "away")},
            "xg": {s: round(xg[s], 2) for s in ("home", "away")},
        }
        GRP = {"corners": "corner_kicks", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
               "fouls": "fouls", "total_shots": "total_shots", "shots_on_target": "shots_on_target",
               "xg": "expected_goals"}
        off = {v: {s: off_side(stats, g, s) for s in ("home", "away")} for v, g in GRP.items()}
        rec["recon"] = recon; rec["official"] = off

        per_var_strict = {}; per_var_postfix = {}
        for var in GRP:
            r = recon[var]; o = off[var]
            if o["home"] is None or o["away"] is None:
                per_var_strict[var] = per_var_postfix[var] = "no_official"; continue
            if var == "xg":
                direct = abs(r["home"]-o["home"]) <= XG_TOL and abs(r["away"]-o["away"]) <= XG_TOL
                swap = abs(r["home"]-o["away"]) <= XG_TOL and abs(r["away"]-o["home"]) <= XG_TOL
            else:
                direct = r["home"] == o["home"] and r["away"] == o["away"]
                swap = r["home"] == o["away"] and r["away"] == o["home"] and o["home"] != o["away"]
            if direct:
                per_var_strict[var] = per_var_postfix[var] = "ok"
            elif swap:
                per_var_strict[var] = "transposed"
                if var == "corners":
                    rec["corner_transposed"] = True
                    per_var_postfix[var] = "ok"  # corner-orientation fix applied
                else:
                    per_var_postfix[var] = "transposed"
            else:
                per_var_strict[var] = per_var_postfix[var] = "mismatch"
        rec["per_var_strict"] = per_var_strict
        rec["per_var_postfix"] = per_var_postfix

        sc = b.get("score", {}) or {}
        score_ok = sc.get("home") is None or (sc.get("home") == recon["goals"]["home"] and sc.get("away") == recon["goals"]["away"])
        rec["score_ok"] = score_ok

        for tag, pv in (("strict", per_var_strict), ("postfix", per_var_postfix)):
            bad = [v for v, s in pv.items() if s in ("transposed", "mismatch")]
            if bad:
                rec[f"quarantined_{tag}"] = True
                rec[f"reasons_{tag}"].append("badvars:" + ",".join(bad))
            if not score_ok:
                rec[f"quarantined_{tag}"] = True
                rec[f"reasons_{tag}"].append("score_vs_eventlog")
        results.append(rec)

    n = len(results)
    def rate(tag):
        u = [r for r in results if not r.get(f"quarantined_{tag}")]
        return len(u), round(len(u)/n, 3)
    us, ur = rate("strict"); ps, pr = rate("postfix")

    cause_strict = Counter(); cause_postfix = Counter()
    for r in results:
        for x in r.get("reasons_strict", []): cause_strict[x.split(":")[0]] += 1
        for x in r.get("reasons_postfix", []): cause_postfix[x.split(":")[0]] += 1
    corner_trans = sum(1 for r in results if r.get("corner_transposed"))
    full_cov = sum(1 for r in results if r.get("coverage") == "full")

    # postfix failures by var (among full-coverage)
    postfix_badvar = Counter()
    for r in results:
        if r.get("coverage") == "full" and r.get("quarantined_postfix"):
            for v, s in r.get("per_var_postfix", {}).items():
                if s in ("mismatch", "transposed"):
                    postfix_badvar[v] += 1
            if not r.get("score_ok"): postfix_badvar["score"] += 1

    byleague = defaultdict(lambda: {"n":0,"full":0,"postfix_usable":0})
    for r in results:
        L=byleague[r["league"]]; L["n"]+=1
        if r.get("coverage")=="full": L["full"]+=1
        if not r.get("quarantined_postfix"): L["postfix_usable"]+=1

    summary = {
        "n": n, "full_coverage": full_cov,
        "usable_strict": us, "usable_rate_strict": ur,
        "usable_postfix_cornerfix": ps, "usable_rate_postfix": pr,
        "corner_transposed_count": corner_trans,
        "corner_transposed_of_full": f"{corner_trans}/{full_cov}",
        "cause_strict": dict(cause_strict),
        "cause_postfix": dict(cause_postfix),
        "postfix_residual_badvar_among_full": dict(postfix_badvar.most_common()),
        "by_league": dict(byleague),
    }
    json.dump({"summary": summary, "results": results}, open(RESULT, "w"), indent=2, default=str)

    print("="*72)
    print("RECONCILIATION v2 (shotmap for shots; corner-orientation characterized)")
    print("="*72)
    print(f"matches: {n}   full-coverage: {full_cov} ({100*full_cov/n:.0f}%)")
    print(f"corners transposed: {corner_trans}/{full_cov} full-coverage matches")
    print(f"\nUSABLE (strict, corner-transpose = fail):   {us}/{n} = {ur*100:.1f}%")
    print(f"USABLE (post corner-orientation fix):       {ps}/{n} = {pr*100:.1f}%")
    print(f"   -> of full-coverage only: {ps}/{full_cov} = {100*ps/full_cov:.0f}%")
    print(f"\nstrict quarantine causes: {dict(cause_strict)}")
    print(f"postfix quarantine causes: {dict(cause_postfix)}")
    print(f"postfix residual bad-variable tally (full-cov): {dict(postfix_badvar.most_common())}")
    print("\nby league (n / full-coverage / postfix-usable):")
    for k,v in byleague.items():
        print(f"   {k}: {v['n']} / {v['full']} / {v['postfix_usable']}")
    print(f"\nwrote {RESULT}")


if __name__ == "__main__":
    main()

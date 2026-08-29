"""
STEP 1 (blocking gate): FootyStats <-> TheStatsAPI merge validation.

Discovery will use FootyStats + TheStatsAPI fields on the SAME matches. Before any
discovery we must prove the join is correct by comparing SHARED fields between the
two sources on joined matches. F016/D2 found the legacy stats files had a match-ID
namespace with zero overlap with the cached match-lists; a silent join mismatch
would corrupt every candidate.

Overlap season used for verification: Championship 24/25.
  * TheStatsAPI: sn_2930227 (552 fixtures cached, per-match /stats cached)
  * FootyStats corpus: competition_id 12451 (Championship 2024/2025, ~557 matches)
Join key: crosswalk(home thestats_id)->footystats_name AND crosswalk(away)->name AND
          |date diff| <= 1 day. Multi-candidate windows are EXCLUDED (not silently
          picked). Ligue 2 has corpus data (comp 12338) but NO crosswalk entries;
          La Liga 2 is absent from the corpus entirely -> both handled in Step 2.

Shared fields compared: cards (yellow), corners, shots (on target), fouls, possession.
Reports agreement rate per field. Model-free; zero API calls.
"""
import json, glob, os
from datetime import datetime
from collections import defaultdict
import numpy as np

CACHE = "/home/ubuntu/data/thestatsapi/championship"
CROSSWALK = "/home/ubuntu/data/mapping/team_crosswalk.json"
CORPUS = "/home/ubuntu/data/discovery/corpus"
TSA_SEASON = "sn_2930227"          # Championship 24/25 (TheStatsAPI)
FS_COMP = 12451                    # Championship 2024/2025 (FootyStats corpus)
DAY = 86400


def load_crosswalk_champ():
    d = json.load(open(CROSSWALK))
    m = {}
    for t in d["leagues"]["England Championship"]:
        if t.get("confidence", 0) >= 0.9:
            m.setdefault(t["thestats_id"], t["footystats_name"])
    return m


def _cell(sd, group, stat, side):
    grp = sd.get(group) or {}
    node = grp.get(stat) or {}
    per = node.get("all")
    if not isinstance(per, dict):
        return None
    return per.get(side)


def load_tsa_matches():
    """TheStatsAPI 24/25 fixtures + cached /stats -> per-match shared-field values."""
    fx = json.load(open(f"{CACHE}/_all_fixtures_{TSA_SEASON}.json"))["fixtures"]
    out = []
    for f in fx:
        mid = f["id"]
        spath = f"{CACHE}/stats_{mid}.json"
        if not os.path.exists(spath):
            continue
        sd = (json.load(open(spath)) or {}).get("data", {})
        du = int(datetime.fromisoformat(f["utc_date"].replace("Z", "+00:00")).timestamp())
        out.append({
            "mid": mid,
            "home_id": f["home_team"]["id"], "away_id": f["away_team"]["id"],
            "home_name": f["home_team"]["name"], "away_name": f["away_team"]["name"],
            "date_unix": du,
            "yellow": (_cell(sd, "overview", "yellow_cards", "home"),
                       _cell(sd, "overview", "yellow_cards", "away")),
            "corners": (_cell(sd, "overview", "corner_kicks", "home"),
                        _cell(sd, "overview", "corner_kicks", "away")),
            "sot": (_cell(sd, "overview", "shots_on_target", "home"),
                    _cell(sd, "overview", "shots_on_target", "away")),
            "fouls": (_cell(sd, "overview", "fouls", "home"),
                      _cell(sd, "overview", "fouls", "away")),
            "poss": (_cell(sd, "overview", "ball_possession", "home"),
                     _cell(sd, "overview", "ball_possession", "away")),
        })
    return out


def load_fs_comp():
    """FootyStats corpus Championship 24/25 (comp 12451), keyed by (home,away)->list."""
    idx = defaultdict(list)
    seen = set()
    for cf in glob.glob(f"{CORPUS}/league-matches_*.json"):
        for mm in json.load(open(cf)).get("data", []):
            if mm.get("competition_id") != FS_COMP:
                continue
            if mm.get("id") in seen:
                continue
            seen.add(mm.get("id"))
            idx[(mm.get("home_name"), mm.get("away_name"))].append(mm)
    return idx


def pct(x):
    return f"{100*x:.1f}%"


def main():
    xwalk = load_crosswalk_champ()
    tsa = load_tsa_matches()
    fs_idx = load_fs_comp()
    fs_total = sum(len(v) for v in fs_idx.values())

    print("=" * 74)
    print("STEP 1 - MERGE VALIDATION (Championship 24/25 overlap season)")
    print("=" * 74)
    print(f"TheStatsAPI matches (24/25, stats cached): {len(tsa)}")
    print(f"FootyStats corpus matches (comp {FS_COMP}, 24/25): {fs_total}")
    print(f"Crosswalk Championship entries (conf>=0.9): {len(xwalk)}")

    crosswalk_miss = 0
    no_fs = 0
    multi = []           # excluded: >1 candidate in window
    joined = []          # (tsa, fs)
    for t in tsa:
        hn = xwalk.get(t["home_id"]); an = xwalk.get(t["away_id"])
        if not (hn and an):
            crosswalk_miss += 1
            continue
        cands = [m for m in fs_idx.get((hn, an), [])
                 if abs(m.get("date_unix", 0) - t["date_unix"]) <= DAY]
        if len(cands) == 0:
            no_fs += 1
        elif len(cands) > 1:
            multi.append((t["mid"], hn, an, len(cands)))
        else:
            joined.append((t, cands[0]))

    n = len(tsa)
    print(f"\nJoin outcome:")
    print(f"  crosswalk miss (team not mapped): {crosswalk_miss}")
    print(f"  no FootyStats match in +-1d window: {no_fs}")
    print(f"  MULTI-candidate windows (EXCLUDED): {len(multi)}")
    for mid, hn, an, k in multi:
        print(f"      {mid}  {hn} v {an}  ({k} candidates)")
    print(f"  clean 1:1 joins: {len(joined)}  (join rate {pct(len(joined)/n)})")

    # ---- shared-field agreement on clean joins ----
    fields = {
        "yellow_cards": ("yellow", lambda m: (m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards"))),
        "corners":      ("corners", lambda m: (m.get("team_a_corners"), m.get("team_b_corners"))),
        "shots_on_tgt": ("sot",    lambda m: (m.get("team_a_shotsOnTarget"), m.get("team_b_shotsOnTarget"))),
        "fouls":        ("fouls",  lambda m: (m.get("team_a_fouls"), m.get("team_b_fouls"))),
        "possession":   ("poss",   lambda m: (m.get("team_a_possession"), m.get("team_b_possession"))),
    }
    print(f"\nShared-field agreement on {len(joined)} clean joins (home & away compared):")
    print(f"  {'field':14s} {'exact%':>8s} {'within1%':>9s} {'meanAbsDiff':>12s} {'n_pairs':>8s}  note")
    report = {}
    for fname, (tkey, fsget) in fields.items():
        exact = 0; within1 = 0; absdiffs = []; npair = 0
        for t, fm in joined:
            tv = t[tkey]; fv = fsget(fm)
            for side in (0, 1):
                a = tv[side]; b = fv[side]
                if a is None or b is None:
                    continue
                a = float(a); b = float(b)
                npair += 1
                d = abs(a - b)
                absdiffs.append(d)
                if d == 0:
                    exact += 1
                if d <= 1:
                    within1 += 1
        if npair == 0:
            print(f"  {fname:14s} {'--':>8s} {'--':>9s} {'--':>12s} {0:>8d}  no comparable pairs")
            report[fname] = {"n_pairs": 0}
            continue
        mad = float(np.mean(absdiffs))
        note = ""
        if fname == "possession":
            note = "(pct scale; exact match not expected, MAD in pct pts)"
        print(f"  {fname:14s} {pct(exact/npair):>8s} {pct(within1/npair):>9s} {mad:>12.3f} {npair:>8d}  {note}")
        report[fname] = {"exact_pct": exact/npair, "within1_pct": within1/npair,
                         "mean_abs_diff": mad, "n_pairs": npair}

    out = {
        "overlap_season": "Championship 24/25",
        "tsa_season": TSA_SEASON, "fs_comp": FS_COMP,
        "tsa_matches": n, "fs_matches": fs_total,
        "crosswalk_entries": len(xwalk),
        "crosswalk_miss": crosswalk_miss, "no_fs_match": no_fs,
        "multi_candidate_excluded": len(multi),
        "multi_detail": multi,
        "clean_joins": len(joined), "join_rate": len(joined)/n,
        "field_agreement": report,
    }
    os.makedirs(f"{CACHE}", exist_ok=True)
    json.dump(out, open(f"{CACHE}/_step1_merge_validation.json", "w"), indent=2, default=str)
    print(f"\nsaved: {CACHE}/_step1_merge_validation.json")

    # ---- verdict ----
    print("\n" + "=" * 74)
    hard = {k: v for k, v in report.items() if k != "possession" and v.get("n_pairs", 0) > 0}
    worst_exact = min((v["exact_pct"] for v in hard.values()), default=0)
    print("VERDICT:")
    if worst_exact >= 0.95:
        print(f"  MERGE TRUSTED - all count fields agree exactly >=95% on 1:1 joins")
        print(f"  (worst count-field exact-match rate = {pct(worst_exact)}).")
    else:
        print(f"  MERGE SUSPECT - worst count-field exact-match = {pct(worst_exact)} (<95%).")
        print(f"  Investigate before any discovery.")


if __name__ == "__main__":
    main()

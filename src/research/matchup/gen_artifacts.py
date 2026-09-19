"""Generate machine-readable research artifacts (dictionary, provenance, coverage, registry)."""
import os, sys, csv, json, time
import numpy as np
from src._repo_paths import ensure_repo_importable
ensure_repo_importable()
from src.research.matchup.corpus import load_corpus, season_of
from src.research.matchup.design import DesignBuilder, WINDOWS, WLBL, POOLS, CHAMP_POOL, outcome
from src.research.matchup import features as F

ROOT = "/home/ubuntu/research/contextual_matchup"
OUT = f"{ROOT}/out"

FAMILY_DESC = {
    "champ": ("champion-parity team rolling FOR/AGAINST (TSA-available subset)", "F0"),
    "direct": ("direct outcome-concept rolling state (goals/corners/cards for+against)", "F1"),
    "league_env": ("leakage-safe competition baseline (prior matches this season-instance)", "F2"),
    "home_away": ("venue-conditioned team state (home team home form, away team away form)", "F3"),
    "matchup": ("explicit A-attack x B-defense combination (arith/geomean/total)", "F4"),
    "oppquality": ("shrunk iterative attack/defense strength ratings (PIT)", "F5"),
    "rich": ("rich TheStatsAPI pressure/mechanism stats FOR/AGAINST", "F6"),
}
PROVIDER_OF = {  # which provider each stat concept comes from in this corpus
    "goals": "derived-from-score", "cards": "TheStatsAPI", "yellow_cards": "TheStatsAPI",
    "fouls": "TheStatsAPI", "xg": "TheStatsAPI", "sot": "TheStatsAPI", "total_shots": "TheStatsAPI",
    "possession": "TheStatsAPI", "corner_kicks": "TheStatsAPI", "np_expected_goals": "TheStatsAPI",
    "big_chances": "TheStatsAPI", "shots_inside_box": "TheStatsAPI", "shots_off_target": "TheStatsAPI",
    "blocked_shots": "TheStatsAPI", "accurate_crosses": "TheStatsAPI", "touches_in_penalty_area": "TheStatsAPI",
    "final_third_entries": "TheStatsAPI", "throw_ins": "TheStatsAPI", "tackles": "TheStatsAPI",
    "interceptions": "TheStatsAPI", "clearances": "TheStatsAPI",
}
TEMPORAL = {
    "champ": "PRIOR_MATCH_ROLL (current-season, strictly kickoff<F)",
    "direct": "PRIOR_MATCH_ROLL",
    "league_env": "PRIOR_MATCH_ONLY (>=20 prior matches this season-instance)",
    "home_away": "PRIOR_MATCH_ROLL (venue-conditioned, current-season)",
    "matchup": "PRIOR_MATCH_ROLL (derived from for/against prior rolls)",
    "oppquality": "PIT_INCREMENTAL_SNAPSHOT (state before F only)",
    "rich": "PRIOR_MATCH_ROLL",
}


def main():
    recs = load_corpus()
    db = DesignBuilder(recs)
    for s in ["xg", "corner_kicks", "cards"]:
        db.ratings(s)
    # sample a mid record with full history for feature-name enumeration
    fam_fns = {"champ": db.f_champ, "direct": db.f_direct, "league_env": db.f_league_env,
               "home_away": db.f_home_away, "matchup": db.f_matchup, "oppquality": db.f_oppquality,
               "rich": db.f_rich}
    # ---- FEATURE_DICTIONARY + FEATURE_PROVENANCE ----
    dict_rows = []; prov_rows = []
    seen = set()
    for market in ["goals", "corners", "cards", "btts"]:
        # find a rec with a valid outcome and rich history
        for rec in recs[len(recs)//2:]:
            if outcome(rec, market, {"goals": 2.5, "corners": 9.5, "cards": 4.5, "btts": None}[market]) is None:
                continue
            names_by_fam = {f: sorted(fam_fns[f](rec, market).keys()) for f in fam_fns}
            break
        for fam, names in names_by_fam.items():
            desc, fid = FAMILY_DESC[fam]
            for nm in names:
                key = (market, fam, nm)
                if key in seen:
                    continue
                seen.add(key)
                # parse orientation/window/stat from name
                orient = "for" if "_for" in nm else ("against" if "_against" in nm else "n/a")
                win = next((w for w in ["w5", "w10", "std"] if nm.endswith(w) or f"_{w}" in nm), "n/a")
                dict_rows.append({"market": market, "family": fid, "family_name": fam,
                                  "feature": nm, "orientation": orient, "window": win,
                                  "meaning": desc})
                prov_rows.append({"market": market, "family": fam, "feature": nm,
                                  "provider": "FootyStats+TheStatsAPI (adapter)",
                                  "temporal_class": TEMPORAL[fam],
                                  "pit_rule": "kickoff_unix(source) < kickoff_unix(fixture); window within season-instance",
                                  "cold_start": "fail-closed (None) below MIN_HISTORY=3 or window length"})

    with open(f"{OUT}/FEATURE_DICTIONARY.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dict_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in dict_rows]
    with open(f"{OUT}/FEATURE_PROVENANCE.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(prov_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in prov_rows]

    # ---- COVERAGE_REPORT: per family/market, fraction of fixtures with a non-null feature ----
    cov_rows = []
    for market in ["goals", "corners", "cards", "btts"]:
        lineval = {"goals": 2.5, "corners": 9.5, "cards": 4.5, "btts": None}[market]
        n = 0; fam_pop = {f: 0 for f in fam_fns}
        by_comp = {}
        for rec in recs:
            if outcome(rec, market, lineval) is None:
                continue
            n += 1
            by_comp.setdefault(rec.competition, [0, {f: 0 for f in fam_fns}])
            by_comp[rec.competition][0] += 1
            for f in fam_fns:
                d = fam_fns[f](rec, market)
                has = any(v is not None for v in d.values())
                fam_pop[f] += int(has)
                by_comp[rec.competition][1][f] += int(has)
        for f in fam_fns:
            cov_rows.append({"market": market, "family": f, "scope": "ALL", "n": n,
                             "pct_populated": round(100 * fam_pop[f] / n, 1) if n else 0})
        for comp, (cn, cp) in by_comp.items():
            for f in fam_fns:
                cov_rows.append({"market": market, "family": f, "scope": comp, "n": cn,
                                 "pct_populated": round(100 * cp[f] / cn, 1) if cn else 0})
    with open(f"{OUT}/COVERAGE_REPORT.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cov_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in cov_rows]

    print(f"wrote FEATURE_DICTIONARY ({len(dict_rows)}), FEATURE_PROVENANCE ({len(prov_rows)}), COVERAGE_REPORT ({len(cov_rows)})")


if __name__ == "__main__":
    main()

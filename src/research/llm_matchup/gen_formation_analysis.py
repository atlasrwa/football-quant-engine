"""Generate deterministic formation analysis artifacts (no LLM calls).

Produces:
  * out/formation_profiles.csv   — per (team, venue, resolved_formation) behavioral profile
                                    with sample_n, reliability, formation_delta vs baseline.
  * out/formation_matchups.csv   — per (team formation x opponent formation) hierarchical
                                    matchup evidence for corner-relevant metrics, showing the
                                    tier ladder occupancy (how sparse exact cohorts are).
  * out/formation_information_gain.json — does resolved formation improve the conditional
                                    expectation of behavior beyond team/venue baseline?
                                    (variance-reduction style measure, brief §33)

These are HISTORICAL RESOLUTION artifacts: they condition on the resolved formation teams
ACTUALLY played in completed matches. No target-fixture leakage (each profile is built from
all matches for that team; this is descriptive resolution, not forecasting).

Run: .venv/bin/python -m src.research.llm_matchup.gen_formation_analysis
"""
from __future__ import annotations
import os, csv, json, statistics
from collections import defaultdict

from src.research.matchup.corpus import load_corpus, season_of
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup import formation as FM
from src.research.llm_matchup import formation_evidence as FE

OUT = "/home/ubuntu/research/llm_matchup/out"

PROFILE_METRICS = ["crosses", "corners", "total_shots", "touches_in_box", "possession",
                   "clearances", "blocked_shots"]


def _team_venue_matches(recs, coverage):
    """Yield (team, venue, formation, family, rec) for every match with a resolved formation.
    Descriptive (all matches); used only for historical resolution profiling."""
    for r in recs:
        if r.fixture_id not in coverage:
            continue
        cov = coverage[r.fixture_id]
        for team, venue, form in ((r.home, "home", cov["home"]), (r.away, "away", cov["away"])):
            if not form:
                continue
            yield team, venue, form, FM.formation_family(form), r


def build_profiles(recs, coverage):
    # accumulate metric values per (team, venue, formation) and per (team, venue) baseline
    cond = defaultdict(lambda: defaultdict(list))     # (team,venue,form) -> metric -> vals
    base = defaultdict(lambda: defaultdict(list))     # (team,venue) -> metric -> vals
    for team, venue, form, fam, r in _team_venue_matches(recs, coverage):
        for m in PROFILE_METRICS:
            v = CH.team_metric(r, team, m, "for", "all")
            if v is not None:
                cond[(team, venue, form)][m].append(v)
                base[(team, venue)][m].append(v)
    rows = []
    for (team, venue, form), md in cond.items():
        fam = FM.formation_family(form)
        n = max((len(v) for v in md.values()), default=0)
        for m in PROFILE_METRICS:
            vals = md.get(m, [])
            bvals = base[(team, venue)].get(m, [])
            if not vals:
                continue
            cv = sum(vals) / len(vals)
            bv = (sum(bvals) / len(bvals)) if bvals else None
            rows.append({
                "team": team, "venue": venue, "resolved_formation": form,
                "formation_family": fam, "metric": m,
                "formation_value": round(cv, 4), "sample_n": len(vals),
                "team_baseline": (round(bv, 4) if bv is not None else None),
                "formation_delta": (round(cv - bv, 4) if bv is not None else None),
                "reliability": FE._reliability(len(vals), float(len(vals))),
            })
    rows.sort(key=lambda r: (r["team"], r["venue"], r["resolved_formation"], r["metric"]))
    return rows


def build_matchups(recs, coverage):
    """For every observed (team_formation x opp_formation) pair, count occupancy and show
    the average corner-relevant metric — demonstrating exact-cohort sparsity."""
    agg = defaultdict(lambda: defaultdict(list))   # (team_fam,opp_fam) -> metric -> vals
    exact = defaultdict(lambda: defaultdict(list)) # (team_form,opp_form) -> metric -> vals
    for r in recs:
        if r.fixture_id not in coverage:
            continue
        cov = coverage[r.fixture_id]
        hf, af = cov["home"], cov["away"]
        if not hf or not af:
            continue
        hfam, afam = FM.formation_family(hf), FM.formation_family(af)
        for team, venue, tf, tfam, of, ofam in (
                (r.home, "home", hf, hfam, af, afam), (r.away, "away", af, afam, hf, hfam)):
            for m in ("crosses", "corners", "clearances"):
                v = CH.team_metric(r, team, m, "for", "all")
                if v is not None:
                    agg[(tfam, ofam)][m].append(v)
                    exact[(tf, of)][m].append(v)
    rows = []
    for (tfam, ofam), md in sorted(agg.items()):
        for m, vals in sorted(md.items()):
            rows.append({"level": "FAMILY_x_FAMILY", "team_formation": tfam,
                         "opp_formation": ofam, "metric": m,
                         "value": round(sum(vals) / len(vals), 4), "sample_n": len(vals)})
    for (tf, of), md in sorted(exact.items()):
        for m, vals in sorted(md.items()):
            rows.append({"level": "EXACT_x_EXACT", "team_formation": tf,
                         "opp_formation": of, "metric": m,
                         "value": round(sum(vals) / len(vals), 4), "sample_n": len(vals)})
    return rows


def information_gain(recs, coverage):
    """Variance-reduction style measure (brief §33): for each metric, compare the residual
    variance of the metric around the (team,venue) baseline vs around the
    (team,venue,formation) conditional mean. Positive reduction => formation carries
    information about behavior beyond team/venue.
    Reported as pooled fraction of variance explained by adding formation."""
    cond = defaultdict(lambda: defaultdict(list))
    base = defaultdict(lambda: defaultdict(list))
    for team, venue, form, fam, r in _team_venue_matches(recs, coverage):
        for m in PROFILE_METRICS:
            v = CH.team_metric(r, team, m, "for", "all")
            if v is not None:
                cond[(team, venue, form)][m].append(v)
                base[(team, venue)][m].append(v)
    out = {}
    for m in PROFILE_METRICS:
        # total within-(team,venue) SS and within-(team,venue,formation) SS
        ss_base = ss_cond = n_used = 0.0
        for (team, venue), md in base.items():
            vals = md.get(m, [])
            if len(vals) < 6:
                continue
            mu = sum(vals) / len(vals)
            ss_base += sum((x - mu) ** 2 for x in vals)
            n_used += len(vals)
        for (team, venue, form), md in cond.items():
            vals = md.get(m, [])
            if len(vals) < 2:
                # singletons contribute 0 residual but also no real info; skip
                continue
            mu = sum(vals) / len(vals)
            ss_cond += sum((x - mu) ** 2 for x in vals)
        frac = (1 - ss_cond / ss_base) if ss_base > 0 else None
        out[m] = {"ss_baseline": round(ss_base, 2), "ss_formation_cond": round(ss_cond, 2),
                  "variance_explained_by_formation": (round(frac, 4) if frac is not None else None),
                  "n_obs": int(n_used),
                  "caveat": "formation-conditional groups are tiny (often n<=2), so this is an "
                            "upper-bound-flavored, optimistic estimate; interpret with the "
                            "sparsity finding in FORMATION_BEHAVIOR_ANALYSIS.md"}
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = load_corpus()
    coverage = FM.resolved_coverage_index()
    profiles = build_profiles(recs, coverage)
    matchups = build_matchups(recs, coverage)
    ig = information_gain(recs, coverage)

    with open(os.path.join(OUT, "formation_profiles.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team", "venue", "resolved_formation", "formation_family",
                                          "metric", "formation_value", "sample_n", "team_baseline",
                                          "formation_delta", "reliability"])
        w.writeheader()
        for r in profiles:
            w.writerow(r)
    with open(os.path.join(OUT, "formation_matchups.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["level", "team_formation", "opp_formation", "metric",
                                          "value", "sample_n"])
        w.writeheader()
        for r in matchups:
            w.writerow(r)
    json.dump(ig, open(os.path.join(OUT, "formation_information_gain.json"), "w"), indent=2)

    # sparsity summary for the analysis doc
    exact_ns = [r["sample_n"] for r in matchups if r["level"] == "EXACT_x_EXACT"]
    fam_ns = [r["sample_n"] for r in matchups if r["level"] == "FAMILY_x_FAMILY"]
    summary = {
        "n_profile_rows": len(profiles),
        "n_matchup_rows": len(matchups),
        "exact_cohort_median_n": (statistics.median(exact_ns) if exact_ns else None),
        "exact_cohort_max_n": (max(exact_ns) if exact_ns else None),
        "family_cohort_median_n": (statistics.median(fam_ns) if fam_ns else None),
        "family_cohort_max_n": (max(fam_ns) if fam_ns else None),
        "information_gain": ig,
    }
    json.dump(summary, open(os.path.join(OUT, "formation_analysis_summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

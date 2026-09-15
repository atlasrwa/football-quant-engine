"""ZERO-SPEND forensic audit of the evidence supplied to Sonnet in the frozen V3 run.

Read-only. No Bedrock, no network, no artifact modification, no rescoring. Compares what
Sonnet SAW (MATERIALIZED_PACKETS_sonnet46_v3.json) against what the upstream PIT-safe
corpus COULD have supported at each fixture cutoff.
"""
from __future__ import annotations
import json, sys, hashlib
from collections import Counter, defaultdict

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
from src.research.hypothesis_engine import corpus_adapter as CA

ROOT = "/home/ubuntu"
PKT = f"{ROOT}/research/hypothesis_engine/out/MATERIALIZED_PACKETS_sonnet46_v3.json"
OUT = f"{ROOT}/research/hypothesis_engine/out/v3_evidence_audit"
CLEAN = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
         'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411',
         'mt_013233190']

# Metrics the V3 evidence exposed (unconditional scalar means), for parity checks.
V3_METRICS = ["corners", "accurate_crosses", "total_shots", "shots_on_target",
              "shots_off_target", "blocked_shots", "shots_inside_box", "touches_in_box",
              "final_third_entries", "possession", "tackles", "fouls", "yellow_cards",
              "clearances", "interceptions", "goals", "throw_ins", "big_chances", "saves"]


def prior_matches(idx, team, cutoff, target_fid):
    out = []
    for r in idx.prior(team, cutoff):
        if r.fixture_id == target_fid:
            continue
        out.append(r)
    return out


def venue_split(idx, team, cutoff, target_fid, metric):
    home_vals, away_vals = [], []
    for r in prior_matches(idx, team, cutoff, target_fid):
        v = CA.team_value(r, team, metric, "FOR")
        if v is None:
            continue
        if r.home == team:
            home_vals.append(v)
        else:
            away_vals.append(v)
    return len(home_vals), len(away_vals)


def window_depth(idx, team, cutoff, target_fid):
    n = len(prior_matches(idx, team, cutoff, target_fid))
    return {"n_prior": n, "W5_ok": n >= 5, "W10_ok": n >= 10, "recent_vs_long_ok": n >= 10}


def formation_audit(idx, team, cutoff, target_fid):
    matches = prior_matches(idx, team, cutoff, target_fid)
    fams = []
    for r in matches:
        fam = CA.team_formation_family(r, team)
        if fam is not None:
            fams.append(fam)
    c = Counter(fams)
    return {"n_prior": len(matches), "n_with_formation": len(fams),
            "coverage": round(len(fams) / len(matches), 4) if matches else 0.0,
            "distinct_formations": len(c), "n_per_formation": dict(c),
            "contrastive": len([f for f, n in c.items() if n >= 4]) >= 2,
            "formation_conditioned_metrics_measurable": (
                len([f for f, n in c.items() if n >= 4]) >= 2)}


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    packets = json.load(open(PKT))
    idx = CA.load_index()
    by_id = {r.fixture_id: r for r in idx.records}

    audit = {"fixtures": {}, "summary": {}}
    loss_counter = Counter()

    for fid in CLEAN:
        target = by_id[fid]
        cutoff = int(target.kickoff_unix)
        pk = packets[f"reference::{fid}"]
        ev = pk["evidence"]

        # ---- what V3 exposed (structure) --------------------------------------------
        v3_windows = sorted({e["scope"].get("window") for e in ev})
        v3_venues = sorted({e["scope"].get("venue") for e in ev})
        v3_metrics = sorted({e["scope"].get("metric") for e in ev})
        v3_conditioned = any(e["scope"].get("venue") not in (None, "ALL")
                             or e["scope"].get("window") not in (None, "ALL_PRIOR")
                             for e in ev)

        fx = {"real_home": target.home, "real_away": target.away,
              "competition": target.competition, "cutoff_unix": cutoff,
              "v3_evidence": {
                  "n_items": len(ev),
                  "windows": v3_windows, "venues": v3_venues,
                  "n_distinct_metrics": len(v3_metrics),
                  "any_conditional_scope": v3_conditioned,
                  "shrinkage_levels": dict(Counter(e.get("shrinkage_level") for e in ev)),
                  "reliability": dict(Counter(e.get("reliability") for e in ev)),
                  "exposes_distribution": any("distribution" in e or "sd" in e or "p25" in e
                                              for e in ev),
                  "exposes_per_match_rows": any("matches" in e or "rows" in e for e in ev),
              }}

        # ---- what upstream COULD support --------------------------------------------
        upstream = {}
        for side_label, team in (("home", target.home), ("away", target.away)):
            wd = window_depth(idx, team, cutoff, fid)
            # venue split availability across the exposed metrics
            venue_ok = {}
            for m in V3_METRICS:
                h, a = venue_split(idx, team, cutoff, fid, m)
                venue_ok[m] = {"home_n": h, "away_n": a,
                               "venue_split_ok": h >= 4 and a >= 4}
            fa = formation_audit(idx, team, cutoff, fid)
            n_venue_splittable = sum(1 for v in venue_ok.values() if v["venue_split_ok"])
            upstream[side_label] = {
                "team": team, "window_depth": wd, "formation": fa,
                "n_metrics_venue_splittable": n_venue_splittable,
                "n_metrics_checked": len(V3_METRICS),
                "venue_detail": venue_ok}
        fx["upstream_capability"] = upstream

        # ---- information-loss classification per capability -------------------------
        # For this fixture, classify the major conditional capabilities.
        classes = {}
        # unconditional scalar means: exposed
        classes["unconditional_scalar_means"] = "RAW_AVAILABLE_AND_EXPOSED"
        # venue split: available upstream (if either team has splittable metrics) but NOT exposed
        venue_avail = any(upstream[s]["n_metrics_venue_splittable"] >= 5
                          for s in ("home", "away"))
        classes["venue_conditioned_behavior"] = (
            "RAW_AVAILABLE_BUT_NOT_EXPOSED" if venue_avail else "BLOCKED_BY_PROVIDER_COVERAGE")
        # recent-vs-long window: derivable from raw matches but collapsed to ALL_PRIOR
        win_avail = any(upstream[s]["window_depth"]["recent_vs_long_ok"]
                        for s in ("home", "away"))
        classes["recent_vs_long_run"] = (
            "DERIVABLE_BUT_NOT_CONSTRUCTED" if win_avail else "BLOCKED_BY_PROVIDER_COVERAGE")
        # per-match temporal structure: raw available, collapsed
        classes["per_match_temporal_structure"] = "RAW_AVAILABLE_BUT_AGGREGATED"
        # formation-conditioned: depends on coverage
        fcontrast = any(upstream[s]["formation"]["contrastive"] for s in ("home", "away"))
        fcover = max(upstream[s]["formation"]["coverage"] for s in ("home", "away"))
        if fcontrast:
            classes["formation_conditioned_behavior"] = "RAW_AVAILABLE_BUT_NOT_EXPOSED"
        elif fcover < 0.5:
            classes["formation_conditioned_behavior"] = "BLOCKED_BY_PROVIDER_COVERAGE"
        else:
            classes["formation_conditioned_behavior"] = "DERIVABLE_BUT_NOT_CONSTRUCTED"
        # opponent-profile: V4 proved measurable downstream; NOT exposed to LLM
        classes["opponent_profile_response"] = "DERIVABLE_BUT_NOT_CONSTRUCTED"
        # interactions: derivable but not constructed (needs the above first)
        classes["interaction_cohorts"] = "DERIVABLE_BUT_NOT_CONSTRUCTED"
        # distribution/heterogeneity: raw available, aggregated away
        classes["distribution_heterogeneity"] = "RAW_AVAILABLE_BUT_AGGREGATED"
        # half-state / HT: provider-dependent
        classes["half_time_state"] = "PIT_UNSAFE"   # only GOAL minutes timestamped (see manifest)

        fx["information_loss"] = classes
        for c in classes.values():
            loss_counter[c] += 1
        audit["fixtures"][fid] = fx

    # ---- summary -----------------------------------------------------------------------
    audit["summary"] = {
        "n_fixtures": len(CLEAN),
        "information_loss_totals": dict(loss_counter),
        "capabilities_audited_per_fixture": 10,
        "v3_evidence_uniformly_unconditional": all(
            audit["fixtures"][f]["v3_evidence"]["windows"] == ["ALL_PRIOR"]
            and audit["fixtures"][f]["v3_evidence"]["venues"] == ["ALL"]
            for f in CLEAN),
        "v3_exposes_distribution": any(
            audit["fixtures"][f]["v3_evidence"]["exposes_distribution"] for f in CLEAN),
        "v3_exposes_per_match_rows": any(
            audit["fixtures"][f]["v3_evidence"]["exposes_per_match_rows"] for f in CLEAN),
    }

    with open(f"{OUT}/capability_matrix.json", "w") as fh:
        json.dump(audit, fh, indent=1, sort_keys=True, default=str)
    print("wrote", f"{OUT}/capability_matrix.json")
    print("uniformly unconditional (venue=ALL, window=ALL_PRIOR):",
          audit["summary"]["v3_evidence_uniformly_unconditional"])
    print("v3 exposes distribution:", audit["summary"]["v3_exposes_distribution"],
          "| per-match rows:", audit["summary"]["v3_exposes_per_match_rows"])
    print("loss totals:", json.dumps(dict(loss_counter)))
    # per-fixture formation summary
    print("\nfixture         home_prior home_formcov home_contrast away_prior away_formcov away_contrast")
    for fid in CLEAN:
        h = audit["fixtures"][fid]["upstream_capability"]["home"]
        a = audit["fixtures"][fid]["upstream_capability"]["away"]
        print(f"{fid:15} {h['window_depth']['n_prior']:>10} "
              f"{h['formation']['coverage']:>12} {str(h['formation']['contrastive']):>13} "
              f"{a['window_depth']['n_prior']:>10} {a['formation']['coverage']:>12} "
              f"{str(a['formation']['contrastive']):>13}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

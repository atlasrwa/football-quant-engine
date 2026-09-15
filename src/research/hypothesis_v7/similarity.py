"""V7 deterministic PIT-safe similar-opponent engine (`v7_similarity_v2`). Phase 7.

Similar-opponent hypotheses are central to V6.1's research families. The LLM may have proposed
WHICH dimensions matter; V7 computes similarity NUMERICALLY and DETERMINISTICALLY, using only
PIT-safe history. Everything below is FROZEN before any effect is tested; no threshold is tuned
per hypothesis after seeing effects. A small preregistered family (two distance specs) is the
only permitted degree of freedom.

The LLM NEVER produces a numeric similarity score.

v2 CHANGES (both made BEFORE any effect was computed, for coverage/spec reasons only)
-------------------------------------------------------------------------------------
1. `xg_conceded_per_match` was REMOVED and replaced by `shots_inside_box_conceded_per_match`.
   Measured corpus coverage for xg is 0.000 in ligue2 and 0.452 in laliga2, so every ligue2
   team profile would have had that dimension imputed to the cohort mean (z=0) while epl/
   laliga profiles carried a real value -- a silent, LEAGUE-CORRELATED distortion of the
   distance metric that `MAX_MISSING_DIMS = 1` would have waved through. The replacement is a
   defensive-quality proxy with >=0.988 coverage in EVERY competition. The swap is justified
   purely by measured availability; no effect was consulted.
2. `PROFILE_SHRINKAGE_K` is now actually APPLIED. v1 declared the constant in its frozen spec
   but `team_profile()` never used it, so the published spec did not describe the code.

All dimensions are read from ONE provider (TheStatsAPI) -- see `provider.py` for why the
base/rich/extra split is storage, not provenance.

ZERO SPEND.
"""
from __future__ import annotations

import math

SIMILARITY_VERSION = "v7_similarity_v2"

#: The frozen similarity input dimensions. All are PIT-safe team-profile summaries computed
#: from prior fixtures only, and all clear the Phase 25 per-competition coverage gate.
SIMILARITY_DIMENSIONS = (
    "goals_conceded_per_match",
    "shots_on_target_conceded_per_match",
    "shots_inside_box_conceded_per_match",
    "fouls_committed_per_match",
    "yellow_cards_per_match",
)

#: dimension -> (storage block, field, perspective). perspective OPP = the opponent's value in
#: that match (i.e. what this team conceded); SELF = this team's own value.
DIMENSION_BINDING = {
    "goals_conceded_per_match": ("base", "GoalCount", "OPP"),
    "shots_on_target_conceded_per_match": ("rich", "shots_on_target", "OPP"),
    "shots_inside_box_conceded_per_match": ("rich", "shots_inside_box", "OPP"),
    "fouls_committed_per_match": ("rich", "fouls", "SELF"),
    "yellow_cards_per_match": ("base", "yellow_cards", "SELF"),
}

#: dimension -> the CONTRACTED METRIC whose coverage row governs it, so the claim that every
#: dimension clears the Phase 25 gate can be VERIFIED against the measured matrix rather than
#: asserted in a version stamp.
DIMENSION_METRIC = {
    "goals_conceded_per_match": "goals",
    "shots_on_target_conceded_per_match": "shots_on_target",
    "shots_inside_box_conceded_per_match": "shots_inside_box",
    "fouls_committed_per_match": "fouls",
    "yellow_cards_per_match": "yellow_cards",
}


def validate_dimension_coverage(coverage: dict) -> dict:
    """Verify every frozen similarity dimension clears the measured Phase 25 coverage gate.

    A dimension silently missing in one competition biases the distance metric in a
    league-correlated way (this is exactly what the removed xg dimension did), so this is
    checked against measurement, never assumed.
    """
    rows = (coverage or {}).get("metrics") or {}
    per_dim, failures = {}, []
    for dim, metric in sorted(DIMENSION_METRIC.items()):
        row = rows.get(metric)
        if row is None:
            failures.append(f"{dim}: metric '{metric}' absent from the coverage matrix")
            per_dim[dim] = {"metric": metric, "gate_pass": False}
            continue
        per_dim[dim] = {"metric": metric,
                        "overall_coverage": row["overall_coverage"],
                        "min_competition_coverage": min(
                            row["competition_coverage"].values()),
                        "excluded_competitions": row["excluded_competitions"],
                        "gate_pass": row["coverage_gate_pass"]}
        if not row["coverage_gate_pass"]:
            failures.append(f"{dim}: metric '{metric}' fails the coverage gate "
                            f"(excluded in {row['excluded_competitions']})")
    return {"all_dimensions_clear_coverage_gate": not failures,
            "per_dimension": per_dim, "failures": failures}


SCALING = "ZSCORE_PIT_TRAIN_ONLY"
MAX_MISSING_DIMS = 1
MISSING_IMPUTATION = "COHORT_MEAN_Z0"

#: shrinkage on the profile itself: pull a team's per-match rate toward the competition
#: baseline with strength K before computing distance (reduces small-sample noise). APPLIED.
PROFILE_SHRINKAGE_K = 8.0

#: distance metrics -- a preregistered FAMILY of size 2 (not a search grid).
DISTANCE_METRICS = ("euclidean_z", "manhattan_z")
PRIMARY_DISTANCE = "euclidean_z"

COHORT_RULE = "K_NEAREST"
K_NEIGHBORS = 8
MIN_PROFILE_HISTORY_MATCHES = 6
TIE_BREAK = "kickoff_unix_asc_then_fixture_id"
RESTRICT_SAME_COMPETITION = True


def _side_value(rec, team_id, block, field, perspective):
    """The per-match value of one dimension for `team_id` in `rec`, or None if unavailable.

    NULL is never read as ZERO: a missing field returns None so the caller can count it as
    missing rather than silently averaging in a zero.
    """
    if rec.home_id == team_id:
        me, opp = "home", "away"
    elif rec.away_id == team_id:
        me, opp = "away", "home"
    else:
        return None
    want = opp if perspective == "OPP" else me

    if block == "base":
        b = rec.base or {}
        if field == "GoalCount":
            v = b.get(f"{want}GoalCount")
        else:
            v = b.get(f"team_{'a' if want == 'home' else 'b'}_{field}")
    else:
        pair = (getattr(rec, block, None) or {}).get(field)
        if not pair:
            return None
        v = pair[0] if want == "home" else pair[1]
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def team_profile(prior_matches, team_id) -> dict:
    """PIT-safe per-match profile for a team from prior matches ONLY.

    `prior_matches` must already be the strictly-before-target set -- the caller enforces PIT
    and `leakage.assert_no_future_in_profile` re-checks it independently.
    """
    n = 0
    acc = {d: 0.0 for d in SIMILARITY_DIMENSIONS}
    cnt = {d: 0 for d in SIMILARITY_DIMENSIONS}
    for r in prior_matches:
        if r.home_id != team_id and r.away_id != team_id:
            continue
        n += 1
        for d in SIMILARITY_DIMENSIONS:
            block, field, persp = DIMENSION_BINDING[d]
            v = _side_value(r, team_id, block, field, persp)
            if v is not None:
                acc[d] += v
                cnt[d] += 1
    if n == 0:
        return {"team_id": team_id, "n_matches": 0,
                "dims": {d: None for d in SIMILARITY_DIMENSIONS},
                "dim_n": {d: 0 for d in SIMILARITY_DIMENSIONS}}
    return {"team_id": team_id, "n_matches": n,
            "dims": {d: (acc[d] / cnt[d] if cnt[d] else None)
                     for d in SIMILARITY_DIMENSIONS},
            "dim_n": dict(cnt)}


def competition_baseline(profiles) -> dict:
    """Per-dimension baseline (the shrinkage prior) over the PIT cohort of profiles."""
    out = {}
    for d in SIMILARITY_DIMENSIONS:
        vals = [p["dims"][d] for p in profiles if p["dims"].get(d) is not None]
        out[d] = (sum(vals) / len(vals)) if vals else None
    return out


def shrink_profile(profile, baseline, k=PROFILE_SHRINKAGE_K) -> dict:
    """Pull each dimension toward the competition baseline with strength k.

    Applies the declared PROFILE_SHRINKAGE_K so the frozen spec and the code agree. A team
    with few PIT matches is pulled hard toward the prior; a long-history team is barely moved.
    """
    dims = {}
    for d in SIMILARITY_DIMENSIONS:
        v = profile["dims"].get(d)
        n = profile["dim_n"].get(d, 0)
        prior = baseline.get(d)
        if v is None or prior is None:
            dims[d] = v if prior is None else prior
            continue
        dims[d] = (n * v + k * prior) / (n + k)
    return {"team_id": profile["team_id"], "n_matches": profile["n_matches"],
            "dims": dims, "dim_n": profile["dim_n"], "shrunk": True, "shrinkage_k": k}


def zscore_fit(profiles) -> dict:
    """Fit mean/sd per dimension on the PIT training profiles ONLY (no future)."""
    stats = {}
    for d in SIMILARITY_DIMENSIONS:
        vals = [p["dims"][d] for p in profiles if p["dims"].get(d) is not None]
        if len(vals) < 2:
            stats[d] = {"mean": (vals[0] if vals else 0.0), "sd": 1.0}
            continue
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
        stats[d] = {"mean": m, "sd": math.sqrt(var) if var > 0 else 1.0}
    return stats


def zvector(profile, fit):
    """z-scored dimension vector; missing -> 0 (cohort mean). Returns (vec, n_missing)."""
    vec, n_missing = [], 0
    for d in SIMILARITY_DIMENSIONS:
        v = profile["dims"].get(d)
        if v is None:
            vec.append(0.0)
            n_missing += 1
        else:
            s = fit[d]
            vec.append((v - s["mean"]) / (s["sd"] or 1.0))
    return vec, n_missing


def distance(a, b, metric=PRIMARY_DISTANCE) -> float:
    if metric == "euclidean_z":
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    if metric == "manhattan_z":
        return sum(abs(x - y) for x, y in zip(a, b))
    raise ValueError(f"unknown distance metric {metric}")


def shrinkage_integrity(published_spec: dict = None) -> dict:
    """Prove PROFILE_SHRINKAGE_K is consumed by production code, not merely published.

    Task 17. Three checks, all functional rather than textual:
      1. the published spec's k equals the code constant;
      2. `shrink_profile` actually MOVES a value toward the prior (so the constant is read);
      3. the movement matches the closed form (n*v + k*prior)/(n+k) at the code's own k, so a
         spec that claims a different k than the code applies is detected.

    A published parameter that exists only as prose fails here.
    """
    probe = {"team_id": "probe", "n_matches": 2,
             "dims": {d: 2.0 for d in SIMILARITY_DIMENSIONS},
             "dim_n": {d: 2 for d in SIMILARITY_DIMENSIONS}}
    prior = {d: 1.0 for d in SIMILARITY_DIMENSIONS}
    got = shrink_profile(probe, prior)["dims"][SIMILARITY_DIMENSIONS[0]]
    expect = (2 * 2.0 + PROFILE_SHRINKAGE_K * 1.0) / (2 + PROFILE_SHRINKAGE_K)
    applied = abs(got - expect) < 1e-12
    moved = abs(got - 2.0) > 1e-12
    spec_k = (published_spec or {}).get("profile_shrinkage_k")
    spec_matches = True if spec_k is None else (float(spec_k) == float(PROFILE_SHRINKAGE_K))
    problems = []
    if not applied:
        problems.append(f"shrink_profile output {got} != closed form {expect} at "
                        f"k={PROFILE_SHRINKAGE_K}")
    if not moved:
        problems.append("shrink_profile did not move the value; K is not consumed")
    if not spec_matches:
        problems.append(f"published spec k={spec_k} != code k={PROFILE_SHRINKAGE_K}")
    return {"code_k": PROFILE_SHRINKAGE_K, "spec_k": spec_k,
            "k_applied_in_production_code": applied, "value_moved": moved,
            "spec_matches_code": spec_matches,
            "integrity_ok": not problems, "problems": problems,
            "pit_safe": True,
            "note": "no published parameter may exist only as prose"}


def version_stamp() -> dict:
    return {"similarity_version": SIMILARITY_VERSION,
            "dimensions": list(SIMILARITY_DIMENSIONS),
            "dimension_bindings": {d: list(b) for d, b in DIMENSION_BINDING.items()},
            "scaling": SCALING, "scaling_fit": "PIT training profiles only",
            "missing_imputation": MISSING_IMPUTATION, "max_missing_dims": MAX_MISSING_DIMS,
            "profile_shrinkage_k": PROFILE_SHRINKAGE_K,
            "profile_shrinkage_applied": True,
            "distance_metrics_family": list(DISTANCE_METRICS),
            "primary_distance": PRIMARY_DISTANCE,
            "cohort_rule": COHORT_RULE, "k_neighbors": K_NEIGHBORS,
            "min_profile_history_matches": MIN_PROFILE_HISTORY_MATCHES,
            "tie_break": TIE_BREAK, "restrict_same_competition": RESTRICT_SAME_COMPETITION,
            "pit_safe": True, "llm_produces_similarity_score": False,
            "thresholds_tuned_per_hypothesis": False,
            "dimension_metrics": dict(DIMENSION_METRIC),
            "xg_dimension_removed_for_coverage": True,
            "coverage_claim_is_verified_not_asserted": True}

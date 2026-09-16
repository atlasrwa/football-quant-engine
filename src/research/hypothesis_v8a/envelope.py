"""V8A fixture-specific capability envelope (`v8a_envelope_v1`). Brief section 5.

The model must know what it can LEGITIMATELY research at THIS fixture. The envelope is built
from the frozen, outcome-blind V7.1 capability contract plus the measured coverage of the
actual PIT-safe prior rows the packet will carry -- never from the brief's illustrative
example, which describes a different corpus (it marks xg UNSUPPORTED; in this corpus xg is
RESTRICTED, admissible in 4/6 competitions).

FIVE DISTINCT STATES, never collapsed (brief section 5: "Unknown != zero. NULL != zero."):

    SUPPORTED             contracted, audited, admissible in every corpus competition, and
                          populated on this fixture's own prior rows above the coverage floor
    SUPPORTED_PARTIAL     admissible here but materially incomplete on THIS fixture's rows,
                          or admissible only on a frozen subset of competitions that includes
                          this one
    LOW_COVERAGE          admissible in principle, but this fixture's own rows populate it
                          too sparsely to condition on
    UNSUPPORTED           contracted and deliberately not admissible -- ambiguous semantics,
                          unaudited per-side split, or this fixture's competition is outside
                          the metric's admissible set
    UNAVAILABLE           no provider in this corpus supplies it at all

A metric that is UNKNOWN to the contract is reported as a NAMED gap under UNAVAILABLE with an
explicit `unknown_not_zero` flag, never silently dropped.

ZERO SPEND. Reads no outcome and no effect.
"""
from __future__ import annotations

import hashlib
import json

ENVELOPE_VERSION = "v8a_envelope_v1"

SUPPORTED = "SUPPORTED"
SUPPORTED_PARTIAL = "SUPPORTED_PARTIAL"
LOW_COVERAGE = "LOW_COVERAGE"
UNSUPPORTED = "UNSUPPORTED"
UNAVAILABLE = "UNAVAILABLE"

#: Population share of this fixture's own prior rows, per metric and perspective.
HIGH_COVERAGE_MIN = 0.90
LOW_COVERAGE_MAX = 0.50

#: Dimensions this corpus cannot honour as a COHORT CONDITION, with the reason. Stated from
#: the frozen V7.1 ontology, so V8A cannot quietly widen the measurable space.
STRUCTURAL_UNAVAILABLE = {
    "xg_model_internals": "the provider supplies a total-xg value, never its components",
    "injuries": "no provider in this repository supplies an injury feed",
    "expected_formation": "no provider supplies a pre-match expected formation or lineup",
    "lineup": "not derivable point-in-time safely",
    "weather": "not provided by source",
    "referee": "not provided by source",
    "player_ratings": "not provided by source",
    "market_prices": "not provided by source; the research path is price-blind by design",
    "minute_level_tactical_state": "no minute-level event feed exists in this corpus",
    "half_time_score_state": ("the corpus carries no half-time score state and no match "
                              "period marker, so no cohort may be conditioned on it"),
}


def _coverage(index, team_id, rec_i, metric, perspective):
    """Share of this team's PIT-safe prior rows on which the metric is actually populated."""
    entries = index.prior_entries(str(team_id), rec_i)
    if not entries:
        return (0.0, 0)
    n_ok = 0
    for e in entries:
        if index.team_value(e[0], str(team_id), metric, perspective) is not None:
            n_ok += 1
    return (n_ok / len(entries), len(entries))


def metric_envelope(cap, index, rec, rec_i, metric):
    """The five-state verdict for one metric at one fixture, both perspectives."""
    status, detail = cap.classify_metric(metric)

    if status == "UNKNOWN":
        return {"status": UNAVAILABLE, "unknown_not_zero": True,
                "reason": detail, "coverage": None}
    if status == "UNSUPPORTED":
        return {"status": UNSUPPORTED, "reason": detail, "coverage": None}

    adm = cap.admissible_competitions(metric)
    if rec.competition not in adm:
        return {"status": UNSUPPORTED,
                "reason": (f"metric is not admissible in this fixture's competition "
                           f"({rec.competition}); admissible in {sorted(adm)}"),
                "coverage": None}

    cov = {}
    worst = 1.0
    for role, team in (("home", rec.home_id), ("away", rec.away_id)):
        for perspective in ("FOR", "AGAINST"):
            share, n = _coverage(index, team, rec_i, metric, perspective)
            cov[f"{role}_{perspective}"] = {"populated_share": round(share, 4),
                                            "n_prior_rows": n}
            worst = min(worst, share)

    if worst < LOW_COVERAGE_MAX:
        out = LOW_COVERAGE
        reason = (f"populated on only {worst:.1%} of the thinnest side's prior rows; "
                  f"below {LOW_COVERAGE_MAX:.0%} this is too sparse to condition on")
    elif worst < HIGH_COVERAGE_MIN or status == "RESTRICTED":
        out = SUPPORTED_PARTIAL
        reason = (f"{detail}; thinnest per-fixture population {worst:.1%}")
    else:
        out = SUPPORTED
        reason = f"{detail}; thinnest per-fixture population {worst:.1%}"

    return {"status": out, "reason": reason, "coverage": cov,
            "contract_status": status,
            "admissible_competitions": sorted(adm),
            "perspectives": ["FOR", "AGAINST"],
            "temporal_resolution": cap.resolution_of(metric)}


def formation_context(index, rec, rec_i, records_by_pos):
    """Formation is CONTEXT, never a cohort condition (brief section 3).

    The V7.1 ontology declares own_formation_family and opponent_formation_family
    UNSUPPORTED -- "formation is not resolvable per prior match in this corpus". That verdict
    is reported verbatim so a model cannot mistake sparse visibility for measurability.
    """
    seen = {}
    for role, team in (("home", rec.home_id), ("away", rec.away_id)):
        entries = index.prior_entries(str(team), rec_i)
        n_rec = 0
        for e in entries:
            r = records_by_pos(e[0])
            f = _recorded_formation(r, team)
            if f:
                n_rec += 1
        share = (n_rec / len(entries)) if entries else 0.0
        seen[role] = {"rows_with_recorded_formation": n_rec,
                      "n_prior_rows": len(entries),
                      "recorded_share": round(share, 4)}
    worst = min(v["recorded_share"] for v in seen.values()) if seen else 0.0
    return {
        "status": SUPPORTED_PARTIAL if worst > 0 else UNAVAILABLE,
        "usable_as_cohort_condition": False,
        "why_not_a_condition": ("v71_ontology.KNOWN_UNSUPPORTED_DIMENSIONS: formation is "
                                "not resolvable per prior match in this corpus, so a "
                                "formation-CONDITIONED cohort is rejected by the compiler"),
        "usable_as": ("context that may MOTIVATE a question about measurable raw behaviour"),
        "per_side": seen,
    }


def _recorded_formation(rec, team_id):
    """Reuse the canonical reader rather than restating it, so V8A and the earlier
    experiments can never disagree about whether a formation was recorded."""
    from src.research.hypothesis_engine import corpus_adapter as CA
    team = rec.home if str(rec.home_id) == str(team_id) else rec.away
    return CA.team_formation_family(rec, team)


def build(cap, index, rec, rec_i, metrics, records_by_pos):
    """The full fixture-specific envelope handed to the model."""
    env = {m: metric_envelope(cap, index, rec, rec_i, m) for m in sorted(metrics)}
    dims = {
        "historical_venue_conditioning": {
            "status": SUPPORTED, "values": ["HOME", "AWAY"],
            "reason": "every prior row carries the venue it was played at"},
        "opponent_profile": {
            "status": SUPPORTED, "values": ["HIGH", "MID", "LOW"],
            "axes_are_chosen_by_the_engine": True,
            "reason": ("restrict to prior matches whose OPPONENT sat in that point-in-time "
                       "tercile of the named profile axis, within the opponent's own "
                       "competition")},
        "competition": {
            "status": SUPPORTED, "values": ["SAME"],
            "reason": "restrict to prior matches in the target fixture's competition"},
        "similar_opponent_cohort": {
            "status": SUPPORTED,
            "dimensions_are_FROZEN": True,
            "frozen_dimensions": ["goals_conceded_per_match",
                                  "shots_on_target_conceded_per_match",
                                  "shots_inside_box_conceded_per_match",
                                  "fouls_committed_per_match",
                                  "yellow_cards_per_match"],
            "reason": ("the engine builds similarity from a FROZEN 5-dimension defensive / "
                       "discipline profile. You may ask for a similar-opponent cohort; you "
                       "may NOT choose or compute the similarity dimensions")},
    }
    dims["own_formation_family"] = formation_context(index, rec, rec_i, records_by_pos)
    dims["opponent_formation_family"] = dict(dims["own_formation_family"])

    for k, why in sorted(STRUCTURAL_UNAVAILABLE.items()):
        dims[k] = {"status": UNAVAILABLE, "reason": why,
                   "unavailable_is_not_zero": True}

    return {"envelope_version": ENVELOPE_VERSION,
            "fixture_id": str(rec.fixture_id),
            "competition": rec.competition,
            "metrics": env,
            "research_dimensions": dims,
            "state_meanings": {
                SUPPORTED: "measurable here, well populated",
                SUPPORTED_PARTIAL: "measurable here but incomplete; expect reduced support",
                LOW_COVERAGE: "too sparsely populated at this fixture to condition on",
                UNSUPPORTED: "the engine will refuse it: semantics or competition admissibility",
                UNAVAILABLE: "no provider supplies it; absence is not a zero"},
            "reads_outcomes": False, "reads_effects": False}


def envelope_hash(env: dict) -> str:
    return hashlib.sha256(
        json.dumps(env, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

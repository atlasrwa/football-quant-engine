"""ITEM 6 STAGE 2 provider measurability substrate (`item6_stage2_provider_measurability_v1`).

The authoritative, outcome-blind answer to "can this Item 6 metric actually be MEASURED
historically from the FootyStats corpus, at what temporal resolution?"

WHY THIS MODULE EXISTS (the central Stage-1 -> Stage-2 gap)
----------------------------------------------------------
Stage 1's `provider_vocab.PROVIDER_METRICS` is the *discovery* vocabulary: the set of
concepts a mechanism was ALLOWED to invoke. It is deliberately wider than what the
FootyStats corpus records, because it also admits TheStatsAPI-side concepts. Stage 1
evidence packets therefore carried only the subset genuinely sourced from FootyStats, and
Stage 1's own diagnostics found 316/595 mechanisms naming a vocabulary-legal metric that was
absent from their own packet.

    STAGE 1 PACKET PRESENCE  !=  STAGE 2 HISTORICAL MEASURABILITY.

This module resolves that question empirically against the corpus schema, not by assumption.
Verified against the corpus record schema (215 fields per match): there is NO crosses,
blocks, tackles, clearances, interceptions, recoveries, touches, passes or big-chances field
anywhere in the FootyStats league-matches corpus. Those concepts are UNMEASURABLE historically
and the families requiring them are excluded -- not because Stage 1 was wrong to propose them,
but because this provider cannot test them.

PROVIDER DISCIPLINE
-------------------
  * FootyStats is the only measurement substrate for Stage 2.
  * TheStatsAPI-only concepts are NOT substituted for similarly named FootyStats fields.
  * npxG remains excluded and is not reintroduced.
  * FootyStats `team_a_xg` is NOT admitted: xg is absent from the frozen Item 6 discovery
    vocabulary, so admitting it here would introduce a metric the LLM was never shown.

Reads no outcome, no market, no LLM output, and makes no model call.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Tuple

PROVIDER_MEASURABILITY_VERSION = "item6_stage2_provider_measurability_v1"

RES_MATCH = "match"
RES_HALF = "half"
RES_UNAVAILABLE = "unavailable"

# --- the FootyStats measurement substrate -------------------------------------------------
# Canonical Item 6 metric -> the per-side FootyStats field base (team_a_<base>/team_b_<base>).
# This mirrors packet_materializer.FULL_MATCH_FIELD exactly: the same 10 metrics that the
# frozen Stage-1 materializer was able to source. Kept as an independent declaration (rather
# than an import) so a drift between the two is caught by a test instead of silently inherited.
FOOTYSTATS_FULL_MATCH_FIELD: Dict[str, str] = {
    "goals": "__goals__",
    "shots": "shots",
    "shots_on_target": "shotsOnTarget",
    "corner_kicks": "corners",
    "possession": "possession",
    "fouls": "fouls",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "offsides": "offsides",
    "cards_2h": "2h_cards",
}

# Metrics that additionally support a genuine FIRST_HALF / SECOND_HALF split in the corpus.
# `cards_2h` is itself a second-half construction and is half-resolved by definition.
FOOTYSTATS_HALF_FIELD: Dict[str, Dict[str, str]] = {
    "corner_kicks": {"FIRST_HALF": "fh_corners", "SECOND_HALF": "2h_corners"},
    "goals": {"FIRST_HALF": "__ht_goals__", "SECOND_HALF": "__2h_goals__"},
}
HALF_CAPABLE: FrozenSet[str] = frozenset(set(FOOTYSTATS_HALF_FIELD) | {"cards_2h"})

# AGAINST-perspective aliases. These are NOT new metrics: the deterministic engine already
# measures opponent-side values through the same field pair (the champion's own feature pool
# carries e.g. h_shots_against_std / a_shotsOnTarget_against_std), so an `X_against` /
# `X_conceded` concept resolves to (X, AGAINST) with no new provider dependency.
AGAINST_ALIAS: Dict[str, str] = {
    "goals_conceded": "goals",
    "shots_against": "shots",
    "shots_on_target_against": "shots_on_target",
}

PERSPECTIVE_FOR = "FOR"
PERSPECTIVE_AGAINST = "AGAINST"

# Vocabulary-legal Stage-1 concepts with NO FootyStats field. Recorded explicitly (rather than
# inferred by absence) so the funnel reports a positive, auditable reason.
FOOTYSTATS_ABSENT: FrozenSet[str] = frozenset({
    "accurate_crosses", "blocks", "clearances", "tackles", "interceptions",
    "ball_recoveries", "touches_in_penalty_area", "passes", "pass_accuracy",
    "big_chances", "big_chances_against",
})

# Structural (non-metric) observables the engine conditions on rather than measures.
STRUCTURAL_OBSERVABLES: FrozenSet[str] = frozenset({
    "venue_home_away", "competition_label", "prior_match_scoreline",
    "formation_recorded_prior_match",
})


def resolve(metric: str) -> Tuple[Optional[str], str, str]:
    """(base_metric, perspective, resolution) for an Item 6 metric name.

    base_metric is None when the concept is not historically measurable from FootyStats.
    """
    m = metric.strip().lower()
    perspective = PERSPECTIVE_FOR
    if m in AGAINST_ALIAS:
        m = AGAINST_ALIAS[m]
        perspective = PERSPECTIVE_AGAINST
    if m not in FOOTYSTATS_FULL_MATCH_FIELD:
        return None, perspective, RES_UNAVAILABLE
    return m, perspective, (RES_HALF if m in HALF_CAPABLE else RES_MATCH)


def is_measurable(metric: str) -> bool:
    return resolve(metric)[0] is not None


def is_half_capable(metric: str) -> bool:
    base, _, _ = resolve(metric)
    return base is not None and base in HALF_CAPABLE


def unmeasurable_metrics(metrics) -> list:
    """The subset of `metrics` that FootyStats cannot measure historically (sorted)."""
    return sorted({m for m in metrics if not is_measurable(m)})


def version_stamp() -> Dict[str, object]:
    return {
        "provider_measurability_version": PROVIDER_MEASURABILITY_VERSION,
        "substrate": "footystats_league_matches_corpus",
        "n_measurable_metrics": len(FOOTYSTATS_FULL_MATCH_FIELD),
        "n_half_capable": len(HALF_CAPABLE),
        "n_against_aliases": len(AGAINST_ALIAS),
        "thestatsapi_substitution_allowed": False,
        "npxg_reintroduced": False,
        "xg_admitted": False,
        "reads_outcomes": False,
        "reads_llm_output": False,
    }

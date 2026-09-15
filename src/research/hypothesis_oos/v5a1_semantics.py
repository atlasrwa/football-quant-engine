"""V5A.1 provider-semantics registry (`provider_semantics_v1`).

Task §17: every metric exposed to the model must have its source field, direction, units,
provider semantics and merge policy documented -- and the documentation must be MODEL-VISIBLE,
not merely recorded in a preregistration the model never sees. V5A's packets carried a bare
list of 27 metric names with no definitions and no provenance, and the model was told that
list was "the closed set of metrics you may use".

Every claim in `METRIC_SEMANTICS` below was verified against the raw provider payloads; the
measurements are reproduced in `research/hypothesis_engine/V5A1_PROVIDER_SEMANTICS_AUDIT.md`.

ZERO SPEND. Declarative module; no model, no network.
"""
from __future__ import annotations

PROVIDER_SEMANTICS_VERSION = "provider_semantics_v1"

#: The corpus is single-provider for every metric exposed here. TheStatsAPI is read through
#: scripts/championship_adapter; the FootyStats-schema key names in `MatchRecord.base`
#: (e.g. `team_a_xg`) are SCHEMA names only -- the VALUES are TheStatsAPI's. That distinction
#: is what the V5A audit's M-8 got wrong when it inferred a cross-provider merge.
PROVIDER = "thestatsapi"

_C = "count"
_F = "float_xg"
_P = "percent"


def _m(source, units, desc, *, direction="higher_is_more", null_policy="NULL_IS_MISSING",
       merge_policy="SINGLE_SOURCE_NO_MERGE", caveat=None):
    d = {"source_field": source, "provider": PROVIDER, "units": units,
         "definition": desc, "direction": direction, "null_policy": null_policy,
         "merge_policy": merge_policy}
    if caveat:
        d["caveat"] = caveat
    return d


#: Canonical metric -> model-visible semantics. This is serialized into BOTH arms' packets,
#: ONCE (task §12), not repeated per cell.
METRIC_SEMANTICS = {
    "accurate_crosses": _m(
        "thestatsapi passes.accurate_crosses", _C,
        "Crosses COMPLETED to a team-mate. This is a completion COUNT, not an accuracy "
        "rate: the corpus does not carry crosses ATTEMPTED, so no completion percentage "
        "can be formed from this packet.",
        caveat="No attempts denominator exists. Do not treat this as a ratio."),
    "big_chances": _m(
        "thestatsapi overview.big_chances", _C,
        "Provider-judged clear scoring opportunities. A subjective provider classification, "
        "not a geometric definition."),
    "blocked_shots": _m(
        "thestatsapi shots.blocked_shots", _C,
        "Shots by the subject blocked by an outfield defender. Counted INSIDE total_shots "
        "(verified: total_shots == on_target + off_target + blocked in 3266/3272 "
        "team-matches)."),
    "clearances": _m("thestatsapi defending.clearances", _C,
                     "Defensive clearances by the subject."),
    "corners": _m("thestatsapi overview.corner_kicks", _C,
                  "Corner kicks taken by the subject."),
    "final_third_entries": _m("thestatsapi passes.final_third_entries", _C,
                              "Completed passes entering the final third."),
    "fouls": _m("thestatsapi overview.fouls", _C, "Fouls committed by the subject."),
    "goals": _m("thestatsapi fixture score (score_home / score_away)", _C,
                "Full-time goals. Taken from the fixture result, not the stats block."),
    "interceptions": _m("thestatsapi defending.interceptions", _C,
                        "Interceptions by the subject."),
    "offsides": _m("thestatsapi attack.offsides", _C,
                   "Offsides called against the subject."),
    "possession": _m(
        "thestatsapi overview.ball_possession", _P,
        "Share of ball possession, in PERCENT. Verified to sum to 100 across the two teams "
        "in 1636/1636 matches, so possession_for and possession_against are complementary "
        "and carry the same information."),
    "red_cards": _m(
        "thestatsapi overview.red_cards", _C,
        "Red cards shown to the subject.",
        null_policy="NULL_COERCED_TO_ZERO_AT_ADAPTER",
        caveat="The provider omits this field in 2988/3312 team-matches and emits an "
               "explicit 0 in 154. Treating null as zero yields a red-card rate of 170 in "
               "3152 reported team-matches (5.4%), which matches the real-world rate, so "
               "the coercion is justified -- but a 0 in this column may be a provider "
               "omission rather than an observed zero."),
    "saves": _m("thestatsapi goalkeeping.saves", _C, "Goalkeeper saves by the subject."),
    "shots_inside_box": _m(
        "thestatsapi shots.shots_inside_box", _C,
        "Shots taken inside the penalty area. Verified: inside + outside == total_shots in "
        "3270/3272 team-matches, so this decomposition is exhaustive."),
    "shots_off_target": _m("thestatsapi shots.shots_off_target", _C,
                           "Shots missing the target and not blocked."),
    "shots_on_target": _m("thestatsapi overview.shots_on_target", _C,
                          "Shots on target, including those saved and those scored."),
    "shots_outside_box": _m("thestatsapi shots.shots_outside_box", _C,
                            "Shots taken outside the penalty area."),
    "tackles": _m("thestatsapi defending.tackles", _C, "Tackles by the subject."),
    "throw_ins": _m("thestatsapi passes.throw_ins", _C, "Throw-ins taken by the subject."),
    "total_shots": _m(
        "thestatsapi overview.total_shots", _C,
        "All shots by the subject. Verified equal to on_target + off_target + blocked, and "
        "to inside_box + outside_box; both decompositions are exhaustive."),
    "touches_in_box": _m("thestatsapi attack.touches_in_penalty_area", _C,
                         "Touches by the subject inside the opposition penalty area."),
    "xg": _m(
        "thestatsapi overview.expected_goals", _F,
        "TOTAL expected goals, PENALTIES INCLUDED. A provider model estimate, not an "
        "observation; treat it as the provider's summary of chance quality.",
        caveat="Available for 78.9% of corpus matches. Non-penalty xG is NOT exposed in "
               "this packet -- see the excluded-metrics section for why."),
    "yellow_cards": _m("thestatsapi overview.yellow_cards", _C,
                       "Yellow cards shown to the subject.",
                       caveat="A second yellow that becomes a red is counted by the "
                              "provider in both columns; the packet cannot separate them."),
}

CANONICAL_METRICS = tuple(sorted(METRIC_SEMANTICS))

# ----------------------------------------------------------------------------------------
# Excluded metrics. Task §16/§17: nothing ambiguous is silently kept, and nothing excluded
# is silently dropped -- the exclusion and its reason are serialized into the packet so the
# model can see that the omission is deliberate.
# ----------------------------------------------------------------------------------------
EXCLUDED_METRICS = {
    "npxg": {
        "excluded_because": "PROVIDER_SOURCE_INCONSISTENCY",
        "detail":
            "np_expected_goals and overview.expected_goals both come from TheStatsAPI, and "
            "the intended relationship (npxG = xG minus penalty xG) is confirmed by the "
            "raw data: 2214/3242 pairs are exactly equal (no penalty), 182 differ by ~0.8 "
            "(one penalty) and 6 by ~1.6 (two). But 511/3242 pairs (15.8%) have npxG "
            "GREATER than xG, by up to 0.99, which that relationship makes impossible. The "
            "error distribution is smooth rather than penalty-shaped, indicating two "
            "independently-maintained provider estimates rather than a derived pair. The "
            "corpus carries no penalty or penalty-xG field, so npxG cannot be recomputed "
            "from xG. Per the V5A.1 mandate, a metric whose cell-level semantics cannot be "
            "confidently validated is excluded rather than exposed with a caveat.",
        "repairable_by": "a provider penalty-xG field, or a single reconciled xG feed",
    },
    "dangerous_attacks": {
        "excluded_because": "SEMANTIC_CONFLICT_NO_CANONICAL_MAPPING",
        "detail":
            "The corpus carries only touches_in_penalty_area as a proxy. There is no "
            "validated mapping from that proxy to the FootyStats 'dangerous attacks' "
            "concept, so exposing it under that name would be a false canonical metric "
            "created by name matching. touches_in_box IS exposed, under its own name.",
        "repairable_by": "a provider field with a documented dangerous-attacks definition",
    },
    "attacks": {
        "excluded_because": "NOT_PROVIDED_BY_SOURCE",
        "detail": "No field in either audited corpus supplies it.",
        "repairable_by": "a provenance-tracked provider field",
    },
    "total_bookings": {
        "excluded_because": "DERIVED_NOT_OBSERVED",
        "detail":
            "Would be yellow_cards + red_cards, but red_cards carries a null-coerced-to-"
            "zero policy and a second yellow is double-counted, so the sum is not a clean "
            "observation. Both components are exposed separately instead.",
        "repairable_by": "a provider bookings field, or a red-card null policy fix",
    },
}

# ----------------------------------------------------------------------------------------
# Non-metric context that is NOT available. Serialized so the model never has to guess.
# ----------------------------------------------------------------------------------------
UNSUPPORTED_CONTEXT = {
    "expected_formation":
        "No provider in this repository supplies a pre-match expected formation or a "
        "timestamped lineup feed. The UPCOMING fixture's formation is UNKNOWN and is not in "
        "this packet. Only RECORDED historical formations are present.",
    "lineup":
        "Lineups exist for completed matches but carry no announcement timestamp, so they "
        "cannot be shown to be point-in-time safe for an upcoming fixture.",
    "injuries": "No injury or availability field exists in either audited corpus.",
    "weather": "Not present in either corpus.",
    "player_ratings": "Not surfaced by the adapters in use.",
    "referee": "Not surfaced by the adapter used for this corpus.",
    "minute_level_events":
        "Only GOAL minutes are timestamped. No timestamped corner, shot, cross, tackle, "
        "card or substitution events exist, so no 'in the N minutes after X' conditioning "
        "is possible for any metric other than goals.",
    "half_time_state":
        "Half-level metric coverage measured at 0% in this corpus, so no half-time score "
        "state or first/second-half split is derivable.",
    "market_prices":
        "Deliberately absent. This packet is a research-question input; it carries no odds, "
        "no market state and no fixture outcome.",
}

#: Canonical side suffixes used in every cell column and every evidence id.
SIDES = ("for", "against")


def cell_columns() -> list:
    """The canonical metric cell columns, in a stable order. One entry per metric x side."""
    out = []
    for m in CANONICAL_METRICS:
        out += [f"{m}_for", f"{m}_against"]
    return out


def metric_semantics_block() -> dict:
    """The model-visible semantics section. Emitted ONCE per packet (task §12)."""
    return {
        "provider_semantics_version": PROVIDER_SEMANTICS_VERSION,
        "orientation_rule":
            "Every metric column is written from the SUBJECT team's perspective in that "
            "match. '<metric>_for' is what the subject recorded; '<metric>_against' is what "
            "its opponent in that match recorded. This is INDEPENDENT of the 'venue' field, "
            "which says whether the subject played at home or away in that match. A row "
            "with venue=AWAY still reports the subject's own production under '_for'.",
        "null_rule":
            "A null cell means the provider did not report that value for that match. It is "
            "never a zero and never an omitted column: every column is present in every row.",
        "reliability_rule": None,      # filled in by the packet builder from the evidence module
        "metrics": METRIC_SEMANTICS,
        "excluded_metrics": EXCLUDED_METRICS,
        "unsupported_context": UNSUPPORTED_CONTEXT,
    }

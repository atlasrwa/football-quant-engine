"""ITEM 6 provider vocabulary (`item6_provider_vocab_v1`).

The bounded set of observable, provider-supported concepts a mechanism may reference,
plus the data-resolution each is available at. This is the controlled vocabulary the
deterministic formalizer maps free-text variable references onto.

Design tension resolved deliberately (KEY DESIGN CHANGE #2 / "DO NOT OVERCONSTRAIN"):
  - mechanism SEMANTICS are controlled free text (so the LLM can transcend the V2/V3
    grammar during discovery), BUT
  - the observable concepts it may invoke are bounded and machine-auditable here.
Downstream deterministic parsing/formalization decides measurability; the LLM never does.

Nothing here reads an outcome, a market, or any LLM output.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

PROVIDER_VOCAB_VERSION = "item6_provider_vocab_v1"

# resolution levels, coarse-to-fine
RES_MATCH = "match"       # one value per completed match
RES_HALF = "half"         # first-half / second-half split available
RES_UNAVAILABLE = "unavailable"


# canonical observable metrics -> resolution actually supported by the provider.
# Half-resolution is only declared where the provider genuinely records it
# (cards_2h is a second-half count; goals/shots have HT/FT splits in the corpus).
PROVIDER_METRICS: Dict[str, str] = {
    "goals": RES_HALF,
    "goals_conceded": RES_HALF,
    "shots": RES_MATCH,
    "shots_on_target": RES_MATCH,
    "shots_against": RES_MATCH,
    "shots_on_target_against": RES_MATCH,
    "big_chances": RES_MATCH,
    "big_chances_against": RES_MATCH,
    "corner_kicks": RES_MATCH,
    "accurate_crosses": RES_MATCH,
    "possession": RES_MATCH,
    "touches_in_penalty_area": RES_MATCH,
    "ball_recoveries": RES_MATCH,
    "tackles": RES_MATCH,
    "interceptions": RES_MATCH,
    "blocks": RES_MATCH,
    "clearances": RES_MATCH,
    "fouls": RES_MATCH,
    "yellow_cards": RES_MATCH,
    "red_cards": RES_MATCH,
    "cards_2h": RES_HALF,
    "offsides": RES_MATCH,
    "passes": RES_MATCH,
    "pass_accuracy": RES_MATCH,
    # historical formation for COMPLETED prior matches is PIT-safe context (V8B1 packet spec).
    "formation_recorded_prior_match": RES_MATCH,
    # venue / competition / recorded scoreline of a COMPLETED prior match are observable.
    "venue_home_away": RES_MATCH,
    "competition_label": RES_MATCH,
    "prior_match_scoreline": RES_HALF,
}

# Concepts that are explicitly UNSUPPORTED / provider-unsafe. A mechanism that requires any
# of these is rejected at formalization (F0/F2). Substring-matched against variable text.
PROVIDER_UNSAFE_CONCEPTS: Tuple[str, ...] = (
    "injury",
    "injuries",
    "injured",
    "suspension",
    "suspended",
    "expected lineup",
    "expected line-up",
    "predicted lineup",
    "predicted xi",
    "starting xi announced",
    "manager intention",
    "managerial intention",
    "tactical switch",
    "tactical instruction",
    "in-game tactical change",
    "unobserved",
    "morale",
    "fatigue index",
    "travel distance",
    "weather",
    "referee identity",
    "transfer",
    "contract",
    "expected lineups",
)

# Concepts that indicate FUTURE / leakage information (never available pre-kickoff of target).
FUTURE_LEAKAGE_CONCEPTS: Tuple[str, ...] = (
    "closing line",
    "closing odds",
    "settlement",
    "final score of this match",
    "target match result",
    "post-match",
    "post match",
    "full-time result of the target",
    "actual outcome of the fixture",
    "this fixture's goals",
    "this match's",
)


def is_supported_metric(name: str) -> bool:
    return name in PROVIDER_METRICS


def resolution_of(name: str) -> str:
    return PROVIDER_METRICS.get(name, RES_UNAVAILABLE)


def half_resolution_metrics() -> List[str]:
    return sorted(m for m, r in PROVIDER_METRICS.items() if r == RES_HALF)


def version_stamp() -> Dict[str, object]:
    return {
        "provider_vocab_version": PROVIDER_VOCAB_VERSION,
        "n_metrics": len(PROVIDER_METRICS),
        "n_half_resolution": len(half_resolution_metrics()),
        "n_unsafe_concepts": len(PROVIDER_UNSAFE_CONCEPTS),
        "n_future_leakage_concepts": len(FUTURE_LEAKAGE_CONCEPTS),
        "reads_outcomes": False,
        "reads_llm_output": False,
    }

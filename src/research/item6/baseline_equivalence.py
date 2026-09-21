"""BASELINE_EQUIVALENCE_DETECTOR_V1  (`item6_baseline_equivalence_v1`).

Deterministic classifier: given a validated Mechanism, decide whether it is
semantically/structurally EQUIVALENT to a family the deterministic baseline already
covers (see baseline_coverage.BASELINE_COVERED_FAMILIES).

Frozen rules (fixed BEFORE any live generation; part of Stage-1 scoring):

  R1 SINGLE-METRIC MIRROR      one metric, for-vs-against, no extra conditioning  -> equivalent
  R2 UNIVARIATE PROFILE SPLIT  one metric + <=1 opponent-profile band             -> equivalent
  R3 SIMPLE VENUE CONTRAST     one metric + only venue conditioning               -> equivalent
  R4 RECENT-VS-LONGRUN         one metric + only recent-window vs long-run         -> equivalent
  R5 ENVIRONMENT BASELINE      one metric vs league/competition baseline           -> equivalent
  R6 COVERED 2D INTERACTION    venue x profile OR competition x profile (single metric) -> equivalent
  R7 SIMILARITY COHORT         one metric over 'similar opponents' only            -> equivalent
  R8 SELECTION-ONLY            merely ranks/selects existing candidates            -> equivalent

A mechanism is NON-baseline-equivalent only if it evades ALL of R1..R8, which in practice
requires at least one of the declared BASELINE_UNSUPPORTED_STRUCTURES: >1 distinct metric
in genuine interaction, two-axis profile intersection, a threshold/nonlinearity, a
half/game-state construction, a cross-metric asymmetry, or a sequencing/regime construction.

Detection is deterministic and text-driven but NOT outcome-aware: it never reads a target
outcome, market, or OOS result. It reads only the mechanism's own fields + the frozen
baseline coverage spec + provider vocabulary.

The classifier is intentionally CONSERVATIVE toward "equivalent": ambiguous, vague, or
single-metric mechanisms default to baseline-equivalent. This protects against the failure
mode where cosmetic novelty (rephrasing a mirror) is scored as genuine expansion. Novelty
must be earned by unambiguous structural signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .baseline_coverage import (
    BASELINE_COVERAGE_VERSION,
    BASELINE_PROFILE_AXES,
)
from .provider_vocab import PROVIDER_METRICS
from .schema import Mechanism

BASELINE_EQUIVALENCE_VERSION = "item6_baseline_equivalence_v1"

# metric surface words -> canonical metric, for detecting how many DISTINCT metrics a
# mechanism invokes. Keys are lowercase surface forms; values are canonical metric ids.
_METRIC_SURFACE: Dict[str, str] = {}
for _m in PROVIDER_METRICS:
    _METRIC_SURFACE[_m.replace("_", " ")] = _m
    _METRIC_SURFACE[_m] = _m
# common english surface synonyms mapped to canonical metrics
_METRIC_SURFACE.update({
    "corner": "corner_kicks",
    "corners": "corner_kicks",
    "cross": "accurate_crosses",
    "crosses": "accurate_crosses",
    "shot on target": "shots_on_target",
    "shots on target": "shots_on_target",
    "shot": "shots",
    "shots": "shots",
    "possession": "possession",
    "tackle": "tackles",
    "tackles": "tackles",
    "foul": "fouls",
    "fouls": "fouls",
    "card": "yellow_cards",
    "cards": "yellow_cards",
    "block": "blocks",
    "blocks": "blocks",
    "goal": "goals",
    "goals": "goals",
    "big chance": "big_chances",
    "big chances": "big_chances",
    "penalty area touch": "touches_in_penalty_area",
    "touches in the penalty area": "touches_in_penalty_area",
    "clearance": "clearances",
    "clearances": "clearances",
    "interception": "interceptions",
    "interceptions": "interceptions",
    "recovery": "ball_recoveries",
    "recoveries": "ball_recoveries",
    "offside": "offsides",
    "offsides": "offsides",
    "pass accuracy": "pass_accuracy",
})

_THRESHOLD_WORDS = re.compile(
    r"\b(threshold|exceed|above|below|more than|greater than|fewer than|less than|"
    r"at least|at most|cutoff|cut-off|nonlinear|non-linear|piecewise|saturat|"
    r"diminishing|inflection|tipping point|beyond a|crosses? \d)\b",
    re.IGNORECASE,
)
_HALF_STATE_WORDS = re.compile(
    r"\b(first half|second half|1st half|2nd half|half-?time|ht |at ht|"
    r"when (leading|trailing|level|ahead|behind)|after (going|conceding|scoring)|"
    r"game state|scoreline|when (winning|losing|drawing)|once (ahead|behind))\b",
    re.IGNORECASE,
)
_SEQUENCE_WORDS = re.compile(
    r"\b(consecutive|streak|sequence|trajectory|momentum over|run of|"
    r"back-to-back|successive|trend across|slope of|accelerat|regime shift|"
    r"following a (win|loss|draw))\b",
    re.IGNORECASE,
)
_TWO_AXIS_PROFILE = re.compile(
    r"\b(both|jointly|simultaneously|combination of|intersection of|and also (high|low))\b",
    re.IGNORECASE,
)
_MIRROR_WORDS = re.compile(
    r"\b(mirror|for versus against|for vs against|attack versus (their|its) (concession|defen)|"
    r"scores? more .* than .* concede|their own .* vs .* conceded)\b",
    re.IGNORECASE,
)
_SELECTION_ONLY = re.compile(
    r"\b(rank|select the most|pick the|prioriti[sz]e|salience|choose the best|"
    r"order the candidates)\b",
    re.IGNORECASE,
)


@dataclass
class EquivalenceVerdict:
    is_baseline_equivalent: bool
    matched_rule: str            # e.g. "R2_UNIVARIATE_PROFILE_SPLIT" or "NONE"
    matched_family_id: str       # baseline family id or "NONE"
    distinct_metrics: List[str]
    novelty_signals: List[str]   # structural escape-hatch signals detected
    rationale: str


def _mechanism_text(m: Mechanism) -> str:
    return " ".join([
        m.mechanism_statement,
        m.conditioning_logic,
        m.expected_relationship_to_test,
        m.why_not_baseline_equivalent,
        " ".join(m.observable_variables),
    ])


# Structural (non-metric) observables: they are provider-supported concepts but must NOT be
# counted as distinct METRICS for interaction detection.
_STRUCTURAL_OBSERVABLES = frozenset({
    "venue_home_away", "competition_label", "formation_recorded_prior_match",
    "prior_match_scoreline",
})

# Profile-axis surface phrases (e.g. "goals for") must not be miscounted as the base metric
# ("goals"). We strip them from the free-text scan first.
_PROFILE_AXIS_PHRASES = tuple(sorted(
    set([ax.replace("_", " ") for ax in BASELINE_PROFILE_AXES]
        + [ax for ax in BASELINE_PROFILE_AXES]),
    key=len, reverse=True))


def distinct_metrics(m: Mechanism) -> List[str]:
    """Canonical distinct provider metrics referenced by the mechanism (variables + text).

    Excludes structural observables (venue/competition/formation/scoreline). Avoids
    substring over-matching by (a) consuming longer surfaces before shorter ones and
    (b) stripping opponent-profile-axis phrases (which name a *conditioning band*, not a
    target metric) before the text scan.
    """
    found = set()
    # explicit variables first (authoritative) — but skip structural observables.
    for v in m.observable_variables:
        vl = v.strip().lower()
        if vl in _STRUCTURAL_OBSERVABLES:
            continue
        if vl in PROVIDER_METRICS and vl not in _STRUCTURAL_OBSERVABLES:
            found.add(vl)
        elif vl in _METRIC_SURFACE:
            found.add(_METRIC_SURFACE[vl])
    # free-text scan: remove profile-axis phrases first so "goals for" doesn't leak "goals".
    text = _mechanism_text(m).lower()
    for phrase in _PROFILE_AXIS_PHRASES:
        text = text.replace(phrase, " __axis__ ")
    # consume longest surfaces first, blanking matched spans so 'shots' can't re-match
    # inside 'shots on target'.
    for surface in sorted(_METRIC_SURFACE, key=len, reverse=True):
        canon = _METRIC_SURFACE[surface]
        if canon in _STRUCTURAL_OBSERVABLES:
            continue
        pat = rf"(^|[^a-z])({re.escape(surface)})([^a-z]|$)"
        if re.search(pat, text):
            found.add(canon)
            text = re.sub(pat, r"\1 __m__ \3", text)
    return sorted(found)


def _profile_axes_referenced(text: str) -> List[str]:
    axes = []
    for ax in BASELINE_PROFILE_AXES:
        if ax.replace("_", " ") in text.lower() or ax in text.lower():
            axes.append(ax)
    return axes


def novelty_signals(m: Mechanism) -> List[str]:
    """Structural escape-hatch signals that could make a mechanism non-baseline-equivalent."""
    text = _mechanism_text(m)
    sig: List[str] = []
    dm = distinct_metrics(m)
    if len(dm) >= 2:
        sig.append("US_MULTI_METRIC_INTERACTION")
    if _TWO_AXIS_PROFILE.search(text) and len(_profile_axes_referenced(text)) >= 2:
        sig.append("US_TWO_DIM_OPP_PROFILE_INTERSECTION")
    if _THRESHOLD_WORDS.search(text):
        sig.append("US_THRESHOLD_NONLINEARITY")
    if _HALF_STATE_WORDS.search(text) or m.data_resolution_required == "half":
        sig.append("US_HALF_STATE_OR_GAME_STATE")
    if len(dm) >= 2 and re.search(r"\b(asymmetr|different metric|distinct metric)\b", text, re.I):
        sig.append("US_CROSS_METRIC_ASYMMETRY")
    if _SEQUENCE_WORDS.search(text):
        sig.append("US_SEQUENCING_REGIME")
    return sorted(set(sig))


def classify(m: Mechanism) -> EquivalenceVerdict:
    text = _mechanism_text(m)
    dm = distinct_metrics(m)
    sig = novelty_signals(m)

    # R8 selection-only
    if _SELECTION_ONLY.search(text) and not sig:
        return EquivalenceVerdict(True, "R8_SELECTION_ONLY", "BC_SALIENCE_RANKING",
                                  dm, sig, "Mechanism only ranks/selects existing candidates.")

    # If NO structural escape-hatch signal is present, the mechanism cannot exceed the
    # single-metric / single-condition baseline grammar -> baseline-equivalent by construction.
    if not sig:
        # attribute to the most specific covered family for reporting
        if _MIRROR_WORDS.search(text):
            fam, rule = "BC_SAME_METRIC_MIRROR", "R1_SINGLE_METRIC_MIRROR"
        elif re.search(r"\brecent\b.*\blong", text, re.I) or re.search(r"\bform\b", text, re.I):
            fam, rule = "BC_RECENT_VS_LONGRUN", "R4_RECENT_VS_LONGRUN"
        elif re.search(r"\bsimilar opponent", text, re.I):
            fam, rule = "BC_SIMILAR_OPPONENT_COHORT", "R7_SIMILARITY_COHORT"
        elif re.search(r"\b(league|competition|environment) baseline\b", text, re.I):
            fam, rule = "BC_ENVIRONMENT_BASELINE", "R5_ENVIRONMENT_BASELINE"
        elif re.search(r"\b(home|away|venue)\b", text, re.I) and len(_profile_axes_referenced(text)) == 0:
            fam, rule = "BC_SIMPLE_VENUE_CONTRAST", "R3_SIMPLE_VENUE_CONTRAST"
        elif len(_profile_axes_referenced(text)) >= 1:
            fam, rule = "BC_UNIVARIATE_PROFILE_SPLIT", "R2_UNIVARIATE_PROFILE_SPLIT"
        else:
            fam, rule = "BC_SINGLE_DIM_PROFILE_ALREADY_EXPRESSIBLE", "R2_UNIVARIATE_PROFILE_SPLIT"
        return EquivalenceVerdict(
            True, rule, fam, dm, sig,
            "No structural signal beyond single-metric/single-condition grammar.")

    # R6 covered two-dim interaction: venue x profile OR competition x profile, single metric.
    # This is covered EVEN THOUGH it is arity-2, because the grammar already expresses it.
    if (len(dm) <= 1
            and "US_MULTI_METRIC_INTERACTION" not in sig
            and "US_TWO_DIM_OPP_PROFILE_INTERSECTION" not in sig
            and "US_THRESHOLD_NONLINEARITY" not in sig
            and "US_HALF_STATE_OR_GAME_STATE" not in sig
            and "US_SEQUENCING_REGIME" not in sig):
        # only escape-hatch signals were cross-metric asymmetry with <2 metrics: incoherent
        return EquivalenceVerdict(
            True, "R6_COVERED_2D_INTERACTION", "BC_COVERED_TWO_DIM_INTERACTION",
            dm, sig, "Single metric with only covered venue/competition x profile conditioning.")

    # Otherwise: at least one genuine escape-hatch structure present -> NOT baseline-equivalent.
    return EquivalenceVerdict(
        False, "NONE", "NONE", dm, sig,
        f"Structural signals beyond baseline grammar: {sig}")


def is_baseline_equivalent(m: Mechanism) -> bool:
    return classify(m).is_baseline_equivalent


def version_stamp() -> Dict[str, object]:
    return {
        "baseline_equivalence_version": BASELINE_EQUIVALENCE_VERSION,
        "baseline_coverage_version": BASELINE_COVERAGE_VERSION,
        "rules": ["R1_SINGLE_METRIC_MIRROR", "R2_UNIVARIATE_PROFILE_SPLIT",
                  "R3_SIMPLE_VENUE_CONTRAST", "R4_RECENT_VS_LONGRUN",
                  "R5_ENVIRONMENT_BASELINE", "R6_COVERED_2D_INTERACTION",
                  "R7_SIMILARITY_COHORT", "R8_SELECTION_ONLY"],
        "conservative_default": "baseline_equivalent",
        "reads_outcomes": False,
        "outcome_aware": False,
    }

"""Frozen protocol constants and support rules for the direct-hypothesis measurement pilot.

Every numeric parameter used anywhere in the measurement apparatus is defined HERE, with its
rationale, before any historical effect is computed. None comes from the LLM: the frozen
hypotheses contain no numbers, and any number implied by their prose is ignored.
"""
from __future__ import annotations

from typing import Dict, Tuple

PROTOCOL_VERSION = "direct_hypothesis_measurement_v1"

#: name -> (value, rationale)
PROTOCOL_CONSTANTS: Dict[str, Tuple[float, str]] = {
    "PROFILE_WINDOW_MATCHES": (10, "Last 10 venue-matched prior matches: the packet's own RECENT_10 "
                               "horizon, and a length that does not depend on how far back the "
                               "corpus happens to start (ALL_PRIOR does)."),
    "MIN_PROFILE_MATCHES_PER_DIM": (5, "At least half the profile window must be non-null for a "
                                    "dimension; a mean of fewer than 5 matches is dominated by one "
                                    "or two games."),
    "MIN_PROFILE_DIMENSION_COVERAGE": (1.0, "All profile dimensions required; a distance over a "
                                       "subset of dimensions is a different profile."),
    "MIN_REFERENCE_OBS": (200, "Robust median/MAD of a competition distribution needs about 100 "
                          "matches (200 team-match values) before it is stable."),
    "MAD_TO_SD": (1.4826, "Consistency constant making MAD estimate the SD under normality."),
    "IQR_TO_SD": (1.349, "Fallback when MAD is 0: IQR/1.349 estimates the SD under normality."),
    "NEIGHBOR_FRACTION": (1 / 3, "Nearest tercile of eligible subject matches; the same "
                          "domain-neutral tercile grid used elsewhere in the engine, not tuned."),
    "MIN_SIMILAR_MATCHES": (10, "Neighbour and comparison groups each need >= 10 matches so that "
                            "no one or two matches dominate a group mean."),
    "MIN_SUBJECT_MATCHES": (30, "Tercile split of 30 gives >= 10 neighbours and >= 20 others; "
                            "also the minimum for a rank correlation with SE near 0.19."),
    "MIN_OBS_PER_PARAMETER": (10, "Regression support rule: >= 10 observations per estimated "
                              "parameter (standard events-per-variable guidance)."),
    "MIN_METRIC_COVERAGE": (0.8, "A required metric must be non-null in >= 80% of the candidate "
                            "subject matches, else the metric is unsupported (fail closed)."),
    "STRENGTH_WINDOW_MATCHES": (10, "Opponent strength = mean goal difference over its last 10 "
                                "same-competition matches."),
    "MIN_STRENGTH_MATCHES": (5, "Strength needs >= 5 of those matches, else it is missing (never "
                             "a gate on eligibility)."),
    "RECENT_BLOCK_MATCHES": (5, "DP5 recent block = last 5 away matches (the packet's RECENT_5 "
                             "horizon applied away-only)."),
    "MIN_LONG_RUN_MATCHES": (20, "DP5 long-run reference needs >= 20 away matches before the "
                             "recent block (four disjoint blocks)."),
    "SHRINKAGE_KAPPA": (5, "Credibility weight n/(n+kappa) with kappa = the recent window length: "
                        "a full recent window gets equal weight with its reference, the "
                        "minimal-assumption choice."),
    "N_RESAMPLES": (10000, "Permutation resamples for every primary null."),
    "RNG_SEED": (0, "numpy.random.default_rng(0), fresh per measurement."),
    "BH_Q": (0.10, "Benjamini-Hochberg across the inferential primaries (exploratory pilot)."),
    "DISTANCE_ROUND_DECIMALS": (12, "Distances are rounded to 12 decimals before ordering so "
                                "floating-point noise cannot reorder ties; ties then break by "
                                "(kickoff, match_id)."),
}


def c(name: str) -> Dict[str, object]:
    """A numeric parameter as it appears in a spec: always traceable to a named constant."""
    return {"constant": name, "value": PROTOCOL_CONSTANTS[name][0]}


def value(name: str):
    return PROTOCOL_CONSTANTS[name][0]


class Status:
    OK = "OK"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
    NO_QUERY_PROFILE = "NO_QUERY_PROFILE"


def neighbor_count(n_eligible: int) -> int:
    import math
    return max(int(value("MIN_SIMILAR_MATCHES")),
               int(math.ceil(n_eligible * value("NEIGHBOR_FRACTION"))))


def group_support(n_eligible: int) -> Tuple[str, str]:
    """Support for a neighbour-vs-rest comparison."""
    if n_eligible < value("MIN_SUBJECT_MATCHES"):
        return Status.INSUFFICIENT_SUPPORT, (
            f"{n_eligible} eligible subject matches < MIN_SUBJECT_MATCHES")
    k = neighbor_count(n_eligible)
    if n_eligible - k < value("MIN_SIMILAR_MATCHES"):
        return Status.INSUFFICIENT_SUPPORT, "comparison group below MIN_SIMILAR_MATCHES"
    return Status.OK, ""


def regression_support(n_eligible: int, n_parameters: int) -> Tuple[str, str]:
    need = int(value("MIN_OBS_PER_PARAMETER")) * n_parameters
    if n_eligible < need:
        return Status.INSUFFICIENT_SUPPORT, (
            f"{n_eligible} observations < MIN_OBS_PER_PARAMETER x {n_parameters} = {need}")
    return Status.OK, ""


def metric_coverage(n_nonnull: int, n_candidates: int) -> Tuple[str, str]:
    if n_candidates == 0 or n_nonnull / n_candidates < value("MIN_METRIC_COVERAGE"):
        return Status.UNSUPPORTED_METRIC, (
            f"non-null {n_nonnull}/{n_candidates} below MIN_METRIC_COVERAGE")
    return Status.OK, ""

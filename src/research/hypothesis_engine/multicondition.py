"""Meaningful multi-condition classifier (`meaningful_multicondition_v1`). FROZEN.

WHY `len(conditions) >= 2` IS NOT A DEFINITION
----------------------------------------------
A counted condition is not a measured cohort. All of the following have two conditions and
none of them is a second research dimension:

    venue=HOME + competition=ANY          -> ANY restricts nothing; one real leg
    venue=HOME + venue=HOME               -> a duplicate; one real leg
    venue=HOME + venue=AWAY               -> contradictory; the cohort is empty
    venue=HOME + half_score_state=...     -> the second leg is withheld for this fixture
    profile(HIGH, corners_against) x2     -> same dimension, same axis; one real leg
    venue=HOME, comparison=VENUE_BASELINE -> cohort IS the baseline; nothing is compared

If "depth" were `len(conditions) >= 2`, every one of those would score as depth, and the
cheapest way to pass V3 would be to pad. So the classifier below is frozen BEFORE
inference and requires a hypothesis to survive six independent checks.

WHAT THIS DOES NOT DO
---------------------
It does not decide whether the interaction has a real effect. Whether the cohort actually
behaves differently is a downstream deterministic measurement, not a property of the
proposal. This module only answers: *is this a distinct, available, non-degenerate,
compilable two-dimensional measurement request?*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import availability, condition_contract, vocabulary

CLASSIFIER_VERSION = "meaningful_multicondition_v1"


# --------------------------------------------------------------------------------------
# Rejection reasons. Each is a distinct way a counted condition fails to be a real leg.
# --------------------------------------------------------------------------------------
FEWER_THAN_TWO_LEGS = "FEWER_THAN_TWO_DISTINCT_LEGS"
LEG_NOT_AVAILABLE = "LEG_DIMENSION_NOT_AVAILABLE_IN_PACKET"
LEG_AXIS_NOT_AVAILABLE = "LEG_AXIS_NOT_AVAILABLE_IN_PACKET"
DUPLICATE_LEG = "DUPLICATE_OR_ALIASED_LEG"
CONTRADICTORY_LEG = "CONTRADICTORY_LEGS_ON_ONE_DIMENSION"
DEGENERATE_VS_COMPARISON = "COHORT_IS_THE_COMPARISON_BASELINE"
DOES_NOT_COMPILE = "DOES_NOT_COMPILE_TO_A_DETERMINISTIC_QUERY"

#: Comparison -> the dimension whose restriction it already applies to the baseline.
#:
#: Conditioning on venue and then comparing against the subject's OWN VENUE baseline
#: measures a cohort against itself. The condition is a compiler no-op in research terms,
#: even though the compiler accepts it happily.
_BASELINE_ABSORBS_DIMENSION = {
    "SUBJECT_VENUE_BASELINE": "venue",
    "SUBJECT_COMPETITION_BASELINE": "competition",
}


@dataclass(frozen=True)
class Leg:
    """One genuinely restricting cohort dimension."""

    dimension: str
    value: str
    axis: Optional[str] = None

    @property
    def key(self) -> tuple:
        """Identity for distinctness. Two profile conditions on DIFFERENT axes are two
        research dimensions; on the SAME axis they are one."""
        return (self.dimension, self.axis)

    def to_dict(self) -> dict:
        d = {"dimension": self.dimension, "value": self.value}
        if self.axis:
            d["axis"] = self.axis
        return d


@dataclass
class Verdict:
    hypothesis_id: str
    meaningful: bool
    legs: tuple = ()
    interaction_family: tuple = ()
    reasons: list = field(default_factory=list)
    n_raw_conditions: int = 0
    n_restricting: int = 0

    def to_dict(self) -> dict:
        return {
            "classifier_version": CLASSIFIER_VERSION,
            "hypothesis_id": self.hypothesis_id,
            "meaningful_multi_condition": self.meaningful,
            "legs": [l.to_dict() for l in self.legs],
            "interaction_family": list(self.interaction_family),
            "reasons": list(self.reasons),
            "n_raw_conditions": self.n_raw_conditions,
            "n_restricting_legs": self.n_restricting,
        }


def restricting_legs(hypothesis: dict) -> tuple[list[Leg], list[str]]:
    """Reduce a hypothesis's conditions to the legs that actually restrict the cohort.

    Drops, with a reason each:
      * `ANY` values -- they place no restriction, so they are padding, not depth;
      * `period=ALL` -- the no-op period;
      * exact duplicates after canonicalization.
    """
    legs: list[Leg] = []
    reasons: list[str] = []
    seen_exact: set[tuple] = set()

    for raw in hypothesis.get("conditions") or []:
        if not isinstance(raw, dict):
            continue
        got = condition_contract.canonicalize_condition(raw)
        if isinstance(got, condition_contract.ContractFailure):
            reasons.append(f"{DUPLICATE_LEG}: condition did not canonicalize "
                           f"({got.reason})")
            continue
        if condition_contract.fold(got.value) == "ANY":
            continue
        if got.dimension == "period" and got.value == "ALL":
            continue
        exact = (got.dimension, got.value, got.axis)
        if exact in seen_exact:
            reasons.append(f"{DUPLICATE_LEG}: {exact}")
            continue
        seen_exact.add(exact)
        legs.append(Leg(got.dimension, got.value, got.axis))

    return legs, reasons


def classify(
    hypothesis: dict,
    ontology: availability.ResearchOntology,
    *,
    compile_results: Optional[Sequence[dict]] = None,
) -> Verdict:
    """Frozen six-check classification of ONE hypothesis.

    `compile_results` is the list of `CompileResult.to_dict()` for this hypothesis. ALL
    plans must be `ok` -- a hypothesis naming three metrics of which one fails on
    granularity is not a clean deterministic query, and this matches the numerator of
    `compile_set`'s `n_fully_compilable` so depth and gate B never disagree.
    """
    hid = hypothesis.get("hypothesis_id", "<anon>")
    raw_conditions = hypothesis.get("conditions") or []
    legs, reasons = restricting_legs(hypothesis)

    # --- check 1: at least two DISTINCT legs (dimension, axis) -------------------------
    by_key: dict[tuple, list[Leg]] = {}
    for leg in legs:
        by_key.setdefault(leg.key, []).append(leg)

    for key, group in sorted(by_key.items()):
        if len(group) > 1:
            # Two different values on one dimension+axis: the cohort is their intersection,
            # which for a closed enum is empty. Never a measurable interaction.
            reasons.append(f"{CONTRADICTORY_LEG}: {key} given values "
                           f"{sorted(l.value for l in group)}")

    distinct = [group[0] for _key, group in sorted(by_key.items()) if len(group) == 1]

    verdict = Verdict(hypothesis_id=hid, meaningful=False, legs=tuple(distinct),
                      interaction_family=tuple(sorted(l.dimension for l in distinct)),
                      reasons=reasons, n_raw_conditions=len(raw_conditions),
                      n_restricting=len(distinct))

    if len(distinct) < 2:
        verdict.reasons.append(
            f"{FEWER_THAN_TWO_LEGS}: {len(distinct)} distinct restricting leg(s) from "
            f"{len(raw_conditions)} written condition(s)")
        return verdict

    # --- check 2: every leg's DIMENSION is genuinely available for this fixture --------
    # NOTE: this reads the DIMENSION's availability, never the comparison's. A dimension
    # can be AVAILABLE while a comparison built on it is COMPILE_AVAILABLE_NO_EVIDENCE.
    for leg in distinct:
        d = ontology.dimensions.get(leg.dimension)
        if d is None or not d.expectable:
            verdict.reasons.append(
                f"{LEG_NOT_AVAILABLE}: {leg.dimension!r} is "
                f"{d.status if d else 'UNKNOWN'} for this fixture")

    # --- check 3: every axis-bearing leg names a resolvable axis -----------------------
    for leg in distinct:
        if leg.axis is None:
            continue
        d = ontology.dimensions.get(leg.dimension)
        if d is None or leg.axis not in d.available_axes:
            verdict.reasons.append(
                f"{LEG_AXIS_NOT_AVAILABLE}: {leg.axis!r} on {leg.dimension!r}")

    # --- check 4: the cohort is not simply the comparison baseline ---------------------
    absorbed = _BASELINE_ABSORBS_DIMENSION.get(hypothesis.get("comparison"))
    if absorbed is not None:
        others = [l for l in distinct if l.dimension != absorbed]
        if len(others) < 2 and any(l.dimension == absorbed for l in distinct):
            # The absorbed leg contributes nothing beyond what the baseline already
            # applies, so what remains is fewer than two real dimensions.
            verdict.reasons.append(
                f"{DEGENERATE_VS_COMPARISON}: comparison "
                f"{hypothesis.get('comparison')!r} already restricts {absorbed!r}, "
                f"leaving {len(others)} independent leg(s)")

    # --- check 5 + 6: it must compile, fully, to a deterministic query -----------------
    if compile_results is not None:
        if not compile_results:
            verdict.reasons.append(f"{DOES_NOT_COMPILE}: no plans produced")
        elif not all(r.get("ok") for r in compile_results):
            failed = sorted({r.get("failure") for r in compile_results
                             if not r.get("ok")})
            verdict.reasons.append(f"{DOES_NOT_COMPILE}: {failed}")

    verdict.meaningful = not verdict.reasons
    return verdict


def classify_set(
    accepted_hypotheses: Sequence[dict],
    ontology: availability.ResearchOntology,
    *,
    compiled: Optional[dict] = None,
) -> dict:
    """Classify every accepted hypothesis and summarise.

    `compiled` is `query_plan.compile_set(...)["results"]`: hypothesis_id -> list of plan
    result dicts.
    """
    verdicts = []
    for h in accepted_hypotheses:
        hid = h.get("hypothesis_id", "<anon>")
        cr = (compiled or {}).get(hid) if compiled is not None else None
        verdicts.append(classify(h, ontology, compile_results=cr))

    meaningful = [v for v in verdicts if v.meaningful]
    families = sorted({tuple(v.interaction_family) for v in meaningful})

    dist: dict[int, int] = {}
    for v in verdicts:
        dist[v.n_restricting] = dist.get(v.n_restricting, 0) + 1

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "fixture_id": ontology.fixture_id,
        "n_hypotheses": len(verdicts),
        "n_meaningful_multi_condition": len(meaningful),
        "meaningful_multi_condition_rate": (round(len(meaningful) / len(verdicts), 4)
                                            if verdicts else None),
        "restricting_leg_count_distribution": {str(k): dist[k] for k in sorted(dist)},
        "interaction_families": [list(f) for f in families],
        "n_distinct_interaction_families": len(families),
        "verdicts": [v.to_dict() for v in verdicts],
    }


def version_stamp() -> dict:
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "rejection_reasons": [
            FEWER_THAN_TWO_LEGS, LEG_NOT_AVAILABLE, LEG_AXIS_NOT_AVAILABLE,
            DUPLICATE_LEG, CONTRADICTORY_LEG, DEGENERATE_VS_COMPARISON, DOES_NOT_COMPILE],
        "baseline_absorbs_dimension": dict(_BASELINE_ABSORBS_DIMENSION),
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "availability_version": availability.AVAILABILITY_VERSION,
        "condition_contract_version": condition_contract.CONTRACT_VERSION,
    }

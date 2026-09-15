"""QUALIFIED_RESEARCH_HYPOTHESIS (`v6_qualified_v1`). §10.

    "Arm B should not pass merely by writing more. Define the primary unit at hypothesis
     level. Do not use raw hypothesis count alone."

The eight conjuncts of §10, each mapped to the ONE scorecard key that decides it. Nothing
here recomputes a gate; a conjunct that disagreed with the gate that produced it would be a
second opinion, and `test_qualified_hypothesis_requires_full_chain` asserts that flipping
any single conjunct to False removes the qualification.

    §10 requirement                          scorecard key
    ---------------------------------------  -------------------------
    1. schema-valid                          schema_valid
    2. grounded in valid evidence            evidence_grounded
    3. availability-compliant                availability_valid
    4. numerical-authority compliant         numeric_contract_valid AND firewall_valid
    5. compiler-valid                        compiler_valid
    6. non-degenerate                        nondegenerate AND comparator_valid
    7. non-redundant                         nonredundant
    8. contextually justified in that arm    contextually_supported

Two conjuncts draw on two keys each, and both pairings are substantive rather than
convenient. Numerical authority is claimed either through a FIELD (§5, the numeric
contract) or through PROSE (§4, the firewall); a hypothesis that claims it either way has
claimed it. Degeneracy likewise comes in two shapes: a cohort that restricts nothing
(`ANY`, contradiction) and a comparison that measures a set against itself (§15's baseline
absorption). Splitting them across two gates is how each gets its own failure class in §8;
merging them here is how §10's single conjunct stays a single conjunct.

ABSTENTION IS NOT A QUALIFIED HYPOTHESIS, AND IS NOT A FAILURE EITHER (§17)
---------------------------------------------------------------------------
An evidence-backed `INSUFFICIENT_EVIDENCE` is CORRECT behaviour and §17 forbids punishing
it. It is also not a research question the engine can go and measure, so it cannot be a
QUALIFIED_RESEARCH_HYPOTHESIS.

The resolution is in the DENOMINATOR, and it is the reason the rate is defined the way it
is: `qualified_rate = qualified / (recoverable NON-ABSTAINING hypotheses)`. An abstention
enters neither side. So abstaining is exactly rate-neutral -- a model that abstains six
times and qualifies the other six scores the same 1.0 as one that qualifies twelve -- while
`n_abstentions` and `n_abstentions_with_refs` are reported on their own axis. Any
denominator that counted abstentions would make discipline look like failure, which §17
names directly. An arm with less evidence may rationally abstain more often, and under this
definition it pays nothing for doing so.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_oos import v6_classes as K

QUALIFIED_VERSION = "v6_qualified_v1"

#: §10 conjunct -> the scorecard keys that must ALL be True. Frozen and machine-readable so
#: the preregistration carries the definition rather than a description of it.
CONJUNCTS = (
    ("schema_valid", ("schema_valid",)),
    ("grounded_in_valid_evidence", ("evidence_grounded",)),
    ("availability_compliant", ("availability_valid",)),
    ("numerical_authority_compliant", ("numeric_contract_valid", "firewall_valid")),
    ("compiler_valid", ("compiler_valid",)),
    ("nondegenerate", ("nondegenerate", "comparator_valid")),
    ("nonredundant", ("nonredundant",)),
    ("contextually_supported", ("contextually_supported",)),
)

CONJUNCT_NAMES = tuple(name for name, _ in CONJUNCTS)


def conjunct_results(scorecard: dict) -> dict:
    """Each §10 conjunct as True / False / None.

    `None` propagates: a conjunct whose key was never measured is UNKNOWN, never a pass.
    """
    out = {}
    for name, keys in CONJUNCTS:
        vals = [scorecard.get(k) for k in keys]
        if any(v is False for v in vals):
            out[name] = False
        elif any(v is None for v in vals):
            out[name] = None
        else:
            out[name] = True
    return out


def is_qualified(adj) -> bool:
    """Does this adjudicated hypothesis meet every §10 conjunct AND assert SUFFICIENT?"""
    if adj.abstaining:
        return False
    if adj.outcome_class not in K.HYPOTHESIS_OK_CLASSES:
        return False
    return all(v is True for v in conjunct_results(adj.scorecard).values())


def annotate(adj) -> dict:
    """Write `qualified` and the conjunct breakdown onto the scorecard, in place.

    Returns the conjunct dict for the response scorecard. Called exactly once per
    hypothesis, by `v6_scorecard`, so there is one place qualification is decided.
    """
    conj = conjunct_results(adj.scorecard)
    q = is_qualified(adj)
    adj.scorecard["qualified"] = q
    adj.scorecard["qualified_conjuncts"] = conj
    return conj


def evidence_specific(adj) -> bool:
    """A qualified hypothesis that made some USE of the evidence surface (§21 secondary).

    Excludes the unconditioned self-comparison -- the one shape a base-arm packet can
    express (see `v6_baseline`). This is the SECONDARY endpoint on which the base arm is
    expected, before any data exists, to score at or near zero BY CONSTRUCTION. Stating
    that expectation in advance is the whole reason the metric is secondary and not the
    gate: a large Arm B number here is a fact about the packets, not a discovery about the
    model.
    """
    if not adj.scorecard.get("qualified"):
        return False
    return not bool(adj.comparator.get("unconditioned_self_comparison"))


def version_stamp() -> dict:
    return {"qualified_version": QUALIFIED_VERSION,
            "conjuncts": {name: list(keys) for name, keys in CONJUNCTS},
            "abstention_is_qualified": False,
            "denominator": "recoverable NON-ABSTAINING hypotheses",
            "denominator_rationale":
                "§17 -- an abstention enters neither numerator nor denominator, so "
                "disciplined abstention is exactly rate-neutral and is never punished"}

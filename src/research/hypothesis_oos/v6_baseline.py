"""Comparator validity and BASELINE ABSORPTION (`v6_baseline_v1`). §15.

    "Prevent tautologies such as: condition venue=HOME + compare against identical
     HOME-only baseline unless the comparison has a distinct estimand."

A conditional mean with no baseline is not a research result -- `vocabulary.COMPARISONS`
already makes a comparator mandatory. What nothing checked before V6 is whether the
comparator and the cohort name the SAME SET. When they do, the engine would dutifully
measure a difference that is zero by construction, and a hypothesis that cannot fail is not
a hypothesis.

ABSORPTION IS ABOUT A RESTRICTION THE COMPARATOR THEN REMOVES
-------------------------------------------------------------
    cohort      = the subject's prior matches, restricted by `window` and `conditions`
    baseline    = the set `comparison` names

Absorbed iff the restriction the hypothesis declares is exactly the restriction the
baseline already carries, so both sides resolve to one set:

    historical_venue_conditioning=HOME + SUBJECT_VENUE_BASELINE, subject at home
    window=ALL_PRIOR                  + SUBJECT_RECENT_VS_LONG_BASELINE
    competition=SAME                  + SUBJECT_COMPETITION_BASELINE

NOT absorbed, and the distinction matters:

    window=W5 + SUBJECT_RECENT_VS_LONG_BASELINE      that IS the comparison's purpose
    venue=AWAY + SUBJECT_VENUE_BASELINE (home side)  away cohort vs home baseline is a
                                                     real contrast with a real estimand

THE UNCONDITIONED SELF-COMPARISON, AND WHY IT IS NOT CLASSED AS ABSORPTION
--------------------------------------------------------------------------
    window=ALL_PRIOR + no conditions + SUBJECT_OVERALL_BASELINE

Both sides are the subject's entire prior record. Read literally this is the purest
tautology of the lot, and the temptation is to reject it.

It must not be rejected, and the reason is an apparatus one rather than a charitable one.
The base arm's packet exposes exactly one window (`ALL_PRIOR`), zero conditionable terms
and exactly one comparison (`SUBJECT_OVERALL_BASELINE`) -- `packet_capability_summary`
returns that, and it is a property of the arm definition §2 preserves. So the combination
above is the ONLY admissible shape a base-arm hypothesis can take. Rejecting it would set
the base arm's qualified count to zero BY CONSTRUCTION, and the A/B difference would then
measure which packet we built rather than what the model did with it -- an
apparatus-confounded result, which §39 ranks as worse than a clean FAIL and §37 bars from
freeze.

So it is classified, named, counted and reported on its own axis:

    `unconditioned_self_comparison = True`

It does NOT disqualify (§10's non-degenerate conjunct is not failed by it), and it IS
excluded from the preregistered SECONDARY endpoint `evidence_specific_qualified_count`
(§21), where a hypothesis must have made some use of the evidence surface to count. The
base arm is expected to score at or near zero on that secondary, and saying so here, before
spend, is what stops a later reader over-reading a large Arm B number as a discovery.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_engine import vocabulary
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O

BASELINE_VERSION = "v6_baseline_v1"

#: Absorption verdicts.
NOT_ABSORBED = "NOT_ABSORBED"
ABSORBED_VENUE = "ABSORBED_VENUE"
ABSORBED_RECENT_VS_LONG = "ABSORBED_RECENT_VS_LONG"
ABSORBED_COMPETITION = "ABSORBED_COMPETITION"

ABSORPTION_CLASSES = (NOT_ABSORBED, ABSORBED_VENUE, ABSORBED_RECENT_VS_LONG,
                      ABSORBED_COMPETITION)

#: Which venue `SUBJECT_VENUE_BASELINE` resolves to, per subject. The baseline is "the
#: subject's own rate AT THE SAME VENUE", and the venue of the upcoming fixture is fixed by
#: which side the subject is -- a fact every packet states in TARGET_FIXTURE_CONTEXT and
#: `target_fixture_venue_context` declares exposed in BOTH arms.
_VENUE_OF_SUBJECT = {"HOME_TEAM": "HOME", "AWAY_TEAM": "AWAY"}


def _conditions(h) -> list:
    c = h.get("conditions")
    return [x for x in c if isinstance(x, dict)] if isinstance(c, list) else []


def _cond_value(h, dimension: str):
    for c in _conditions(h):
        if c.get("dimension") == dimension:
            return c.get("value")
    return None


def is_unconditioned_self_comparison(h) -> bool:
    """The one shape the base arm can express. Named, counted, never a rejection.

    `side` and `target_metrics` do not enter: they select WHICH quantity is measured, not
    which matches the cohort contains, so they cannot make a cohort differ from a baseline
    drawn over the same matches.
    """
    return (not _conditions(h)
            and h.get("window") == "ALL_PRIOR"
            and h.get("comparison") == "SUBJECT_OVERALL_BASELINE")


def absorption(h) -> dict:
    """Does the comparator remove exactly the restriction the hypothesis declared?

    Pure function of the hypothesis, in MODEL language. No packet is consulted: whether the
    packet can SUPPORT the comparison is `v5a2_admissibility`'s question and produces a
    different failure class. This one is about whether the comparison means anything.
    """
    comp = h.get("comparison")
    subject = vocabulary.canonical_subject(str(h.get("subject") or "")) or h.get("subject")
    window = h.get("window")

    if comp == "SUBJECT_VENUE_BASELINE":
        v = _cond_value(h, O.HISTORICAL_VENUE_CONDITIONING)
        baseline_venue = _VENUE_OF_SUBJECT.get(subject)
        if v is not None and baseline_venue is not None and v == baseline_venue:
            return {"absorbed": True, "class": ABSORBED_VENUE,
                    "detail": f"the cohort is restricted to {v!r} matches and "
                              f"SUBJECT_VENUE_BASELINE is the subject's own rate at the "
                              f"venue of this fixture, which for {subject} is "
                              f"{baseline_venue!r}. Both sides are the same set of "
                              f"matches, so the comparison has no estimand. Compare a "
                              f"venue-restricted cohort against SUBJECT_OVERALL_BASELINE, "
                              f"or drop the condition."}

    if comp == "SUBJECT_RECENT_VS_LONG_BASELINE":
        if window == "ALL_PRIOR":
            return {"absorbed": True, "class": ABSORBED_RECENT_VS_LONG,
                    "detail": "SUBJECT_RECENT_VS_LONG_BASELINE compares a SHORT window "
                              "against the long run, and the cohort window is ALL_PRIOR. "
                              "Both sides are the long run. Set window to W5 or W10, or "
                              "choose a different comparison."}

    if comp == "SUBJECT_COMPETITION_BASELINE":
        if _cond_value(h, "competition") == "SAME":
            return {"absorbed": True, "class": ABSORBED_COMPETITION,
                    "detail": "the cohort is already restricted to this fixture's "
                              "competition and SUBJECT_COMPETITION_BASELINE is the "
                              "subject's rate in that same competition. Both sides are "
                              "the same set."}

    return {"absorbed": False, "class": NOT_ABSORBED, "detail": ""}


def comparator_reasons(h, packet=None) -> list:
    """Why this hypothesis's comparator is invalid. Empty list = valid.

    Packet SUPPORT for a comparison is deliberately NOT re-checked here --
    `v5a2_admissibility.packet_admissibility_reasons` owns it and produces
    MODEL_AVAILABILITY_VIOLATION, an earlier gate with a different meaning. Duplicating it
    would double-count one mistake under two classes, which §8 exists to prevent.
    """
    reasons: list = []
    comp = h.get("comparison")
    if comp not in vocabulary.COMPARISONS:
        reasons.append(f"comparison {comp!r} is not one of {list(vocabulary.COMPARISONS)}")
        return reasons
    ab = absorption(h)
    if ab["absorbed"]:
        reasons.append(f"BASELINE ABSORPTION ({ab['class']}): {ab['detail']}")
    return reasons


def classify(h, packet=None) -> dict:
    """The full comparator scorecard for one hypothesis."""
    ab = absorption(h)
    reasons = comparator_reasons(h, packet)
    return {
        "comparison": h.get("comparison"),
        "absorbed": ab["absorbed"],
        "absorption_class": ab["class"],
        "unconditioned_self_comparison": is_unconditioned_self_comparison(h),
        "comparator_valid": not reasons,
        "reasons": reasons,
    }


def arm_comparator_surface(packet) -> dict:
    """What comparisons this packet admits, and whether a non-absorbed one is reachable.

    Written into the packet audit so the §15 decision above is checkable rather than
    asserted: a reader can see for themselves that the base arm admits exactly one
    comparison and that it is reachable only as an unconditioned self-comparison.
    """
    summary = ADM.packet_capability_summary(packet)
    comps = summary["comparisons"]
    conditionable = summary["conditionable_terms"]
    windows = summary["windows"]
    non_self = []
    for c in comps:
        if c == "SUBJECT_OVERALL_BASELINE":
            if conditionable or any(w != "ALL_PRIOR" for w in windows):
                non_self.append(c)
        elif c == "SUBJECT_RECENT_VS_LONG_BASELINE":
            if any(w in ("W5", "W10") for w in windows):
                non_self.append(c)
        elif c == "SUBJECT_VENUE_BASELINE":
            if O.HISTORICAL_VENUE_CONDITIONING in conditionable:
                non_self.append(c)
    return {"comparisons": comps, "conditionable_terms": conditionable,
            "windows": windows,
            "non_self_comparison_reachable": sorted(non_self),
            "only_unconditioned_self_comparison_is_reachable": not non_self}


def version_stamp() -> dict:
    return {"baseline_version": BASELINE_VERSION,
            "absorption_classes": list(ABSORPTION_CLASSES),
            "unconditioned_self_comparison_disqualifies": False,
            "unconditioned_self_comparison_counts_toward_evidence_specific": False}

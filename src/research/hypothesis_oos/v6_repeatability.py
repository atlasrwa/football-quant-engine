"""Normalized intent and same-input repeat similarity (`v6_repeatability_v1`). §9, §22.

    "Do not interpret temperature=0 as determinism."

THE OBSERVATION THIS MODULE EXISTS TO MEASURE PROPERLY
-------------------------------------------------------
V5A.2 issued four BYTE-IDENTICAL requests at `temperature = 0.0` -- the same
`serialized_request_sha256` on all four -- and the primary metric came back

    6, 0, 7, 0

with output token counts 3801 / 3892 / 4390 / 4164. One repeat group in one arm on one
fixture: below the preregistered minimum of three, so V5A.2 recorded it and correctly
refused to rely on it. The pooled SD was 3.27 on a 0-12 count.

A generator with that much within-input spread can produce an Arm B minus Arm A difference
of several hypotheses from nothing at all. So §22's requirement is not a formality: the
claim V6 can make is not "B > A" but "B - A exceeds what this generator does to itself when
nothing changes", and that requires the self-noise floor to be measured on the SAME
statistic, at the SAME scale, from MULTIPLE fixtures in BOTH arms (§9).

WHAT IS COMPARED WITHIN A REPEAT GROUP (§9)
--------------------------------------------
    accepted / qualified hypothesis count     `v6_selfnoise` (the numeric floor)
    normalized hypothesis intent              `normalized_intent`  -> Jaccard
    evidence references                       `reference_set`      -> Jaccard
    dimensions used                           `dimension_set`      -> Jaccard
    comparison types                          `comparison_set`     -> Jaccard
    compiler plans                            `plan_set`           -> Jaccard

All six are deterministic functions of the response. None of them reads prose: two
identically-specified measurements are the same measurement however differently they are
worded, and a similarity metric that moved when the wording moved would be measuring
style.

`priority` is excluded (§23), as it is from `validator_v5._intent_key` and from every
scorecard metric.

EVERY SET IS SERIALIZED SORTED. §30 requires byte-identical artifacts under
PYTHONHASHSEED 1/2/3/12345, and a Python set has no stable iteration order.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_engine import vocabulary

REPEATABILITY_VERSION = "v6_repeatability_v1"


def normalized_intent(h: dict) -> str:
    """The measurable intent of one hypothesis, as one canonical string.

    Identical in content to `validator_v5._intent_key` and asserted so by
    `test_repeatability_normalization_matches_redundancy_key`: the relation that decides
    "is this the same measurement as a sibling" and the one that decides "is this the same
    measurement as in the previous repeat" must not be two different opinions.
    """
    subject = vocabulary.canonical_subject(str(h.get("subject") or "")) or h.get("subject")
    metrics = "+".join(sorted(str(m) for m in (h.get("target_metrics") or [])))
    conds = "&".join(sorted(
        f"{c.get('dimension')}={c.get('value')}@{c.get('axis')}"
        for c in (h.get("conditions") or []) if isinstance(c, dict)))
    return (f"{subject}|{metrics}|{h.get('side')}|{h.get('window')}|"
            f"{h.get('comparison')}|{conds}|{h.get('sufficiency')}")


def normalized_intents(res) -> list:
    """Sorted normalized intents of every RECOVERED hypothesis in one response.

    Includes rejected hypotheses on purpose. Self-noise is a property of what the GENERATOR
    produced, not of what our gates let through; measuring it on accepted hypotheses only
    would confound generator variability with gate behaviour.
    """
    return sorted(normalized_intent(a.hypothesis or {}) for a in res.hypotheses)


def reference_set(res) -> list:
    out = set()
    for a in res.hypotheses:
        for r in (a.hypothesis or {}).get("evidence_refs") or []:
            if isinstance(r, str):
                out.add(r)
    return sorted(out)


def dimension_set(res) -> list:
    out = set()
    for a in res.hypotheses:
        h = a.hypothesis or {}
        for c in h.get("conditions") or []:
            if isinstance(c, dict):
                out.add(f"{c.get('dimension')}@{c.get('axis')}")
        if h.get("window") in ("W5", "W10"):
            out.add(f"window={h.get('window')}")
    return sorted(out)


def comparison_set(res) -> list:
    return sorted({str((a.hypothesis or {}).get("comparison")) for a in res.hypotheses})


def plan_set(res) -> list:
    """The compiler's own view: one entry per (metric, side, window, conditions) plan.

    Built from the TRANSLATED hypothesis, so it speaks the engine's language and two
    responses that specify the same measurement in different model-language spellings
    produce the same plan entry.
    """
    out = set()
    for a in res.hypotheses:
        if a.internal is None:
            continue
        conds = "&".join(sorted(
            f"{c.get('dimension')}={c.get('value')}@{c.get('axis')}"
            for c in (a.internal.get("conditions") or []) if isinstance(c, dict)))
        for m in a.internal.get("target_metrics") or []:
            out.add(f"{a.internal.get('subject')}|{m}|{a.internal.get('side')}|"
                    f"{a.internal.get('window')}|{a.internal.get('comparison')}|{conds}")
    return sorted(out)


def jaccard(a, b) -> float:
    """Deterministic set similarity. Two EMPTY sets are 1.0 -- identical responses, and the
    alternative (0.0) would report two identical empty outputs as maximally dissimilar."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


#: The five set-valued axes §9 names, each as (label, extractor). Frozen and ordered, so
#: the repeatability report is byte-stable.
SIMILARITY_AXES = (
    ("normalized_intent", normalized_intents),
    ("evidence_references", reference_set),
    ("dimensions_used", dimension_set),
    ("comparison_types", comparison_set),
    ("compiler_plans", plan_set),
)


def pairwise_similarity(responses: list) -> dict:
    """Mean pairwise Jaccard on every §9 axis, across the repeats of ONE group.

    Mean over all unordered pairs rather than "each against the first": the first response
    is not a reference, and treating it as one would make the number depend on call order
    inside a group.
    """
    n = len(responses)
    out = {}
    for label, fn in SIMILARITY_AXES:
        sets = [fn(r) for r in responses]
        pairs = [jaccard(sets[i], sets[j])
                 for i in range(n) for j in range(i + 1, n)]
        out[label] = {
            "n_repeats": n,
            "n_pairs": len(pairs),
            "mean_jaccard": round(sum(pairs) / len(pairs), 6) if pairs else None,
            "min_jaccard": round(min(pairs), 6) if pairs else None,
            "set_sizes": [len(s) for s in sets],
        }
    return out


def group_report(fixture_id: str, arm: str, responses: list, values: list) -> dict:
    """One repeat group: the numeric spread and all five similarity axes."""
    return {
        "fixture_id": fixture_id, "arm": arm,
        "n_repeats": len(responses),
        "primary_values": list(values),
        "similarity": pairwise_similarity(responses),
    }


def version_stamp() -> dict:
    return {"repeatability_version": REPEATABILITY_VERSION,
            "similarity_axes": [a for a, _ in SIMILARITY_AXES],
            "similarity_metric": "Jaccard over sorted deterministic sets",
            "includes_rejected_hypotheses": True,
            "priority_excluded": True,
            "reads_prose": False}

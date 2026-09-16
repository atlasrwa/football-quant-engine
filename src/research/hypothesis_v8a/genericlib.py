"""V8A outcome-blind generic hypothesis library (`v8a_genericlib_v1`). Brief sections 8/10/16.

STRUCTURE ONLY. Nothing here reads, stores or can expose V7/V7.1 survival, effects, quality
scores, p-values, candidate status, fold performance or confirmatory results. The library is
built from the frozen V7.1 structural grammar (`hypothesis_v71.controls` + `ontology`) and
the frozen capability contract, all of which are outcome-blind by construction.

WHY MEMBERSHIP IS A PREDICATE, NOT A SAMPLE
-------------------------------------------
The brief describes "2,000 generic hypotheses". V7.1's uniform pool is exactly that: 2,000
SHA-256-stream draws. Deciding EXACT_DUPLICATE / STRUCTURAL_EQUIVALENT against a 2,000-draw
sample would make the headline novelty rate a function of sampling luck -- a structurally
ordinary candidate the sample happened to miss would score INCREMENTAL_STRUCTURE. The brief's
own framing ("the generic generator is the minimum bar") requires the bar to be the WHOLE
grammar, so:

    * GENERIC_REACHABLE is decided ANALYTICALLY, against the generator's exact IMAGE.
    * A materialized library is used ONLY for nearest-3 retrieval and for proving the
      predicate agrees with the real generator.

THE IMAGE IS NOT THE CARTESIAN PRODUCT
--------------------------------------
`controls.enumerate_pool` normalises after picking slots, so some slot combinations are
unreachable and must NOT be called generic:

    * `_conditions_for` emits every condition with the SAME kind. A cohort conditioned on
      venue AND opponent profile TOGETHER is compiler-valid but the generator can never emit
      it. That is a genuine two-variable interaction and the main channel through which real
      incremental structure can appear.
    * a comparator with `requires_filter` is forced to COMPETITION/1 and can never carry a
      venue condition.
    * a comparator with `requires_conditions` can never carry zero conditions.
    * `n_conditions` is drawn from (1, 1, 2), so three or more conditions is unreachable.

Treating the raw Cartesian product as the image would over-credit the generic baseline and
under-credit the LLM arms; treating the 2,000-sample as the image does the reverse.

FROZEN DEGENERACY RULE
----------------------
A condition set containing the same dimension+axis twice with different values (e.g.
venue=HOME and venue=AWAY) selects the empty cohort. Such keys are excluded from the library,
from the membership predicate and from retrieval, and are labelled INVALID for every arm
alike. Frozen here, before any model call, rather than decided after seeing retrievals.

ZERO SPEND.
"""
from __future__ import annotations

import hashlib
import itertools
import json

from src.research.hypothesis_v71 import controls as C
from src.research.hypothesis_v71 import ontology as O

GENERICLIB_VERSION = "v8a_genericlib_v1"

MAX_CONDITIONS_REACHABLE = 2
MAX_TARGET_METRICS = 5

SUBJECTS = tuple(C.SUBJECTS)
SIDES = tuple(C.SIDES)
WINDOWS = tuple(C.WINDOWS)
COMPARATORS = tuple(C.COMPARATORS)
CONDITION_KINDS = tuple(C.CONDITION_KINDS)
PROFILE_AXES = tuple(C.PROFILE_AXES)
PROFILE_VALUES = tuple(C.PROFILE_VALUES)
VENUE_VALUES = tuple(C.VENUE_VALUES)

#: Labels the deterministic judge can return (brief section 16).
EXACT_DUPLICATE = "EXACT_DUPLICATE"
STRUCTURAL_EQUIVALENT = "STRUCTURAL_EQUIVALENT"
INCREMENTAL_STRUCTURE = "INCREMENTAL_STRUCTURE"
INVALID = "INVALID"
ABSTAINED = "ABSTAINED"


# ---------------------------------------------------------------------------------------
# canonical structural key
# ---------------------------------------------------------------------------------------
def condition_signature(conditions):
    """Order-independent canonical signature of a condition set, plus its kinds."""
    sig, kinds = [], set()
    for c in conditions or []:
        dim = str(c.get("dimension") or "").strip()
        if dim in O.NON_RESTRICTIVE_VALUES:
            continue
        val = c.get("value")
        if val in O.NON_RESTRICTIVE_VALUES:
            continue
        axis = c.get("axis")
        sig.append((dim, axis, str(val)))
        kinds.add(C.CONDITION_KIND_OF.get(dim, "UNSUPPORTED:" + dim))
    # An identical condition asserted twice restricts nothing further, so it canonicalises
    # to one. A same-dimension pair at DIFFERENT values is a contradiction, not a
    # duplicate, and is caught by `is_degenerate`.
    return tuple(sorted(set(sig))), (sorted(kinds) or ["NONE"])


def is_degenerate(conditions) -> bool:
    """Same dimension+axis asserted at two different values -> empty cohort."""
    seen = {}
    for dim, axis, val in condition_signature(conditions)[0]:
        k = (dim, axis)
        if k in seen and seen[k] != val:
            return True
        seen[k] = val
    return False


def canonical_key(spec) -> tuple:
    """The structural identity of a hypothesis. Prose plays no part."""
    sig, _kinds = condition_signature(spec.get("conditions"))
    metrics = tuple(sorted({str(m).strip().lower()
                            for m in (spec.get("target_metrics") or [])}))
    return (
        str(spec.get("comparison") or "").upper(),
        str(spec.get("subject") or "").upper(),
        str(spec.get("side") or "").upper(),
        str(spec.get("window") or "ALL_PRIOR").upper(),
        sig,
        metrics,
    )


def key_hash(key) -> str:
    return hashlib.sha256(
        json.dumps(key, sort_keys=True, separators=(",", ":"),
                   default=list).encode()).hexdigest()


# ---------------------------------------------------------------------------------------
# the generator IMAGE, as an analytic predicate
# ---------------------------------------------------------------------------------------
def reachability(spec, vocabulary) -> dict:
    """Could `controls.enumerate_pool` ever have emitted this structure?

    Returns a verdict dict with the exact reason, so a rejection is always explainable and
    never a bare boolean.
    """
    vocab = set(vocabulary)
    reasons = []

    comparator = str(spec.get("comparison") or "").upper()
    binding = O.COMPARATOR_BINDINGS.get(comparator)
    if binding is None:
        return {"reachable": False, "blocking": "UNKNOWN_COMPARATOR",
                "reasons": [f"comparator {comparator!r} is not in the frozen ontology"]}

    if str(spec.get("subject") or "").upper() not in SUBJECTS:
        reasons.append("subject outside grammar")
    if str(spec.get("side") or "").upper() not in SIDES:
        reasons.append("side outside grammar")
    if str(spec.get("window") or "ALL_PRIOR").upper() not in WINDOWS:
        reasons.append("window outside grammar")

    metrics = sorted({str(m).strip().lower()
                      for m in (spec.get("target_metrics") or [])})
    if not metrics:
        reasons.append("no target metric")
    elif len(metrics) > MAX_TARGET_METRICS:
        reasons.append(f"{len(metrics)} target metrics exceeds grammar maximum "
                       f"{MAX_TARGET_METRICS}")
    outside = [m for m in metrics if m not in vocab]
    if outside:
        reasons.append("metrics outside the shared vocabulary: " + ", ".join(outside))

    conds = spec.get("conditions") or []
    sig, kinds = condition_signature(conds)
    n = len(sig)

    if is_degenerate(conds):
        return {"reachable": False, "blocking": "DEGENERATE_CONDITIONS",
                "reasons": ["the same dimension is asserted at two different values, "
                            "which selects the empty cohort"]}

    bad_dims = [k for k in kinds if k.startswith("UNSUPPORTED:")]
    if bad_dims:
        return {"reachable": False, "blocking": "UNSUPPORTED_FILTER_DIMENSION",
                "reasons": ["this corpus cannot honour: " + ", ".join(bad_dims)]}

    if n > MAX_CONDITIONS_REACHABLE:
        reasons.append(f"{n} conditions; the generator draws n_conditions from (1,1,2) so "
                       f"it can never emit more than {MAX_CONDITIONS_REACHABLE}")
    if n > 1 and len(kinds) > 1:
        reasons.append("conditions mix kinds (" + "+".join(kinds) + "); "
                       "`_conditions_for` emits every condition with a single kind, so the "
                       "generator can never emit this interaction")

    req = binding.get("requires_filter")
    if req:
        want = (req["dimension"], None, req["value"])
        if sig != (want,):
            reasons.append(f"{comparator} is normalised to exactly "
                           f"{req['dimension']}={req['value']}; no other condition set is "
                           f"reachable for it")
    elif binding.get("requires_conditions") and n == 0:
        reasons.append(f"{comparator} requires at least one condition")

    return {"reachable": not reasons,
            "blocking": None if not reasons else "NOT_IN_GENERATOR_IMAGE",
            "reasons": reasons,
            "n_conditions": n, "condition_kinds": kinds}


# ---------------------------------------------------------------------------------------
# materialized library (retrieval + predicate agreement proof)
# ---------------------------------------------------------------------------------------
def _condition_sets():
    """Every reachable single-kind condition set of size 0, 1 or 2, degenerates removed."""
    out = [("NONE", [])]
    for v in VENUE_VALUES:
        out.append(("VENUE", [{"dimension": "historical_venue_conditioning", "value": v}]))
    out.append(("COMPETITION", [{"dimension": "competition", "value": "SAME"}]))
    singles = [{"dimension": "opponent_profile", "axis": a, "value": b}
               for a in PROFILE_AXES for b in PROFILE_VALUES]
    for s in singles:
        out.append(("OPPONENT_PROFILE", [s]))
    for a, b in itertools.combinations(singles, 2):
        if a["axis"] == b["axis"]:
            continue                      # same axis at two bands -> empty cohort
        out.append(("OPPONENT_PROFILE", [a, b]))
    return out


def build_library(vocabulary):
    """The materialized structural library: exhaustive over every slot except metric-set
    cardinality, which is pinned to single metrics so the artifact stays finite.

    Retrieval only. The GENERIC/INCREMENTAL verdict never depends on this list.
    """
    vocab = sorted(vocabulary)
    lib = []
    for comparator in sorted(COMPARATORS):
        binding = O.COMPARATOR_BINDINGS[comparator]
        for kind, conds in _condition_sets():
            if binding.get("requires_filter"):
                req = binding["requires_filter"]
                if not (len(conds) == 1 and conds[0]["dimension"] == req["dimension"]
                        and conds[0].get("value") == req["value"]):
                    continue
            elif binding.get("requires_conditions") and not conds:
                continue
            for subject in SUBJECTS:
                for side in SIDES:
                    for window in WINDOWS:
                        for metric in vocab:
                            lib.append({
                                "comparison": comparator, "subject": subject,
                                "side": side, "window": window,
                                "conditions": [dict(c) for c in conds],
                                "target_metrics": [metric],
                                "condition_kind": kind,
                                "required_capabilities": (
                                    ["opponent_profile"]
                                    if (kind == "OPPONENT_PROFILE"
                                        or binding.get("requires_similarity")) else []),
                            })
    for i, h in enumerate(lib):
        h["generic_id"] = f"GEN_{i:07d}"
        h["structural_key_sha256"] = key_hash(canonical_key(h))
    return lib


def library_hash(lib) -> str:
    keys = sorted(h["structural_key_sha256"] for h in lib)
    return hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------------------
# deterministic structural retrieval (brief section 10) -- FROZEN BEFORE ANY CALL
# ---------------------------------------------------------------------------------------
#: Transparent, inspectable, integer-weighted structural distance. Deliberately NOT a
#: semantic embedding: the brief asks for a transparent structural distance unless there is
#: an exceptionally strong reason otherwise, and there is none.
DISTANCE_WEIGHTS = {
    "target_metric": 6,
    "metric_perspective": 5,
    "comparator": 4,
    "subject_role": 3,
    "condition_kind": 3,
    "condition_values": 2,
    "window": 2,
    "n_conditions": 1,
}


def distance(a, b) -> int:
    """Structural distance between two hypotheses. Integer, symmetric, order-independent."""
    d = 0
    ma = {str(m).lower() for m in (a.get("target_metrics") or [])}
    mb = {str(m).lower() for m in (b.get("target_metrics") or [])}
    if not (ma & mb):
        d += DISTANCE_WEIGHTS["target_metric"]
    elif ma != mb:
        d += 1
    if str(a.get("side", "")).upper() != str(b.get("side", "")).upper():
        d += DISTANCE_WEIGHTS["metric_perspective"]
    if str(a.get("comparison", "")).upper() != str(b.get("comparison", "")).upper():
        d += DISTANCE_WEIGHTS["comparator"]
    if str(a.get("subject", "")).upper() != str(b.get("subject", "")).upper():
        d += DISTANCE_WEIGHTS["subject_role"]

    sa, ka = condition_signature(a.get("conditions"))
    sb, kb = condition_signature(b.get("conditions"))
    if set(ka) != set(kb):
        d += DISTANCE_WEIGHTS["condition_kind"]
    if set(sa) != set(sb):
        d += DISTANCE_WEIGHTS["condition_values"]
    if str(a.get("window", "ALL_PRIOR")).upper() != str(b.get("window", "ALL_PRIOR")).upper():
        d += DISTANCE_WEIGHTS["window"]
    d += DISTANCE_WEIGHTS["n_conditions"] * abs(len(sa) - len(sb))
    return d


def nearest(candidate, library, k=3):
    """The k structurally nearest generic hypotheses. Deterministic: ties break on the
    generic_id, which is itself a frozen enumeration position. The LLM never chooses."""
    scored = sorted(((distance(candidate, g), g["generic_id"], g) for g in library),
                    key=lambda t: (t[0], t[1]))
    return [{"generic_id": g["generic_id"], "distance": dist,
             "comparison": g["comparison"], "subject": g["subject"], "side": g["side"],
             "window": g["window"], "conditions": g["conditions"],
             "target_metrics": g["target_metrics"]}
            for dist, _gid, g in scored[:k]]


# ---------------------------------------------------------------------------------------
# the deterministic final judgment (brief section 16)
# ---------------------------------------------------------------------------------------
def judge(spec, library_keys, vocabulary, *, ir_ok: bool, ir_status: str) -> dict:
    """The label belongs to deterministic code. The model's own novelty prose is audit
    evidence only and is never read here."""
    if not ir_ok:
        return {"label": INVALID, "reason": f"compiler rejected the candidate: {ir_status}"}

    conds = spec.get("conditions") or []
    if is_degenerate(conds):
        return {"label": INVALID,
                "reason": "degenerate condition set selects the empty cohort"}

    reach = reachability(spec, vocabulary)
    kh = key_hash(canonical_key(spec))

    if kh in library_keys:
        return {"label": EXACT_DUPLICATE,
                "reason": "canonical structural key is byte-identical to an enumerated "
                          "generic hypothesis",
                "structural_key_sha256": kh}
    if reach["reachable"]:
        return {"label": STRUCTURAL_EQUIVALENT,
                "reason": "different prose, but the structure lies inside the generic "
                          "generator's image: enumeration already represents this "
                          "statistical question",
                "structural_key_sha256": kh}
    return {"label": INCREMENTAL_STRUCTURE,
            "reason": "measurable, but outside the generic generator's image: "
                      + "; ".join(reach["reasons"]),
            "not_reachable_because": reach["reasons"],
            "structural_key_sha256": kh}


def version_stamp() -> dict:
    return {
        "genericlib_version": GENERICLIB_VERSION,
        "structure_only": True,
        "exposes_survival": False,
        "exposes_effects": False,
        "exposes_quality_scores": False,
        "exposes_p_values": False,
        "exposes_candidate_status": False,
        "exposes_fold_performance": False,
        "exposes_confirmatory_results": False,
        "membership_is_analytic_not_sampled": True,
        "retrieval": "transparent integer structural distance; NOT a semantic embedding",
        "distance_weights": dict(DISTANCE_WEIGHTS),
        "degeneracy_rule": ("same dimension+axis at two values is excluded from the library, "
                            "the predicate and retrieval, and is INVALID for every arm"),
        "grammar_source": "hypothesis_v71.controls + hypothesis_v71.ontology (frozen)",
    }

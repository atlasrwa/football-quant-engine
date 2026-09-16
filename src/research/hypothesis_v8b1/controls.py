"""V8B.1 control arms R (structurally matched blind) and H (deterministic heuristic). See
research/hypothesis_engine/V8B1_BLIND_CONTROL_SPEC.md and V8B1_HEURISTIC_SPEC.md for the full
design rationale.

Both arms consume ONLY structural metadata already returned by
src.research.hypothesis_v8b1.search.search() -- which itself excludes every outcome-shaped
field by construction (FORBIDDEN_OUTCOME_FIELDS, enforced by an assertion in search.py).
Neither arm reads a Sonnet selection's prose, mechanism_summary, or research_reason -- only
its structural shape (target_metrics[0], subject, side, comparator, n_conditions,
capability_status) and the COUNT of Sonnet's valid selections at a fixture.

ZERO SPEND. No network. No CHAMPION. Reads no target outcome, ever.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v8b1 import search as SE

CONTROLS_VERSION = "v8b1_controls_v1"

#: The six structural matching dimensions, reusing V7.1's own SLOTS vocabulary in spirit
#: (controls.py::SLOTS) rather than inventing a new one.
MATCH_DIMENSIONS = ("target_metric", "subject", "side", "comparator", "n_conditions",
                    "capability_status")

HEURISTIC_COVERAGE_SUPPORTED = 2.0
HEURISTIC_COVERAGE_RESTRICTED = 1.0
HEURISTIC_SALIENCE_FIRST_CONDITION = 1.0
HEURISTIC_COMPLEXITY_PENALTY_PER_EXTRA_CONDITION = 0.5
HEURISTIC_SIMILARITY_BONUS = 0.5


@dataclass(frozen=True)
class SonnetShape:
    """The ONLY view of a Sonnet selection either control arm may see: its structural shape
    plus which fixture it was made at. No prose field exists on this type at all -- there is
    nothing to accidentally read."""
    hypothesis_id: str
    target_metric: str
    subject: str
    side: str
    comparator: str
    n_conditions: int
    capability_status: str


def shape_of(candidate: dict) -> SonnetShape:
    """Build a SonnetShape from a search.py candidate dict (or an equivalently-shaped
    resolved selection) -- the ONLY conversion function either control arm uses."""
    return SonnetShape(
        hypothesis_id=candidate["hypothesis_id"],
        target_metric=candidate["target_metrics"][0],
        subject=candidate["subject"],
        side=candidate["side"],
        comparator=candidate["comparator"],
        n_conditions=candidate["complexity"]["n_conditions"],
        capability_status=candidate["capability_status"],
    )


# ============================ Arm R: structurally matched blind =========================
_RELAXATION_TIERS = ("EXACT", "CONDITIONS_PM1", "CAPABILITY_EITHER", "MECHANISM_FAMILY",
                    "SIDE_EITHER", "UNMATCHED")


def _tier_query_kwargs(shape: SonnetShape, tier: str) -> dict:
    if tier == "EXACT":
        return {"target_metric": shape.target_metric, "subject": shape.subject,
               "side": shape.side, "comparator": shape.comparator}
    if tier == "CONDITIONS_PM1":
        return {"target_metric": shape.target_metric, "subject": shape.subject,
               "side": shape.side, "comparator": shape.comparator}
    if tier == "CAPABILITY_EITHER":
        return {"target_metric": shape.target_metric, "subject": shape.subject,
               "side": shape.side, "comparator": shape.comparator}
    if tier == "MECHANISM_FAMILY":
        want = None
        for mech, (comp, _prof) in SE.MECHANISM_TYPES.items():
            if comp == shape.comparator:
                want = mech
                break
        return {"target_metric": shape.target_metric, "subject": shape.subject,
               "side": shape.side, "mechanism_type": want} if want else None
    if tier == "SIDE_EITHER":
        return {"target_metric": shape.target_metric, "subject": shape.subject}
    return None


def _tier_filter(shape: SonnetShape, tier: str, candidates: list[dict]) -> list[dict]:
    if tier == "EXACT":
        return [c for c in candidates
               if c["complexity"]["n_conditions"] == shape.n_conditions
               and c["capability_status"] == shape.capability_status]
    if tier == "CONDITIONS_PM1":
        return [c for c in candidates
               if abs(c["complexity"]["n_conditions"] - shape.n_conditions) <= 1
               and c["capability_status"] == shape.capability_status]
    if tier == "CAPABILITY_EITHER":
        return [c for c in candidates
               if abs(c["complexity"]["n_conditions"] - shape.n_conditions) <= 1]
    if tier in ("MECHANISM_FAMILY", "SIDE_EITHER"):
        return list(candidates)
    return []


def match_blind_control(shape: SonnetShape, capability, exclude_ids: set) -> dict | None:
    """One blind control for one Sonnet selection, at one fixture. Returns None (UNMATCHED)
    if no candidate survives the frozen relaxation order. `exclude_ids` prevents the same
    hypothesis_id from being used as a control twice at the same fixture."""
    for tier in _RELAXATION_TIERS:
        if tier == "UNMATCHED":
            return None
        kwargs = _tier_query_kwargs(shape, tier)
        if kwargs is None:
            continue
        q = SE.SearchQuery(max_results=SE.MAX_RESULTS_HARD_CAP, **kwargs)
        candidates = [c for c in SE.search(q, capability) if c["hypothesis_id"] not in exclude_ids]
        filtered = _tier_filter(shape, tier, candidates)
        if filtered:
            filtered.sort(key=lambda c: c["hypothesis_id"])
            return dict(filtered[0], matched_tier=tier)
    return None


def blind_selections_for_fixture(sonnet_shapes: list[SonnetShape], capability) -> dict:
    """Arm R's full output for one fixture: one matched (or UNMATCHED) control per Sonnet
    selection, in the SAME order Sonnet emitted them, sized to exactly K_valid(T) entries
    (UNMATCHED entries included, counted, never silently dropped)."""
    used = set()
    out = []
    for shape in sonnet_shapes:
        m = match_blind_control(shape, capability, used)
        if m is not None:
            used.add(m["hypothesis_id"])
            out.append({"status": "MATCHED", "sonnet_hypothesis_id": shape.hypothesis_id,
                       **m})
        else:
            out.append({"status": "UNMATCHED", "sonnet_hypothesis_id": shape.hypothesis_id})
    return {"k_valid": len(sonnet_shapes), "n_matched": sum(1 for o in out if o["status"] == "MATCHED"),
           "selections": out}


# ============================== Arm H: deterministic heuristic ===========================
def heuristic_score(candidate: dict) -> float:
    """The frozen, parameter-free scoring formula. Consumes ONLY fields search.py already
    returns -- there is no outcome-shaped field on `candidate` to accidentally read."""
    coverage = (HEURISTIC_COVERAGE_SUPPORTED if candidate["capability_status"] == "SUPPORTED"
               else HEURISTIC_COVERAGE_RESTRICTED)
    n_cond = candidate["complexity"]["n_conditions"]
    salience = min(n_cond, 1) * HEURISTIC_SALIENCE_FIRST_CONDITION
    penalty = max(n_cond - 1, 0) * HEURISTIC_COMPLEXITY_PENALTY_PER_EXTRA_CONDITION
    similarity_bonus = (HEURISTIC_SIMILARITY_BONUS if candidate["complexity"]["uses_similarity"]
                        else 0.0)
    return coverage + salience - penalty + similarity_bonus


def heuristic_selections_for_fixture(k_valid: int, capability) -> dict:
    """Arm H's full output for one fixture: top-K_valid candidates by heuristic_score over
    the FULL admissible universe (no filter), tie-broken by hypothesis_id."""
    q = SE.SearchQuery(max_results=SE.MAX_RESULTS_HARD_CAP)
    candidates = SE.search(q, capability)
    scored = [(heuristic_score(c), c["hypothesis_id"], c) for c in candidates]
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = [c for _s, _id, c in scored[:k_valid]]
    return {"k_valid": k_valid, "n_selected": len(top),
           "selections": [dict(c, heuristic_score=s) for s, _id, c in scored[:k_valid]]}


def version_stamp() -> dict:
    return {"controls_version": CONTROLS_VERSION,
            "match_dimensions": list(MATCH_DIMENSIONS),
            "relaxation_tiers": list(_RELAXATION_TIERS),
            "heuristic_coefficients": {
                "coverage_supported": HEURISTIC_COVERAGE_SUPPORTED,
                "coverage_restricted": HEURISTIC_COVERAGE_RESTRICTED,
                "salience_first_condition": HEURISTIC_SALIENCE_FIRST_CONDITION,
                "complexity_penalty_per_extra_condition":
                    HEURISTIC_COMPLEXITY_PENALTY_PER_EXTRA_CONDITION,
                "similarity_bonus": HEURISTIC_SIMILARITY_BONUS,
            },
            "reads_outcomes": False, "reads_llm_prose": False,
            "tuned_against_sonnet_result": False}

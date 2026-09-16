"""V8B.1 deterministic hypothesis search interface (`v8b1_search_v1`). See
research/hypothesis_engine/V8B1_HYPOTHESIS_SEARCH_SPEC.md for the full design rationale.

Lets Sonnet navigate the admissible hypothesis universe already defined by
`hypothesis_v71.ontology`/`capability` without pasting that universe into the prompt and
without asking the model to enumerate it from memory. Every candidate is built from
structural fields alone -- ontology grammar plus the capability contract's coverage
classification -- and carries NO outcome, effect, p-value, or terminal state.

ZERO SPEND. No network. No CHAMPION. Reads no target outcome, ever.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import ontology as O

SEARCH_VERSION = "v8b1_search_v1"

MAX_RESULTS_HARD_CAP = 50

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
               "shots_on_target_against", "possession_for", "shots_against")

#: mechanism_type -> (comparator, requires_opponent_profile_condition). A pure relabeling of
#: existing comparators for query convenience -- introduces no new grammar.
MECHANISM_TYPES = {
    "attack_x_defense": ("SUBJECT_CONDITIONAL_VS_BASELINE", True),
    "cross_entity": ("SUBJECT_VS_FIXTURE_OPPONENT", False),
    "similar_opponent": ("SIMILAR_OPPONENT_COHORT", False),
    "recent_regime": ("SUBJECT_RECENT_VS_LONG_BASELINE", False),
    "venue_conditioned": ("SUBJECT_VENUE_BASELINE", False),
    "competition_conditioned": ("SUBJECT_COMPETITION_BASELINE", False),
    "league_environment": ("LEAGUE_ENVIRONMENT_BASELINE", False),
    "opponent_baseline": ("OPPONENT_OVERALL_BASELINE", False),
    "unconditional": ("SUBJECT_OVERALL_BASELINE", False),
}

#: Fields that must NEVER appear on a returned candidate. Enforced by an explicit test
#: (V8B1_HYPOTHESIS_SEARCH_SPEC.md section 5, item 1), not merely by convention.
FORBIDDEN_OUTCOME_FIELDS = frozenset({
    "effect", "score", "p_value", "oos_quality_score", "direction_agreement",
    "terminal_state", "candidate_feature", "candidate_feature_eligible", "survives",
    "oos_survives", "quality_score", "mean_effect", "signal_variance",
})


@dataclass(frozen=True)
class SearchQuery:
    target_metric: str | None = None
    subject: str | None = None
    side: str | None = None
    comparator: str | None = None
    mechanism_type: str | None = None
    opponent_profile_dimension: str | None = None
    venue: str | None = None
    competition_conditioned: bool | None = None
    window: str | None = None
    max_conditions: int | None = None
    max_results: int = 20


def _candidate_shapes(capability, window_choices=("ALL_PRIOR",)):
    """Every structural shape the ontology can express, restricted to metrics this fixture's
    competition actually supports (SUPPORTED or RESTRICTED, never UNKNOWN/UNSUPPORTED). This
    is the same finite grammar controls.enumerate_pool draws from, walked exhaustively rather
    than sampled, because the per-fixture candidate pool here is small enough to enumerate."""
    metrics = sorted(m for m in CAP.METRIC_SEMANTICS
                     if capability.classify_metric(m)[0] in (CAP.SUPPORTED, CAP.RESTRICTED))
    subjects = ("HOME_TEAM", "AWAY_TEAM")
    sides = ("FOR", "AGAINST")
    comparators = sorted(O.COMPARATOR_BINDINGS)
    condition_shapes = [[]]
    for value in O.FILTER_DIMENSIONS["historical_venue_conditioning"]["values"]:
        condition_shapes.append([{"dimension": "historical_venue_conditioning",
                                  "value": value}])
    for axis in PROFILE_AXES:
        for band in O.FILTER_DIMENSIONS["opponent_profile"]["values"]:
            condition_shapes.append([{"dimension": "opponent_profile", "value": band,
                                     "axis": axis}])
    condition_shapes.append([{"dimension": "competition", "value": "SAME"}])

    for metric, subj, side, comp, window, conds in itertools.product(
            metrics, subjects, sides, comparators, window_choices, condition_shapes):
        binding = O.COMPARATOR_BINDINGS[comp]
        caps = ()
        if any(c.get("dimension") == "opponent_profile" for c in conds) or \
                binding.get("requires_similarity"):
            caps = ("opponent_profile",)
        spec = {"target_metrics": [metric], "subject": subj, "side": side,
               "comparison": comp, "window": window, "conditions": conds,
               "research_family": "V8B1_SEARCH", "required_capabilities": caps}
        yield spec


def _matches(spec, ir, capability, q: SearchQuery) -> bool:
    if ir.status != IRM.OK:
        return False
    status, _adm, _detail = capability.classify_metrics(ir.target_metrics)
    if status not in (CAP.SUPPORTED, CAP.RESTRICTED):
        return False
    if q.target_metric and q.target_metric not in ir.target_metrics:
        return False
    if q.subject and spec["subject"] != q.subject:
        return False
    if q.side and spec["side"] != q.side:
        return False
    if q.comparator and spec["comparison"] != q.comparator:
        return False
    if q.mechanism_type:
        want_comp, want_profile = MECHANISM_TYPES.get(q.mechanism_type, (None, False))
        if want_comp is None or spec["comparison"] != want_comp:
            return False
        has_profile = any(c.get("dimension") == "opponent_profile" for c in spec["conditions"])
        if want_profile and not has_profile:
            return False
    if q.opponent_profile_dimension:
        if not any(c.get("dimension") == "opponent_profile"
                  and c.get("axis") == q.opponent_profile_dimension
                  for c in spec["conditions"]):
            return False
    if q.venue:
        if not any(c.get("dimension") == "historical_venue_conditioning"
                  and c.get("value") == q.venue for c in spec["conditions"]):
            return False
    if q.competition_conditioned is not None:
        has_comp = any(c.get("dimension") == "competition" for c in spec["conditions"])
        if has_comp != q.competition_conditioned:
            return False
    if q.window and spec["window"] != q.window:
        return False
    if q.max_conditions is not None and len(spec["conditions"]) > q.max_conditions:
        return False
    return True


def _sort_key(status_rank, spec, ir):
    return (status_rank, len(spec["conditions"]), ir.ir_id())


_STATUS_RANK = {CAP.SUPPORTED: 0, CAP.RESTRICTED: 1}


def search(query: SearchQuery, capability) -> list[dict]:
    """Deterministically enumerate up to `query.max_results` (hard-capped at
    MAX_RESULTS_HARD_CAP) candidate hypotheses matching `query`, for the fixture whose
    admissible universe `capability` describes. Same query + same capability -> byte-
    identical output, always."""
    max_results = min(int(query.max_results), MAX_RESULTS_HARD_CAP)
    rows = []
    for spec in _candidate_shapes(capability):
        ir = IRM.build_ir(spec)
        if not _matches(spec, ir, capability, query):
            continue
        status, adm, _detail = capability.classify_metrics(ir.target_metrics)
        rows.append((_sort_key(_STATUS_RANK[status], spec, ir), spec, ir, status, adm))
    rows.sort(key=lambda r: r[0])

    out = []
    for _key, spec, ir, status, adm in rows[:max_results]:
        candidate = {
            "hypothesis_id": ir.ir_id(),
            "structural_description": ir.describe(),
            "target_metrics": list(ir.target_metrics),
            "subject": spec["subject"],
            "side": spec["side"],
            "comparator": spec["comparison"],
            "conditions": spec["conditions"],
            "window": spec["window"],
            "capability_status": status,
            "admissible_competitions": sorted(adm),
            "complexity": {
                "n_conditions": len(spec["conditions"]),
                "n_target_metrics": len(ir.target_metrics),
                "uses_similarity": bool(spec["required_capabilities"]),
            },
        }
        assert not (set(candidate) & FORBIDDEN_OUTCOME_FIELDS), (
            "a forbidden outcome-shaped field leaked into a search result")
        out.append(candidate)
    return out


def resolve(hypothesis_id: str, capability) -> IRM.IR | None:
    """Resolve a canonical hypothesis_id back to its IR, by re-walking the same finite grammar
    search() draws from and matching on ir_id(). Used to validate a Sonnet selection actually
    corresponds to a real, previously-returned candidate (V8B1_HYPOTHESIS_SEARCH_SPEC.md
    section 6) rather than a free-floating string."""
    for spec in _candidate_shapes(capability):
        ir = IRM.build_ir(spec)
        if ir.status == IRM.OK and ir.ir_id() == hypothesis_id:
            return ir
    return None


def version_stamp() -> dict:
    return {"search_version": SEARCH_VERSION,
            "max_results_hard_cap": MAX_RESULTS_HARD_CAP,
            "mechanism_types": sorted(MECHANISM_TYPES),
            "forbidden_outcome_fields": sorted(FORBIDDEN_OUTCOME_FIELDS),
            "reads_outcomes": False,
            "deterministic": True,
            "ordering": "capability_status_rank, n_conditions, ir_id (all structural)"}

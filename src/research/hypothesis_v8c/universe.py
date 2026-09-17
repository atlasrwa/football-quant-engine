"""V8C selectable universe (`v8c_universe_v1`).

Builds, for ONE target fixture:

    ADMISSIBLE_IR          every structurally valid IR the frozen ontology grammar expresses,
                           restricted to metrics the capability contract covers -- FULLY
                           ENUMERATED, never truncated
    PRE_T_EVALUABLE_IR     the subset the deterministic engine proves, before kickoff, it can
                           actually measure here

WHY THE FULL ENUMERATION MATTERS (`D-V8C-P1-HUNIVERSE`)
------------------------------------------------------
`hypothesis_v8b1.search.search()` sorts by `(capability_status, n_conditions, ir_id)` and then
truncates at `MAX_RESULTS_HARD_CAP = 50`. That cap is a PRESENTATION limit -- how many
candidates a single LLM tool call returns -- and it is fine for that. It is NOT the universe.
V8B.1's H arm ranked its heuristic over `search(max_results=50)`, so "H's top pick" was really
"the best of the 50 lowest ir_ids", a different question from the one S and R answered.

V8C therefore computes evaluability over the WHOLE enumeration (19,008 structurally valid IRs
on this corpus) and filters BEFORE any ordering or truncation. The presentation cap is applied
last, to the already-filtered set, exactly where it belongs.

The candidate dicts carry the same structural fields V8B.1's `search()` emitted -- so the
frozen `shape_of`, the frozen matching tiers and the frozen `heuristic_score` all consume them
unchanged -- plus the pre-T support quantities, which are structural, not outcome-derived.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v8b1 import search as SE
from src.research.hypothesis_v8c import pre_t as PT

UNIVERSE_VERSION = "v8c_universe_v1"

#: Presentation cap for ONE LLM tool call. Applied AFTER the evaluability filter, never before.
PRESENTATION_CAP = SE.MAX_RESULTS_HARD_CAP

#: Retained verbatim from V8B.1: no outcome-shaped field may appear on a candidate.
FORBIDDEN_OUTCOME_FIELDS = SE.FORBIDDEN_OUTCOME_FIELDS

_STATUS_RANK = {CAP.SUPPORTED: 0, CAP.RESTRICTED: 1}


@dataclass(frozen=True)
class FixtureUniverse:
    """Both universes for one target fixture, plus an EXPLICIT attrition ledger.

    The ledger separates the three stages of the funnel so no count is conflated:

        n_shapes_enumerated      every shape the frozen grammar emits (S3 input)
        n_structurally_invalid   IR build failed (MISSING_REQUIRED_CONDITION etc.)
        n_capability_excluded    metric not SUPPORTED/RESTRICTED anywhere in the corpus
        n_admissible             = enumerated - structurally_invalid - capability_excluded
                                   (S3 output: the ADMISSIBLE_IR universe)
        status_counts            PreTEvaluability status -> count, over `n_admissible` ONLY
        n_evaluable              = status_counts[PRE_T_EVALUABLE]  (S5 output)
    """
    fixture_id: str
    rec_i: int
    competition: str
    admissible: tuple          # tuple[dict] -- populated only when collect_admissible=True
    evaluable: tuple           # tuple[dict] -- PRE_T_EVALUABLE, ordered structurally
    status_counts: dict        # PreTEvaluability status -> count over the admissible universe
    n_shapes_enumerated: int = 0
    n_structurally_invalid: int = 0
    n_capability_excluded: int = 0
    n_admissible: int = 0
    n_evaluable: int = 0

    def evaluable_ids(self) -> tuple:
        return tuple(c["hypothesis_id"] for c in self.evaluable)

    def ledger(self) -> dict:
        """The attrition funnel as a flat, hashable record. The two assertions are the point:
        a funnel whose stages do not reconcile is a reporting defect, not a rounding detail."""
        assert (self.n_shapes_enumerated - self.n_structurally_invalid
                - self.n_capability_excluded) == self.n_admissible, "universe ledger mismatch"
        assert sum(self.status_counts.values()) == self.n_admissible, (
            "pre-T status counts do not sum to the admissible universe")
        return {"n_shapes_enumerated": self.n_shapes_enumerated,
                "n_structurally_invalid": self.n_structurally_invalid,
                "n_capability_excluded": self.n_capability_excluded,
                "n_admissible": self.n_admissible,
                "n_pre_t_evaluable": self.n_evaluable,
                "pre_t_status_counts": dict(sorted(self.status_counts.items()))}


def _candidate_dict(spec, ir, status, adm, verdict) -> dict:
    """The V8B.1 candidate shape, plus PRE-T STRUCTURAL support quantities.

    Every added field is a count, a diversity measure or a weighting property of PRIOR
    observations. None is an effect, a score, a direction or a p-value -- the
    FORBIDDEN_OUTCOME_FIELDS assertion below is kept as the mechanical check.
    """
    c = {
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
        "pre_t": {
            "status": verdict.status,
            "raw_n": verdict.raw_n,
            "unique_fixtures": verdict.unique_fixtures,
            "unique_opponents": verdict.unique_opponents,
            "effective_n": verdict.effective_n,
            "weight_concentration": verdict.weight_concentration,
            "baseline_n": verdict.baseline_n,
        },
    }
    assert not (set(c) & FORBIDDEN_OUTCOME_FIELDS), (
        "a forbidden outcome-shaped field leaked into a V8C candidate")
    return c


def _sort_key(c):
    """Structural ordering only: capability rank, then condition count, then canonical id.
    Identical in spirit to V8B.1's `_sort_key`; nothing here reads a support quantity, so the
    order cannot be read as a measurability ranking."""
    return (_STATUS_RANK.get(c["capability_status"], 9),
            c["complexity"]["n_conditions"], c["hypothesis_id"])


def build_fixture_universe(index, rec_i, *, ctx, capability, fixture_id=None,
                           collect_admissible=False) -> FixtureUniverse:
    """Enumerate and classify the WHOLE candidate space at one target fixture.

    `collect_admissible=False` (the default) keeps only the evaluable candidates and the
    status counts -- the admissible list is 19,008 dicts per fixture, which is not something
    to hold for 947 fixtures at once. The COUNTS are always exact.
    """
    rec = index.recs[rec_i]
    fid = str(fixture_id if fixture_id is not None else rec.fixture_id)
    admissible, evaluable, counts = [], [], {}
    n_shapes = n_structurally_invalid = n_capability_excluded = 0

    for spec in SE._candidate_shapes(capability):
        n_shapes += 1
        ir = IRM.build_ir(spec)
        if ir.status != IRM.OK:
            n_structurally_invalid += 1
            continue
        status, adm, _detail = capability.classify_metrics(ir.target_metrics)
        if status not in (CAP.SUPPORTED, CAP.RESTRICTED):
            n_capability_excluded += 1
            continue
        verdict = PT.evaluate_candidate(ir, index, rec_i, ctx=ctx, capability=capability)
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
        cand = _candidate_dict(spec, ir, status, adm, verdict)
        if collect_admissible:
            admissible.append(cand)
        if verdict.evaluable:
            evaluable.append(cand)

    evaluable.sort(key=_sort_key)
    if collect_admissible:
        admissible.sort(key=_sort_key)
    n_admissible = n_shapes - n_structurally_invalid - n_capability_excluded

    return FixtureUniverse(fixture_id=fid, rec_i=int(rec_i), competition=rec.competition,
                           admissible=tuple(admissible), evaluable=tuple(evaluable),
                           status_counts=dict(sorted(counts.items())),
                           n_shapes_enumerated=n_shapes,
                           n_structurally_invalid=n_structurally_invalid,
                           n_capability_excluded=n_capability_excluded,
                           n_admissible=int(n_admissible), n_evaluable=len(evaluable))


# ---- the LLM-facing search, now over the EVALUABLE universe (§9) -------------------------
def search_evaluable(query: SE.SearchQuery, fixture_universe: FixtureUniverse) -> list[dict]:
    """The same structural query grammar V8B.1 froze, answered from PRE_T_EVALUABLE_IR_SPACE.

    Sonnet keeps every research affordance it had -- search, compare, reason, abstain -- and
    the football reasoning prompt is unchanged (§9). The ONLY difference is that the candidate
    set no longer contains hypotheses the engine has already proven it cannot measure here.
    That is measurability control, not outcome cherry-picking: the filter reads no target
    observation, no effect and no direction.

    The presentation cap is applied LAST, to the filtered set.
    """
    rows = [c for c in fixture_universe.evaluable if _query_matches(query, c)]
    rows.sort(key=_sort_key)
    return rows[:min(int(query.max_results), PRESENTATION_CAP)]


def _query_matches(q: SE.SearchQuery, c: dict) -> bool:
    """Field-for-field the same predicate set as `search._matches`, evaluated against an
    already-built candidate dict instead of a spec/IR pair."""
    if q.target_metric and q.target_metric not in c["target_metrics"]:
        return False
    if q.subject and c["subject"] != q.subject:
        return False
    if q.side and c["side"] != q.side:
        return False
    if q.comparator and c["comparator"] != q.comparator:
        return False
    if q.mechanism_type:
        want_comp, want_profile = SE.MECHANISM_TYPES.get(q.mechanism_type, (None, False))
        if want_comp is None or c["comparator"] != want_comp:
            return False
        has_profile = any(x.get("dimension") == "opponent_profile" for x in c["conditions"])
        if want_profile and not has_profile:
            return False
    if q.opponent_profile_dimension:
        if not any(x.get("dimension") == "opponent_profile"
                   and x.get("axis") == q.opponent_profile_dimension
                   for x in c["conditions"]):
            return False
    if q.venue:
        if not any(x.get("dimension") == "historical_venue_conditioning"
                   and x.get("value") == q.venue for x in c["conditions"]):
            return False
    if q.competition_conditioned is not None:
        has_comp = any(x.get("dimension") == "competition" for x in c["conditions"])
        if has_comp != q.competition_conditioned:
            return False
    if q.window and c["window"] != q.window:
        return False
    if q.max_conditions is not None and c["complexity"]["n_conditions"] > q.max_conditions:
        return False
    return True


def version_stamp() -> dict:
    return {"universe_version": UNIVERSE_VERSION,
            "repairs": ["D-V8C-P1-HUNIVERSE", "D-V8C-P1-MEASSPACE"],
            "enumerates_full_grammar_before_filtering": True,
            "presentation_cap": PRESENTATION_CAP,
            "presentation_cap_applied_after_filter": True,
            "ordering": "capability_status_rank, n_conditions, ir_id (all structural)",
            "candidate_fields_added_vs_v8b1": ["pre_t.status", "pre_t.raw_n",
                                               "pre_t.unique_fixtures",
                                               "pre_t.unique_opponents", "pre_t.effective_n",
                                               "pre_t.weight_concentration",
                                               "pre_t.baseline_n"],
            "added_fields_are_structural_not_outcome": True,
            "prompt_changed": False,
            "reads_target_outcome": False}

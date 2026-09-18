"""V8C selectable universe (`v8c_universe_v2`).

Repairs P1 UNIVERSE-GRAMMAR (uses the declared V8C grammar, not `_candidate_shapes`),
P1 MEASSPACE (two candidate projections), P1 SEARCH-REACHABILITY (deterministic pagination)
and P1 RESEARCH-FAMILY (structural family carried on every candidate).

    ADMISSIBLE_IR          structurally valid + capability-covered + COMPADM at this fixture
    PRE_T_EVALUABLE_IR     the subset the engine proves, before kickoff, it can measure here

THE TWO PROJECTIONS -- P1 MEASSPACE
-----------------------------------
Every candidate exists in exactly two forms:

    internal     structural fields + the `pre_t` support block (raw_n, unique_fixtures,
                 unique_opponents, effective_n, weight_concentration, baseline_n)
    llm_facing   structural fields ONLY

The pre-T classifier, R matching, H ranking and the freeze records consume `internal`. The
search tool Sonnet sees returns `llm_facing`. Support magnitudes are withheld because the
endpoint must measure FOOTBALL REASONING, not sample-size shopping: if Sonnet could read
`raw_n`, a trivially winning policy is "pick the biggest cohort", and the experiment would
measure whether a model can sort a column. Every candidate in the space is already evaluable,
so withholding the magnitudes removes a confound without withholding anything the football
question needs.

This is SEPARATE from `FORBIDDEN_OUTCOME_FIELDS`, which passes on these keys -- they are
support statistics, not outcomes. `assert_llm_safe` is the mechanical check.

PAGINATION -- P1 SEARCH-REACHABILITY
------------------------------------
V8B.1's `search()` truncated at 50 with no cursor, so everything after the 50th candidate of
any query was unreachable to S while R matched within tier queries and H ranked the whole
evaluable set. The three arms did not share an action space. V8C paginates over the total
order `(capability_status_rank, n_conditions, ir_id)` -- `ir_id` is unique, so the order is
total and the cursor is well defined. `unreachable_candidate_count` is COMPUTED by exhaustive
pagination, never asserted.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v8b1 import search as SE
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import pre_t as PT

UNIVERSE_VERSION = "v8c_universe_v2"

#: Presentation cap for ONE tool result. A page size, never a limit on the reachable set.
PAGE_SIZE_CAP = 50

#: Retained verbatim from V8B.1.
FORBIDDEN_OUTCOME_FIELDS = SE.FORBIDDEN_OUTCOME_FIELDS

#: Support-statistic keys that must NEVER appear in the Sonnet-facing projection (MEASSPACE).
SUPPORT_KEYS = frozenset({"pre_t", "raw_n", "unique_fixtures", "unique_opponents",
                          "effective_n", "weight_concentration", "baseline_n", "scale_var",
                          "support_status", "support_failures"})

_STATUS_RANK = {CAP.SUPPORTED: 0, CAP.RESTRICTED: 1}

SearchQuery = SE.SearchQuery


@dataclass(frozen=True)
class FixtureUniverse:
    """Both universes for one target fixture, plus an explicit attrition ledger."""
    fixture_id: str
    rec_i: int
    competition: str
    evaluable: tuple            # internal projection, ordered by the total structural key
    status_counts: dict
    n_shapes_enumerated: int = 0
    n_structurally_invalid: int = 0
    n_capability_excluded: int = 0
    n_admissible: int = 0
    n_evaluable: int = 0

    def evaluable_ids(self) -> tuple:
        return tuple(c["hypothesis_id"] for c in self.evaluable)

    def ledger(self) -> dict:
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

    def research_family_counts(self) -> dict:
        out = {}
        for c in self.evaluable:
            out[c["research_family"]] = out.get(c["research_family"], 0) + 1
        return dict(sorted(out.items()))


def _internal_candidate(spec, ir, status, adm, verdict) -> dict:
    c = {
        "hypothesis_id": ir.ir_id(),
        "structural_description": ir.describe(),
        "target_metrics": list(ir.target_metrics),
        "subject": spec["subject"],
        "side": spec["side"],
        "comparator": spec["comparison"],
        "conditions": spec["conditions"],
        "window": spec["window"],
        "research_family": spec["research_family"],
        "capability_status": status,
        "admissible_competitions": sorted(adm),
        "complexity": {"n_conditions": len(spec["conditions"]),
                       "n_target_metrics": len(ir.target_metrics),
                       "uses_similarity": bool(spec["required_capabilities"])},
        "pre_t": {"status": verdict.status, "raw_n": verdict.raw_n,
                  "unique_fixtures": verdict.unique_fixtures,
                  "unique_opponents": verdict.unique_opponents,
                  "effective_n": verdict.effective_n,
                  "weight_concentration": verdict.weight_concentration,
                  "baseline_n": verdict.baseline_n},
    }
    assert not (set(c) & FORBIDDEN_OUTCOME_FIELDS), (
        "a forbidden outcome-shaped field leaked into a V8C candidate")
    return c


def llm_facing(candidate: dict) -> dict:
    """The Sonnet-facing projection: structural fields ONLY (P1 MEASSPACE)."""
    out = {k: v for k, v in candidate.items() if k not in SUPPORT_KEYS}
    assert_llm_safe(out)
    return out


def assert_llm_safe(candidate: dict) -> None:
    """Mechanical MEASSPACE check: no support statistic and no outcome-shaped field."""
    leaked = (set(candidate) & SUPPORT_KEYS) | (set(candidate) & FORBIDDEN_OUTCOME_FIELDS)
    if leaked:
        raise AssertionError(
            f"support/outcome fields leaked into the Sonnet-facing view: {sorted(leaked)}")


def _sort_key(c):
    """The TOTAL structural order. `ir_id` is unique, so this is a strict total order and the
    pagination cursor is well defined. Nothing here reads a support quantity, so the order
    cannot be read as a measurability ranking."""
    return (_STATUS_RANK.get(c["capability_status"], 9),
            c["complexity"]["n_conditions"], c["hypothesis_id"])


def build_fixture_universe(index, rec_i, *, ctx, capability, fixture_id=None,
                           grammar_kwargs=None) -> FixtureUniverse:
    """Enumerate and classify the WHOLE declared grammar at one target fixture."""
    rec = index.recs[rec_i]
    fid = str(fixture_id if fixture_id is not None else rec.fixture_id)
    evaluable, counts = [], {}
    n_shapes = n_structurally_invalid = n_capability_excluded = 0
    gkw = grammar_kwargs or {}

    from src.research.hypothesis_v71 import ir as IRM
    for spec in GR.candidate_specs(capability, **gkw):
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
        if verdict.evaluable:
            evaluable.append(_internal_candidate(spec, ir, status, adm, verdict))

    evaluable.sort(key=_sort_key)
    return FixtureUniverse(
        fixture_id=fid, rec_i=int(rec_i), competition=rec.competition,
        evaluable=tuple(evaluable), status_counts=dict(sorted(counts.items())),
        n_shapes_enumerated=n_shapes, n_structurally_invalid=n_structurally_invalid,
        n_capability_excluded=n_capability_excluded,
        n_admissible=n_shapes - n_structurally_invalid - n_capability_excluded,
        n_evaluable=len(evaluable))


# ---- the Sonnet-facing paginated search (P1 SEARCH-REACHABILITY) -------------------------
def search_evaluable(query: SearchQuery, fixture_universe: FixtureUniverse, *,
                     cursor: str | None = None, internal: bool = False) -> dict:
    """One PAGE of the evaluable universe matching `query`, plus a cursor.

    Deterministic: the ordering is the total structural key, so the same query + cursor always
    returns the same page. `internal=True` returns the full projection (for R/H/freeze);
    the default returns the Sonnet-facing projection.
    """
    rows = [c for c in fixture_universe.evaluable if _query_matches(query, c)]
    rows.sort(key=_sort_key)
    start = 0
    if cursor:
        for i, c in enumerate(rows):
            if c["hypothesis_id"] == cursor:
                start = i + 1
                break
        else:
            return {"results": [], "cursor": None, "n_remaining": 0, "n_matching": len(rows),
                    "cursor_status": "UNKNOWN_CURSOR"}
    page_size = min(int(query.max_results), PAGE_SIZE_CAP)
    page = rows[start:start + page_size]
    remaining = max(0, len(rows) - (start + len(page)))
    return {"results": [c if internal else llm_facing(c) for c in page],
            "cursor": (page[-1]["hypothesis_id"] if page and remaining else None),
            "n_remaining": remaining, "n_matching": len(rows), "cursor_status": "OK"}


def paginate_all(query: SearchQuery, fixture_universe: FixtureUniverse) -> list:
    """Every id reachable by exhaustively paginating `query`. Used to COMPUTE
    `unreachable_candidate_count` rather than assert it."""
    out, cursor, guard = [], None, 0
    while True:
        guard += 1
        if guard > 100000:                              # structural runaway guard
            raise AssertionError("pagination did not terminate")
        page = search_evaluable(query, fixture_universe, cursor=cursor)
        out.extend(c["hypothesis_id"] for c in page["results"])
        cursor = page["cursor"]
        if not cursor:
            return out


def reachability_report(fixture_universe: FixtureUniverse) -> dict:
    """Is every evaluable candidate reachable by the Sonnet-facing search? COMPUTED.

    The unfiltered query paginated to exhaustion must enumerate the entire evaluable set; if
    it does not, some region of S's action space is invisible while R and H can still reach it.
    """
    reachable = set(paginate_all(SearchQuery(max_results=PAGE_SIZE_CAP), fixture_universe))
    universe = set(fixture_universe.evaluable_ids())
    unreachable = universe - reachable
    return {"n_evaluable": len(universe), "n_reachable": len(reachable),
            "unreachable_candidate_count": len(unreachable),
            "unreachable_sample": sorted(unreachable)[:10],
            "page_size_cap": PAGE_SIZE_CAP,
            "ordering": "(capability_status_rank, n_conditions, ir_id) -- total order",
            "method": "exhaustive pagination of the unfiltered query"}


def _query_matches(q: SearchQuery, c: dict) -> bool:
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
        if want_profile and not any(x.get("dimension") == "opponent_profile"
                                    for x in c["conditions"]):
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
            "repairs": ["P1-UNIVERSE-GRAMMAR", "P1-MEASSPACE", "P1-SEARCH-REACHABILITY",
                        "P1-RESEARCH-FAMILY"],
            "grammar": GR.version_stamp()["grammar_version"],
            "pre_t": PT.version_stamp()["pre_t_evaluability_version"],
            "page_size_cap": PAGE_SIZE_CAP,
            "pagination": "deterministic cursor over a total structural order",
            "unreachable_count_is_computed_not_asserted": True,
            "projections": ["internal", "llm_facing"],
            "support_keys_withheld_from_llm": sorted(SUPPORT_KEYS),
            "measspace_rationale": ("the endpoint must measure football reasoning, not "
                                    "sample-size shopping; every candidate is already "
                                    "evaluable so no needed information is withheld"),
            "reads_target_outcome": False}

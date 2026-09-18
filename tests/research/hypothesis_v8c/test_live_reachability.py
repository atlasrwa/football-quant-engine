"""P1-C: reachability under the LIVE bounded-search protocol, not unlimited pagination."""
from __future__ import annotations

from src.research.hypothesis_v8c import live_reachability as LR
from src.research.hypothesis_v8c import universe as UNI


def test_every_evaluable_candidate_is_live_addressable(golden_universe):
    """Each candidate must be returned by its canonical query on the FIRST page."""
    rep = LR.audit_fixture(golden_universe)
    assert rep["n_evaluable"] > 0
    assert rep["n_live_unreachable"] == 0, rep["unreachable_sample"]
    assert rep["n_live_addressable"] == rep["n_evaluable"]
    assert rep["failing_candidate_classes"] == {}


def test_canonical_query_is_expressible_by_the_model(golden_universe):
    """Every field the canonical query uses must be a real SearchQuery parameter, or the model
    could not issue it."""
    fields = set(UNI.SearchQuery.__dataclass_fields__)
    for cand in golden_universe.evaluable[:30]:
        q = LR.canonical_query(cand)
        assert isinstance(q, UNI.SearchQuery)
        for k, v in vars(q).items():
            assert k in fields, f"{k} is not an expressible search parameter"


def test_call_cap_is_not_relaxed(golden_universe):
    """The repair must not quietly replace the 6-call cap with unlimited search."""
    rep = LR.audit_fixture(golden_universe)
    assert rep["call_cap_relaxed"] is False
    assert rep["max_search_calls"] == 6
    assert rep["page_size_cap"] == 50
    assert rep["max_pages_required_for_any_candidate"] <= rep["max_search_calls"]
    assert LR.version_stamp()["call_cap_relaxed"] is False


def test_worst_canonical_result_set_is_within_one_page(golden_universe):
    rep = LR.audit_fixture(golden_universe)
    assert rep["worst_canonical_result_set"] <= LR.PAGE_SIZE_CAP
    assert rep["candidates_requiring_pagination"] == 0

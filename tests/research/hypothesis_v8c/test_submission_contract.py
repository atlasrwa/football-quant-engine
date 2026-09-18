"""P1-D: the frozen model-submission contract.

All-or-nothing. A response containing one valid and one fabricated id is NOT converted into a
clean one-selection treatment -- partial acceptance would make the treatment arm's content
depend on which ids happened to survive validation.
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import runner as RUN
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GRAMMAR_KW


def _run(fu, cap, submit, n_search=1, max_results=50):
    def selector(session):
        for _ in range(n_search):
            session.search({"max_results": max_results})
        return submit(session)
    return RUN.run_fixture(fu, cap, selector=selector, grammar_kwargs=GRAMMAR_KW)


def _first_ids(fu, k):
    return [c["hypothesis_id"] for c in fu.evaluable[:k]]


def test_contract_constants_are_frozen():
    assert RUN.MAX_SELECTIONS == 8
    assert RUN.PARTIAL_ACCEPTANCE is False
    assert set(RUN.TERMINAL_SELECTION_STATUSES) == {RUN.OK, RUN.OK_ABSTAIN,
                                                    RUN.INVALID_SUBMISSION}


def test_valid_max_k_response_is_accepted(golden_universe, golden_env):
    ids = _first_ids(golden_universe, RUN.MAX_SELECTIONS)
    res = _run(golden_universe, golden_env.capability, lambda s: ids)
    assert res["status"] == RUN.OK
    assert res["accepted"] == ids
    assert res["research_yield"]["accepted"] == RUN.MAX_SELECTIONS


def test_over_cap_is_invalid(golden_universe, golden_env):
    ids = _first_ids(golden_universe, RUN.MAX_SELECTIONS + 1)
    res = _run(golden_universe, golden_env.capability, lambda s: ids)
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["accepted"] == []
    assert any(p["reason"] == RUN.REASON_OVER_CAP for p in res["problems"])


def test_duplicate_ids_are_invalid(golden_universe, golden_env):
    one = _first_ids(golden_universe, 1)[0]
    res = _run(golden_universe, golden_env.capability, lambda s: [one, one])
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["accepted"] == []
    assert any(p["reason"] == RUN.REASON_DUPLICATE for p in res["problems"])


def test_one_valid_plus_one_fabricated_accepts_NOTHING(golden_universe, golden_env):
    """THE case the audit names: no silent partial conversion."""
    good = _first_ids(golden_universe, 1)[0]
    res = _run(golden_universe, golden_env.capability, lambda s: [good, "mt_FABRICATED"])
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["accepted"] == [], "a mixed submission was partially accepted"
    assert res["research_yield"] == {"submitted": 2, "accepted": 0, "rejected": 2,
                                     "abstained": False}
    assert any(p["reason"] == RUN.REASON_NOT_RETURNED for p in res["problems"])


def test_fabricated_id_alone_is_invalid(golden_universe, golden_env):
    res = _run(golden_universe, golden_env.capability, lambda s: ["mt_INVENTED"])
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["accepted"] == []


def test_id_never_returned_this_session_is_invalid(golden_universe, golden_env):
    """A real id the model did not receive -- remembered, guessed, or from another run."""
    page = UNI.search_evaluable(UNI.SearchQuery(max_results=5), golden_universe)
    returned = {c["hypothesis_id"] for c in page["results"]}
    unseen = next(c["hypothesis_id"] for c in golden_universe.evaluable
                  if c["hypothesis_id"] not in returned)
    res = _run(golden_universe, golden_env.capability, lambda s: [unseen], max_results=5)
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["problems"][0]["reason"] == RUN.REASON_NOT_RETURNED


def test_id_from_another_fixture_is_invalid(golden_env, golden_universe):
    """An id valid in a DIFFERENT fixture's universe is not valid here."""
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import pit_context as PC
    # RICHER than the golden fixture, so its evaluable set is a strict superset and a
    # genuinely foreign id exists.
    other_env = G.build_environment(n_prior_blocks=90, n_opponents=16,
                                    metrics=("goals", "yellow_cards"))
    octx = PC.build_pit_context(other_env.index, other_env.target_pos)
    other = UNI.build_fixture_universe(other_env.index, other_env.target_pos, ctx=octx,
                                       capability=other_env.capability,
                                       fixture_id=other_env.target_fixture_id,
                                       grammar_kwargs=GRAMMAR_KW)
    here = set(golden_universe.evaluable_ids())
    foreign = next((c["hypothesis_id"] for c in other.evaluable
                    if c["hypothesis_id"] not in here), None)
    if foreign is None:
        pytest.skip("the two universes coincide; no cross-fixture id available")
    res = _run(golden_universe, golden_env.capability, lambda s: [foreign])
    assert res["status"] == RUN.INVALID_SUBMISSION
    assert res["accepted"] == []


def test_abstention_is_legal(golden_universe, golden_env):
    res = _run(golden_universe, golden_env.capability, lambda s: [])
    assert res["status"] == RUN.OK_ABSTAIN
    assert res["accepted"] == []
    assert res["research_yield"]["abstained"] is True


def test_every_outcome_has_an_explicit_status(golden_universe, golden_env):
    """No submission shape may fall through without a named terminal status."""
    good = _first_ids(golden_universe, 1)[0]
    for submit in ([], [good], [good, good], ["mt_X"], [good, "mt_X"],
                   _first_ids(golden_universe, RUN.MAX_SELECTIONS + 1)):
        res = _run(golden_universe, golden_env.capability, lambda s, v=submit: v)
        assert res["status"] in RUN.TERMINAL_SELECTION_STATUSES
        assert "research_yield" in res
